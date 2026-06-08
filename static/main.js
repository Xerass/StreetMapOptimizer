//state holders
let waypoints = [];     // [[lon, lat], ...]
let markers = [];       // leaflet markerscd
let routeLayer = null;  // polyline layer group

// centered on Metro Manila
const map = L.map('map', {
    zoomControl: false
}).setView([13.1594, 123.7103], 13);

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
const statusBar = document.getElementById('statusBar');

//on click, add waypoint
map.on('click', function(e) {
    if (waypoints.length >= 8) {
        setStatus('Max 8 waypoints reached', 'error');
        return;
    }

    const lon = e.latlng.lng;
    const lat = e.latlng.lat;
    addWaypoint(lon, lat);
});

function createMarkerIcon(label) {
    return L.divIcon({
        className: '',
        html: `<div class="custom-marker"></div>
               <div class="custom-marker-label">${label}</div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7]
    });
}

function addWaypoint(lon, lat) {
    const idx = waypoints.length;
    waypoints.push([lon, lat]);

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

    waypointList.innerHTML = waypoints.map((wp, i) => `
        <div class="waypoint-item">
            <div class="waypoint-number">${i + 1}</div>
            <div class="waypoint-coords">${wp[1].toFixed(4)}, ${wp[0].toFixed(4)}</div>
            <button class="waypoint-remove" onclick="removeWaypoint(${i})">×</button>
        </div>
    `).join('');
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
                optimize: optimizeToggle.checked
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
}

//clear all button
clearBtn.addEventListener('click', () => {
    waypoints = [];
    markers.forEach(m => map.removeLayer(m));
    markers = [];
    clearRoute();
    renderWaypointList();
    setStatus('cleared');
});

//status bar
function setStatus(msg, type = '') {
    statusBar.textContent = msg;
    statusBar.className = 'status-bar' + (type ? ` ${type}` : '');
}