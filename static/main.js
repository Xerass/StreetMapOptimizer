//state holders
let waypoints = [];     // [[lon, lat], ...]
let markers = [];       // leaflet markerscd
let routeLayer = null;  // polyline layer group

// clamped to Bicol Region
const bicolBounds = L.latLngBounds([12.4, 122.8], [14.4, 124.8]);

const map = L.map('map', {
    zoomControl: false,
    maxBounds: bicolBounds,
    maxBoundsViscosity: 1.0,
    minZoom: 8
}).setView([13.1594, 123.7103], 9);

// zoom control top-right
L.control.zoom({ position: 'topright' }).addTo(map);

// CartoDB dark tiles, free since we are broke boys
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://carto.com/">CARTO</a> | &copy; <a href="https://osm.org/copyright">OSM</a>',
    maxZoom: 19
}).addTo(map);

//refs
const waypointList = document.getElementById('waypointList');
const routeBtn = document.getElementById('routeBtn');
const clearBtn = document.getElementById('clearBtn');
const optimizeToggle = document.getElementById('optimizeToggle');
const routeStats = document.getElementById('routeStats');
const dynamicToggle = document.getElementById('dynamicToggle');
const conditionsPanel = document.getElementById('conditionsPanel');
const statusBar = document.getElementById('statusBar');
const poiSearch = document.getElementById('poiSearch');
const searchResults = document.getElementById('searchResults');

//poi icons
const POI_ICONS = {
    airport:      'fa-plane',
    stadium:      'fa-futbol',
    mall:         'fa-cart-shopping',
    university:   'fa-graduation-cap',
    museum:       'fa-landmark',
    cinema:       'fa-film',
    hospital:     'fa-hospital',
    tourism:      'fa-camera',
    resort:       'fa-umbrella-beach',
    park:         'fa-tree',
    bus_station:  'fa-bus',
    hotel:        'fa-bed',
    government:   'fa-building-columns',
    library:      'fa-book',
    police:       'fa-shield-halved',
    fire_station: 'fa-fire-extinguisher',
    bank:         'fa-money-bill',
    fuel:         'fa-gas-pump',
    school:       'fa-school',
    market:       'fa-store',
    other:        'fa-location-dot',
};

// zoom thresholds, lower number = visible earlier (zoomed out more)
const POI_ZOOM = {
    airport: 8, stadium: 8,
    mall: 10, university: 10, museum: 10, cinema: 10,
    hospital: 11, tourism: 11, resort: 11, park: 11, bus_station: 11,
    hotel: 12, government: 12, library: 12,
    police: 13, fire_station: 13, bank: 13, fuel: 13, market: 13,
    school: 14, other: 14,
};

let allPois = [];
let poiLayer = L.layerGroup().addTo(map);
let poiMarkers = [];

fetch('/static/bicol_locations.json')
    .then(r => r.json())
    .then(data => {
        allPois = data;
        updatePoiMarkers();
    });

function updatePoiMarkers() {
    poiLayer.clearLayers();
    poiMarkers = [];
    const zoom = map.getZoom();
    const bounds = map.getBounds();

    for (const poi of allPois) {
        const minZoom = POI_ZOOM[poi.type] || 14;
        if (zoom < minZoom) continue;

        const latlng = L.latLng(poi.lat, poi.lon);
        if (!bounds.contains(latlng)) continue;

        const icon = POI_ICONS[poi.type] || 'fa-location-dot';
        const m = L.marker(latlng, {
            icon: L.divIcon({
                className: '',
                html: `<div class="poi-marker"><i class="fa-solid ${icon}"></i></div>`,
                iconSize: [24, 24],
                iconAnchor: [12, 12],
            }),
            interactive: true,
        });

        m.bindTooltip(poi.name, {
            className: 'poi-tooltip',
            direction: 'top',
            offset: [0, -14],
        });

        m.on('click', () => {
            if (waypoints.length >= 8) {
                setStatus('Max 8 waypoints reached', 'error');
                return;
            }
            addWaypoint(poi.lon, poi.lat, poi.name);
            setStatus(`added ${poi.name}`);
        });

        poiLayer.addLayer(m);
        poiMarkers.push(m);
    }
}

map.on('zoomend', updatePoiMarkers);
map.on('moveend', updatePoiMarkers);

//serarch functionality with fuzzy matching
let searchTimeout = null;

poiSearch.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    const q = poiSearch.value.trim().toLowerCase();

    if (q.length < 2) {
        searchResults.classList.remove('visible');
        return;
    }

    searchTimeout = setTimeout(() => {
        const matches = allPois
            .filter(p => p.name.toLowerCase().includes(q))
            .slice(0, 20);

        if (matches.length === 0) {
            searchResults.innerHTML = '<div class="search-result-item"><span class="search-result-name" style="color:var(--text-dim)">No results</span></div>';
        } else {
            searchResults.innerHTML = matches.map(p => `
                <div class="search-result-item" data-lat="${p.lat}" data-lon="${p.lon}" data-name="${p.name.replace(/"/g, '&quot;')}">
                    <span class="search-result-icon"><i class="fa-solid ${POI_ICONS[p.type] || 'fa-location-dot'}"></i></span>
                    <div class="search-result-info">
                        <div class="search-result-name">${p.name}</div>
                        <div class="search-result-type">${p.type.replace('_', ' ')}</div>
                    </div>
                </div>
            `).join('');
        }
        searchResults.classList.add('visible');
    }, 150);
});

