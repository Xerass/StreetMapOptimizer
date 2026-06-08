#for basic web app interface we use flask (not within task list but found it fun)
from flask import Flask, render_template, request, jsonify

import requests
import networkx as nx
import matplotlib.pyplot as plt

#used in per-segment distance calcs
from math import radians, sin, cos, sqrt, atan2

#used in route permutations
from itertools import permutations

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



#now that we infroduced multiple routess, we know its going to experience the classic Travelling Salesman Problem
#in order to solve this, we can use a brute force approach that is waypoint limited
#capped it at 8 since 8! = 40320 which is still manageable for a brute force approach
#anything beyond that becomes comoputationally expensive and likely capped by the api call

#to be precise, this returns an ordered list that represent the best order of the waypoints
def optimize_routes(waypoints):
    n = len(waypoints)

    if n <= 2:
        #bugfix: trailing comma made this return a tuple instead of a list
        return list(range(n))

    distances, durations = get_distance_matrix(waypoints)

    #were gonna brute force all permutations lmao

    best_order = None
    best_distance = float("inf")

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
            total += d

        #if it passes our validity checks, we set it as best_order if its also better than current
        if valid and total < best_distance:
            best_distance = total
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

    if len(waypoints) < 2:
        #we use jsonify to simplify communcation between back and front ends
        return jsonify({"error": "Need at least 2 waypoints"}), 400
    

    if len(waypoints) > 8:
        return jsonify({"error": "Max 8 waypoints (brute-force TSP)"}), 400
    

    try: 
        if optimize and len(waypoints) > 2:
            order = optimize_routes(waypoints)
            if order is None:
                return jsonify({"error": "Max 8 waypoints (brute-force TSP)"}), 400
           
            #order the waypoitns
            optimized_waypoints = [waypoints[i] for i in order]
           
            segments = [] #we treat each pair as a segment
            total_distance = 0
            total_duration = 0

            for k in range(len(order) - 1):
                #now that we have our orderings, we can now use our 2 point get_osrm_route

                dist, dur, coords = get_osrm_route(optimized_waypoints[k], optimized_waypoints[k + 1])
                segments.append(coords)
                total_distance += dist
                total_duration += dur

            
            return jsonify({
                "segments": segments,
                "distance": total_distance,
                "duration": total_duration,
                "order": order,
                "optimized_waypoints": optimized_waypoints
            })
        
        #if oprimized was false, sequential routing is used (no TSP optim)
        else:
            segments = []
            total_distance = 0
            total_duration = 0
            for i in range(len(waypoints) - 1):
                dist, dur, coords = get_osrm_route(waypoints[i], waypoints[i + 1])
                segments.append(coords)
                total_distance += dist
                total_duration += dur
 
            return jsonify({
                "segments": segments,
                "distance": total_distance,
                "duration": total_duration,
                "order": list(range(len(waypoints))),
                "optimized_waypoints": waypoints
            })

    except Exception as e:
        #likely an issue beyond our code
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)