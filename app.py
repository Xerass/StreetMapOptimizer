#for basic web app interface we use flask (not within task list but found it fun)
from flask import Flask, render_template, request, jsonify

import requests
import networkx as nx
import matplotlib.pyplot as plt

#used in per-segment distance calcs
from math import radians, sin, cos, sqrt, atan2

#used in route permutations
from itertools import permutations


#mapping of penalties for road quality
SURFACE_PENALTIES = {
    "asphalt": 1.0,
    "concrete": 1.0,
    "paved": 1.0,
    "cobblestone": 1.2,
    "compacted": 1.25,
    "gravel": 1.4,
    "dirt": 1.5,
    "mud": 1.7,
    "sand": 1.6,
    "unpaved": 1.45,
    "ground": 1.5,
}


app = Flask(__name__)



#so osrm is a routing engine that we cna just use to 
#get the route between 2 points
#a router 
def get_osrm_route(start, end):
    #this osrm api call is the free one so throttling may be expected
    url = f"http://router.project-osrm.org/route/v1/driving/{start[0]},{start[1]};{end[0]},{end[1]}?overview=full&geometries=geojson"
    response = requests.get(url)
    data = response.json()

    #we need to parse that
    if data.get("routes"):
        #index 0 presents "best" route
        route = data["routes"][0]
        distance = route["distance"]
        duration = route["duration"]
        coords = route["geometry"]["coordinates"]
        return distance, duration, coords
    
    else:
        #slight modification on the example
        #from past experiences, vague error messages with API
        #tend to just lengthen the debugging process
        #here we deliver clear error messages
        code = data.get("code", "Unknown")
        message = data.get("message", "No additional info")
        raise Exception(f"OSRM error [{code}]: {message}")

#calculates straight line distance between 2 points in a spehere
def haversine(coord1, coord2):
    R = 6371000  #our "sphere" is radius of the earth itself

    lat1, lon1 = radians(coord1[1]), radians(coord1[0])
    lat2, lon2 = radians(coord2[1]), radians(coord2[0])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c

#given a list of waypoints, create a distance matrix with them
#this will be the main driver for n > 2 waypoints 
#this is seprate from the 2 point one since we want to use it for multiple waypoints
#this makes it 1 call, so its much more respectful to the API, we really dont want to be hogging requests 
def get_distance_matrix(waypoints):
    #calls osrm for a table request
    #call returns  Returns (distances[][], durations[][]), both are n×n matrices
    #none ifno route exists

    #since we need to cram in our waypoints into the url, we need to do this horribly ugly fstring
    coords_str = ";".join(f"{wp[0]},{wp[1]}" for wp in waypoints)

    url = (
        f"http://router.project-osrm.org/table/v1/driving/{coords_str}"
        f"?annotations=distance,duration"
    )

    response = requests.get(url)
    data = response.json()

    if data.get("code") != "Ok":
        code = data.get("code", "Unknown")
        message = data.get("message", "No additional info")
        raise Exception(f"OSRM table error [{code}]: {message}")

    return data["distances"], data["durations"]

#open-meteo offers free weeather status along an area
#we can use this to find the weather at each waypoint (per segment proved to be a lot more API call intensive)
#unfavorable weather results in a bigger penalty, clear = no penalty

def get_waypoint_weather(waypoints):
    #get the midpoint of all waypoints as a rough location for wather
    penalties = []
    infos = []

    for i, wp in enumerate(waypoints):
        #this ensures that our calls are at max N
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={wp[1]}&longitude={wp[0]}"
                f"&current=weather_code,wind_speed_10m,precipitation"
            )
            response = requests.get(url, timeout = 5)
            data = response.json()
            #current weather, grab it
            current = data.get("current", {})

            precip = current.get("precipitation", 0)
            wind = current.get("wind_speed_10m", 0)
            weather_code = current.get("weather_code", 0)

            #penalties are fully arbitrary, vibes based             
            
            penalty = 1.0

            #precipitation penalty
            if precip > 10:
                penalty += 0.5    # heavy rain
            elif precip > 2:
                penalty += 0.2    # moderate rain
            elif precip > 0:
                penalty += 0.1    # drizzle

            #wind penalty
            if wind > 60:
                penalty += 0.2
            elif wind > 30:
                penalty += 0.1


            penalties.append(round(penalty, 2))
            infos.append({
                "waypoint": i + 1,
                "coords": [round(wp[0], 4), round(wp[1], 4)],
                "precipitation_mm": precip,
                "wind_kmh": wind,
                "weather_code": weather_code,
                "penalty": round(penalty, 2)
            })

        except Exception:
            #API must have flunked, just return defaults
            penalties.append(1.0)
            infos.append({
                "waypoint": i + 1,
                "coords": [round(wp[0], 4), round(wp[1], 4)],
                "precipitation_mm": 0,
                "wind_kmh": 0,
                "weather_code": 0,
                "penalty": 1.0
            })

    return penalties, infos