searchResults.addEventListener('click', (e) => {
    const item = e.target.closest('.search-result-item');
    if (!item || !item.dataset.lat) return;

    if (waypoints.length >= 8) {
        setStatus('Max 8 waypoints reached', 'error');
        return;
    }

    const lat = parseFloat(item.dataset.lat);
    const lon = parseFloat(item.dataset.lon);
    const name = item.dataset.name;

    addWaypoint(lon, lat, name);
    map.setView([lat, lon], 14);
    poiSearch.value = '';
    searchResults.classList.remove('visible');
    setStatus(`added ${name}`);
});

poiSearch.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        searchResults.classList.remove('visible');
        poiSearch.blur();
    }
});

document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-section')) {
        searchResults.classList.remove('visible');
    }
});

//WMO weather codes to readable names
const weatherNames = {
    0: 'Clear', 1: 'Mostly clear', 2: 'Partly cloudy', 3: 'Overcast',
    45: 'Fog', 48: 'Rime fog',
    51: 'Light drizzle', 53: 'Drizzle', 55: 'Heavy drizzle',
    61: 'Light rain', 63: 'Rain', 65: 'Heavy rain',
    71: 'Light snow', 73: 'Snow', 75: 'Heavy snow',
    80: 'Light showers', 81: 'Showers', 82: 'Heavy showers',
    95: 'Thunderstorm', 96: 'Hail storm', 99: 'Severe storm'
};

//on click, add waypoint
map.on('click', function(e) {
    if (waypoints.length >= 8) {
        setStatus('Max 8 waypoints reached', 'error');
        return;
    }

    const lon = e.latlng.lng;
    const lat = e.latlng.lat;

    // snap to nearest POI if close enough
    const nearest = findNearestPoi(lat, lon, 0.002);
    if (nearest) {
        addWaypoint(nearest.lon, nearest.lat, nearest.name);
    } else {
        addWaypoint(lon, lat);
    }
});

function findNearestPoi(lat, lon, threshold) {
    let best = null;
    let bestDist = threshold;
    for (const p of allPois) {
        const d = Math.hypot(p.lat - lat, p.lon - lon);
        if (d < bestDist) {
            bestDist = d;
            best = p;
        }
    }
    return best;
}

