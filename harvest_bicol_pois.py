#a one time harverster 

import json
import requests
import time

#were gonna be using overpass to harvest the POIs, this will run once, give us the js file and we can just use it locally from there
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

#bicol Region bounding box: south, west, north, east
BICOL_BBOX = "12.4,122.8,14.4,124.8"

# POI categories to harvest
QUERIES = [
    ("mall",        'nw["shop"="mall"]'),
    ("hospital",    'nw["amenity"="hospital"]'),
    ("school",      'nw["amenity"="school"]'),
    ("university",  'nw["amenity"="university"]'),
    ("church",      'nw["amenity"="place_of_worship"]'),
    ("government",  'nw["office"="government"]'),
    ("bus_station",  'nw["amenity"="bus_station"]'),
    ("airport",     'nw["aeroway"="aerodrome"]'),
    ("port",        'nw["amenity"="ferry_terminal"]'),
    ("tourism",     'nw["tourism"="attraction"]'),
    ("museum",      'nw["tourism"="museum"]'),
    ("hotel",       'nw["tourism"="hotel"]'),
    ("resort",      'nw["leisure"="resort"]'),
    ("park",        'nw["leisure"="park"]'),
    ("market",      'nw["amenity"="marketplace"]'),
    ("police",      'nw["amenity"="police"]'),
    ("fire_station", 'nw["amenity"="fire_station"]'),
    ("library",     'nw["amenity"="library"]'),
    ("bank",        'nw["amenity"="bank"]'),
    ("fuel",        'nw["amenity"="fuel"]'),
    ("stadium",     'nw["leisure"="stadium"]'),
    ("cinema",      'nw["amenity"="cinema"]'),
]


def build_overpass_query(categories):
    parts = []
    for _, selector in categories:
        # nw shorthand isn't supported by all Overpass versions, expand to node + way
        tag = selector[2:]  # strip 'nw' prefix, keep '["key"="value"]'
        parts.append(f"  node{tag}({BICOL_BBOX});")
        parts.append(f"  way{tag}({BICOL_BBOX});")

    return f"""
[out:json][timeout:120];
(
{chr(10).join(parts)}
);
out center tags;
""".strip()


def extract_pois(data, categories):
    #for each element, in data we get its tag, name and if its type is a node, its a valid lat.lon we can use to serve as a POT
    #we then attach its name as a key. and append to seen to drevent dupes
    category_map = {sel: cat for cat, sel in categories}
    pois = []
    seen = set()

    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue

        if el["type"] == "node":
            lat, lon = el["lat"], el["lon"]
        elif "center" in el:
            lat, lon = el["center"]["lat"], el["center"]["lon"]
        else:
            continue

        key = (name.lower().strip(), round(lat, 3), round(lon, 3))
        if key in seen:
            continue
        seen.add(key)

        poi_type = classify(tags, categories)

        pois.append({
            "name": name,
            "type": poi_type,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
        })

    return pois


def classify(tags, categories):
    for cat, _ in categories:
        if cat == "mall" and tags.get("shop") == "mall":
            return "mall"
        if cat == "tourism" and tags.get("tourism") == "attraction":
            return "tourism"
        if cat == "museum" and tags.get("tourism") == "museum":
            return "museum"
        if cat == "hotel" and tags.get("tourism") == "hotel":
            return "hotel"
        if cat == "resort" and tags.get("leisure") == "resort":
            return "resort"
        if cat == "park" and tags.get("leisure") == "park":
            return "park"
        if cat == "stadium" and tags.get("leisure") == "stadium":
            return "stadium"
        if cat == "airport" and tags.get("aeroway") == "aerodrome":
            return "airport"
        if tags.get("amenity") == cat:
            return cat
        if tags.get("office") == "government" and cat == "government":
            return "government"
    return "other"


def main():
    print("Building Overpass query for Bicol POIs")
    query = build_overpass_query(QUERIES)

    print("Sending request to Overpass API (might take a while)")
    #lmao, apache kept rejecting the call, we need to set up a user agent so we get through
    headers = {
        "User-Agent": "BicolRoutePlanner/1.0",
        "Accept": "*/*",
    }
    resp = requests.post(OVERPASS_URL, data={"data": query}, headers=headers, timeout=180)

    #response status, debuggine helper
    if not resp.ok:
        print(f"HTTP {resp.status_code}")
        print(resp.text[:2000])
        resp.raise_for_status()
    data = resp.json()

    print(f"Raw elements returned: {len(data.get('elements', []))}")

    pois = extract_pois(data, QUERIES)
    pois.sort(key=lambda p: (p["type"], p["name"]))

    out_path = "bicol_locations.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pois, f, ensure_ascii=False, indent=2)

    type_counts = {}
    for p in pois:
        type_counts[p["type"]] = type_counts.get(p["type"], 0) + 1

    print(f"\nSaved {len(pois)} POIs to {out_path}")
    print("\nBreakdown by type:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:15s} {c}")


if __name__ == "__main__":
    main()