def get_road_quality_factor(waypoints):
    #define a bounding box from the waypoint to serve as our road quality sampler
    lons = [wp[0] for wp in waypoints]
    lats = [wp[1] for wp in waypoints]
    buffer = 0.01  # roughly 1km padding

    bbox = f"{min(lats)-buffer},{min(lons)-buffer},{max(lats)+buffer},{max(lons)+buffer}"

    #query on overpass
    query = f"""
    [out:json][timeout:10];
    way["highway"]["surface"]({bbox});
    out tags;
    """

    try:
        response = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            timeout=10
        )

        data = response.json()
        elements = data.get("elements", [])
        
        #if elements ever returned null, just set it to defaults
        if not elements:
            return 1.0, {"surfaces": {}, "factor": 1.0, "road_count": 0}


        #we perform a simple count and weighted average
        surface_counts = {}
        for elem in elements:
            surface = elem.get("tags", {}).get("surface", "unknown")
            surface_counts[surface] = surface_counts.get(surface, 0) + 1

        total_weight = 0
        total_penalty = 0
        for surface, count in surface_counts.items():
            penalty = SURFACE_PENALTIES.get(surface, 1.15) #surfaces not listed we just throw a conservative 15% penalty
            total_penalty += penalty * count
            total_weight += count

        factor = round(total_penalty / total_weight, 2) if total_weight > 0 else 1.0


        road_info = {
            "surfaces": surface_counts,
            "factor": factor,
            "road_count": total_weight
        }

        return factor, road_info
    
    except Exception:

        return 1.0, {"surfaces": {}, "factor": 1.0, "road_count": 0}

#now that we infroduced multiple routess, we know its going to experience the classic Travelling Salesman Problem
#in order to solve this, we can use a brute force approach that is waypoint limited
#capped it at 8 since 8! = 40320 which is still manageable for a brute force approach
#anything beyond that becomes comoputationally expensive and likely capped by the api call

#to be precise, this returns an ordered list that represent the best order of the waypoints
def optimize_routes(waypoints, weather_penalties=None, road_factor=1.0):
    n = len(waypoints)

    if n <= 2:
        #bugfix: trailing comma made this return a tuple instead of a list
        return list(range(n))

    distances, durations = get_distance_matrix(waypoints)

    best_order = None
    best_cost = float("inf")

    for perm in permutations(range(1, n)):
        order = (0,) + perm #fix the first point, permute the rest
        total = 0
        valid = True
        for k in range(len(order) - 1):
            
            #get distances between the pair
            d = distances[order[k]][order[k + 1]]
            #bugfix: missing parens meant 'or' vs 'and' precedence could misfire
            if d is None or (d == 0 and order[k] != order[k + 1]):
                #route is invalid, no route exists between these waypoints
                valid = False
                break

            #if we have weather data, weight the segment cost
            #penalty for a segment = average of both endpoint penalties
            if weather_penalties:
                seg_weather = (weather_penalties[order[k]] + weather_penalties[order[k + 1]]) / 2
            else:
                seg_weather = 1.0

            total += d * seg_weather * road_factor

        #if it passes our validity checks, we set it as best_order if its also better than current
        if valid and total < best_cost:
            best_cost = total
            best_order = list(order)
 
    return best_order

def build_graph(coords):
    G = nx.Graph()

    for i in range(len(coords) - 1):
        #map out each coordinate along the route
        point_a = tuple(coords[i])
        point_b = tuple(coords[i + 1])
        distance = haversine(point_a, point_b)
        G.add_edge(point_a, point_b, weight=distance)
    
    return G


# =========== flask routes and app setup ====================

#entry point
@app.route("/")
def index():
    return render_template("index.html")


#define our POST 
@app.route("/api/route", methods=["POST"])
def calculate_route():
    #expects JSON {"waypoints": [[lon, lat], [lon,lat]] ...., optimize:bool}

    #returns the route segments with coords for the drawing on the map
    data = request.get_json()
    waypoints = data.get("waypoints", [])
    optimize = data.get("optimize", False)
    dynamic = data.get("dynamic", False)

    if len(waypoints) < 2:
        return jsonify({"error": "Need at least 2 waypoints"}), 400

    if len(waypoints) > 8:
        return jsonify({"error": "Max 8 waypoints (brute-force TSP)"}), 400

    try:
        weather_penalties = None
        weather_infos = None
        road_factor = 1.0
        road_info = None

        if dynamic:
            weather_penalties, weather_infos = get_waypoint_weather(waypoints)
            road_factor, road_info = get_road_quality_factor(waypoints)

        if optimize and len(waypoints) > 2:
            order = optimize_routes(waypoints, weather_penalties, road_factor)
            if order is None:
                return jsonify({"error": "Could not find a valid route between all waypoints"}), 400

            optimized_waypoints = [waypoints[i] for i in order]

            segments = []
            total_distance = 0
            total_duration = 0
            adjusted_duration = 0

            for k in range(len(order) - 1):
                dist, dur, coords = get_osrm_route(optimized_waypoints[k], optimized_waypoints[k + 1])
                segments.append(coords)
                total_distance += dist
                total_duration += dur

                if weather_penalties:
                    seg_weather = (weather_penalties[order[k]] + weather_penalties[order[k + 1]]) / 2
                else:
                    seg_weather = 1.0
                adjusted_duration += dur * seg_weather * road_factor

            result = {
                "segments": segments,
                "distance": total_distance,
                "duration": total_duration,
                "adjusted_duration": round(adjusted_duration, 1),
                "order": order,
                "optimized_waypoints": optimized_waypoints
            }

        else:
            segments = []
            total_distance = 0
            total_duration = 0
            adjusted_duration = 0

            for i in range(len(waypoints) - 1):
                dist, dur, coords = get_osrm_route(waypoints[i], waypoints[i + 1])
                segments.append(coords)
                total_distance += dist
                total_duration += dur

                if weather_penalties:
                    seg_weather = (weather_penalties[i] + weather_penalties[i + 1]) / 2
                else:
                    seg_weather = 1.0
                adjusted_duration += dur * seg_weather * road_factor

            result = {
                "segments": segments,
                "distance": total_distance,
                "duration": total_duration,
                "adjusted_duration": round(adjusted_duration, 1),
                "order": list(range(len(waypoints))),
                "optimized_waypoints": waypoints
            }

        if dynamic:
            result["dynamic"] = {
                "waypoint_weather": weather_infos,
                "road_quality": road_info,
                "road_factor": road_factor
            }

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)