function createMarkerIcon(label) {
    return L.divIcon({
        className: '',
        html: `<div class="custom-marker"></div>
               <div class="custom-marker-label">${label}</div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7]
    });
}

let waypointNames = [];

function addWaypoint(lon, lat, name) {
    const idx = waypoints.length;
    waypoints.push([lon, lat]);
    waypointNames.push(name || null);

    const marker = L.marker([lat, lon], {
        icon: createMarkerIcon(idx + 1),
        draggable: true
    }).addTo(map);

    // drag to update position
    marker.on('dragend', function(e) {
        const pos = e.target.getLatLng();
        waypoints[idx] = [pos.lng, pos.lat];
        renderWaypointList();
        clearRoute();
    });

    markers.push(marker);
    renderWaypointList();
    clearRoute();
    setStatus(`waypoint ${idx + 1} added`);
}

function removeWaypoint(idx) {
    waypoints.splice(idx, 1);
    waypointNames.splice(idx, 1);
    map.removeLayer(markers[idx]);
    markers.splice(idx, 1);

    // rebuild marker labels
    markers.forEach((m, i) => m.setIcon(createMarkerIcon(i + 1)));

    renderWaypointList();
    clearRoute();
}

function renderWaypointList() {
    routeBtn.disabled = waypoints.length < 2;

    if (waypoints.length === 0) {
        waypointList.innerHTML = `
            <div class="empty-state">
                Click anywhere on the map<br>to add waypoints
            </div>`;
        return;
    }

    waypointList.innerHTML = waypoints.map((wp, i) => {
        const display = waypointNames[i]
            ? `<div class="waypoint-name">${waypointNames[i]}</div><div class="waypoint-coords-sub">${wp[1].toFixed(4)}, ${wp[0].toFixed(4)}</div>`
            : `<div class="waypoint-coords">${wp[1].toFixed(4)}, ${wp[0].toFixed(4)}</div>`;
        return `
            <div class="waypoint-item">
                <div class="waypoint-number">${i + 1}</div>
                <div class="waypoint-info">${display}</div>
                <button class="waypoint-remove" onclick="removeWaypoint(${i})">×</button>
            </div>`;
    }).join('');
}

//actual route stuff
routeBtn.addEventListener('click', async () => {
    if (waypoints.length < 2) return;

    clearRoute();
    setStatus('calculating route...', 'loading');
    routeBtn.disabled = true;

    try {
        const res = await fetch('/api/route', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                waypoints: waypoints,
                optimize: optimizeToggle.checked,
                dynamic: dynamicToggle.checked
            })
        });

        const data = await res.json();

        if (!res.ok) {
            setStatus(data.error || 'Route calculation failed', 'error');
            routeBtn.disabled = false;
            return;
        }

        drawRoute(data);

        // update marker order if optimized
        if (optimizeToggle.checked && data.optimized_waypoints) {
            waypoints = data.optimized_waypoints;
            // rebuild markers in new order
            markers.forEach(m => map.removeLayer(m));
            markers = [];
            waypoints.forEach((wp, i) => {
                const marker = L.marker([wp[1], wp[0]], {
                    icon: createMarkerIcon(i + 1),
                    draggable: true
                }).addTo(map);

                const idx = i;
                marker.on('dragend', function(e) {
                    const pos = e.target.getLatLng();
                    waypoints[idx] = [pos.lng, pos.lat];
                    renderWaypointList();
                    clearRoute();
                });

                markers.push(marker);
            });
            renderWaypointList();
        }

        // show stats
        const distKm = (data.distance / 1000).toFixed(2);
        const durMin = (data.duration / 60).toFixed(1);
        document.getElementById('statDistance').textContent = `${distKm} km`;
        document.getElementById('statDuration').textContent = `${durMin} min`;
        document.getElementById('statPoints').textContent = waypoints.length;
        routeStats.classList.add('visible');

        //show per-waypoint conditions if dynamic was on
        if (data.dynamic) {
            const dyn = data.dynamic;
            const adjMin = (data.adjusted_duration / 60).toFixed(1);

            //per-waypoint weather breakdown, ordered by final route order
            const wpWeather = dyn.waypoint_weather;
            const order = data.order;

            //reorder weather infos to match the optimized order
            const orderedWeather = order.map(i => wpWeather[i]);

            document.getElementById('condWaypoints').innerHTML = orderedWeather.map((w, i) => {
                const name = weatherNames[w.weather_code] || `Code ${w.weather_code}`;
                const penaltyPct = ((w.penalty - 1) * 100).toFixed(0);
                const penaltyStr = w.penalty > 1.0 ? `+${penaltyPct}%` : 'none';
                const penaltyClass = w.penalty >= 1.3 ? 'penalty-high' : w.penalty > 1.0 ? 'penalty-mid' : 'penalty-ok';

                return `
                    <div class="cond-waypoint">
                        <div class="cond-wp-number">${i + 1}</div>
                        <div class="cond-wp-detail">
                            <span class="cond-wp-weather">${name}</span>
                            <span class="cond-wp-sub">${w.precipitation_mm}mm rain, ${w.wind_kmh}km/h wind</span>
                        </div>
                        <div class="cond-wp-penalty ${penaltyClass}">${penaltyStr}</div>
                    </div>`;
            }).join('');

            //road quality
            const roadInfo = dyn.road_quality;
            const topSurfaces = Object.entries(roadInfo.surfaces)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 3)
                .map(([s, c]) => s)
                .join(', ');
            document.getElementById('condRoad').textContent =
                `${roadInfo.factor}x` + (topSurfaces ? ` (${topSurfaces})` : '');

            //adjusted duration
            document.getElementById('condAdjDuration').textContent = `${adjMin} min`;

            conditionsPanel.classList.add('visible');
        } else {
            conditionsPanel.classList.remove('visible');
        }

        setStatus(`route found — ${distKm} km`);

    } catch (err) {
        setStatus(`error: ${err.message}`, 'error');
    }

    routeBtn.disabled = false;
});

function drawRoute(data) {
    routeLayer = L.layerGroup().addTo(map);

    data.segments.forEach(segment => {
        // OSRM returns [lon, lat], leaflet wants [lat, lon]
        const latlngs = segment.map(c => [c[1], c[0]]);

        // glow effect
        L.polyline(latlngs, {
            color: '#3dd68c',
            weight: 8,
            opacity: 0.15
        }).addTo(routeLayer);

        // main line
        L.polyline(latlngs, {
            color: '#3dd68c',
            weight: 3,
            opacity: 0.9
        }).addTo(routeLayer);
    });
}

//helper
function clearRoute() {
    if (routeLayer) {
        map.removeLayer(routeLayer);
        routeLayer = null;
    }
    routeStats.classList.remove('visible');
    conditionsPanel.classList.remove('visible');
}

//clear all button
clearBtn.addEventListener('click', () => {
    waypoints = [];
    waypointNames = [];
    markers.forEach(m => map.removeLayer(m));
    markers = [];
    clearRoute();
    renderWaypointList();
    setStatus('cleared');
});

// sidebar collapse
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebarToggle');

sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
    setTimeout(() => map.invalidateSize(), 300);
});

//status bar
function setStatus(msg, type = '') {
    statusBar.textContent = msg;
    statusBar.className = 'status-bar' + (type ? ` ${type}` : '');
}