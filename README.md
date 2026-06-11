# Route Planner

A web-based route planner that calculates multi-waypoint driving routes using OSRM. Supports brute-force TSP optimization for up to 8 waypoints and optional dynamic conditions that factor in real-time weather and road surface quality.

## Demo

[![Watch the demo](https://img.youtube.com/vi/hWsyaENlLjM/maxresdefault.jpg)](https://youtu.be/hWsyaENlLjM)

## What it does

- Drop up to 8 waypoints on a dark-themed Leaflet map
- Calculate driving routes between waypoints using the OSRM public API
- Optimize waypoint order using a brute-force Travelling Salesman approach (permutation-based, capped at 8 since 8! is still manageable)
- Optionally apply dynamic penalties to travel time based on weather (rain, wind, fog) and road surface type (gravel, dirt, unpaved)
- Display route distance, duration, and adjusted duration on the sidebar

## Tech Stack

- **Backend:** Flask (Python)
- **Routing API:** OSRM (Open Source Routing Machine, public demo server)
- **Weather API:** Open-Meteo (free, no API key)
- **Road data:** Overpass API (queries OpenStreetMap)
- **Graph library:** NetworkX
- **Frontend:** Leaflet.js with CartoDB dark tiles

## Setup

### Install dependencies

```
pip install flask requests networkx matplotlib
```

### Run

```
python app.py
```

Server starts at `http://localhost:5000`.

## How the dynamic conditions work

When the "Dynamic conditions" toggle is on, two things happen before the route is returned:

1. **Weather penalty:** Fetches current weather at the midpoint of all waypoints from Open-Meteo. Heavy rain adds up to 40% to duration, fog adds 25%, thunderstorms add 35%, strong winds add up to 20%.

2. **Road quality factor:** Queries Overpass for road surface tags in the bounding box of the waypoints. Asphalt/paved roads have no penalty. Gravel gets a 1.4x multiplier, dirt gets 1.5x, mud gets 1.7x. The final factor is a weighted average across all tagged roads in the area.

These multipliers are applied to duration only. Distance stays the same since the actual road length does not change with conditions.

## Limitations

- Uses the OSRM public demo server, so throttling may happen under heavy use
- TSP is brute-force, so it is limited to 8 waypoints (8! = 40,320 permutations)
- Weather is fetched for the midpoint of all waypoints, not per-segment
- Road quality is based on OSM surface tags in the bounding box, not matched to the exact route
- Overpass and Open-Meteo are free community services, so occasional downtime is possible (the app falls back to 1.0x multipliers if either API fails)

## APIs Used

| API | Purpose | Auth |
|-----|---------|------|
| OSRM | Driving routes and distance matrix | None (public demo) |
| Open-Meteo | Current weather conditions | None |
| Overpass | Road surface metadata from OSM | None |
