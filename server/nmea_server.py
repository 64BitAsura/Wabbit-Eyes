#!/usr/bin/env python3
"""
NMEA-based vessel simulation server for Wabbit Eyes.
Uses Kafkar/NMEA_Simulator (vendored in nmea_simulator/) to generate realistic
NMEA sentences for 1000 shipping vessels travelling between major trade ports.

Replaces the original Node.js mock server with NMEA_Simulator-powered data.
Serves SSE at /stream and static files from docs/.
"""

import os
import sys
import json
import math
import time
import heapq
import random
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add server directory to path for nmea_simulator imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nmea_simulator import GPRMC, VHW, TrackManager

# --------------- Configuration ---------------
PORT = int(os.environ.get('PORT', 3000))
VESSEL_COUNT = 1000
EMIT_INTERVAL_MS = 200
TIME_SCALE = 3000

# --------------- Major Trade Ports ---------------
TRADE_PORTS = [
    {"name": "Shanghai",        "lat": 31.23,  "lon": 121.47},
    {"name": "Singapore",       "lat":  1.26,  "lon": 103.84},
    {"name": "Rotterdam",       "lat": 51.92,  "lon":   4.48},
    {"name": "Busan",           "lat": 35.10,  "lon": 129.04},
    {"name": "Guangzhou",       "lat": 23.12,  "lon": 113.25},
    {"name": "Qingdao",         "lat": 36.07,  "lon": 120.38},
    {"name": "Hong Kong",       "lat": 22.29,  "lon": 114.17},
    {"name": "Jebel Ali",       "lat": 25.01,  "lon":  55.06},
    {"name": "Tianjin",         "lat": 38.99,  "lon": 117.73},
    {"name": "Los Angeles",     "lat": 33.74,  "lon": -118.27},
    {"name": "Hamburg",         "lat": 53.55,  "lon":   9.99},
    {"name": "Antwerp",         "lat": 51.26,  "lon":   4.42},
    {"name": "Port Klang",      "lat":  3.00,  "lon": 101.39},
    {"name": "Kaohsiung",       "lat": 22.62,  "lon": 120.30},
    {"name": "Xiamen",          "lat": 24.47,  "lon": 118.08},
    {"name": "Dalian",          "lat": 38.91,  "lon": 121.60},
    {"name": "New York",        "lat": 40.68,  "lon": -74.05},
    {"name": "Tanjung Pelepas", "lat":  1.36,  "lon": 103.55},
    {"name": "Laem Chabang",    "lat": 13.09,  "lon": 100.88},
    {"name": "Tokyo",           "lat": 35.65,  "lon": 139.77},
    {"name": "Felixstowe",      "lat": 51.96,  "lon":   1.30},
    {"name": "Santos",          "lat": -23.95, "lon": -46.33},
    {"name": "Colombo",         "lat":  6.93,  "lon":  79.85},
    {"name": "Piraeus",         "lat": 37.94,  "lon":  23.64},
    {"name": "Mumbai",          "lat": 18.95,  "lon":  72.84},
    {"name": "Durban",          "lat": -29.87, "lon":  31.03},
    {"name": "Cape Town",       "lat": -33.92, "lon":  18.42},
    {"name": "Melbourne",       "lat": -37.81, "lon": 144.97},
    {"name": "Yokohama",        "lat": 35.44,  "lon": 139.64},
    {"name": "Savannah",        "lat": 32.08,  "lon": -81.09},
]

VESSEL_TYPES = [
    'cargo', 'tanker', 'container', 'bulk_carrier',
    'lng_carrier', 'roro', 'passenger'
]

SPEED_RANGES = {
    'cargo':        (12, 16),
    'tanker':       (12, 16),
    'container':    (16, 22),
    'bulk_carrier': (11, 15),
    'lng_carrier':  (16, 20),
    'roro':         (15, 20),
    'passenger':    (18, 24),
}


# --------------- Maritime Routing ---------------
# Ocean routing waypoints: major chokepoints and open-sea nodes used to
# constrain vessel routes to water-only paths.

MARITIME_WAYPOINTS = {
    # Atlantic Ocean
    'atl_n':     {'lat': 45.0,  'lon': -30.0},   # North Atlantic
    'atl_s':     {'lat': -20.0, 'lon': -22.0},   # South Atlantic
    # Mediterranean & approaches
    'gibraltar': {'lat': 36.0,  'lon':  -5.3},   # Strait of Gibraltar
    'med_w':     {'lat': 38.0,  'lon':   5.0},   # Western Mediterranean
    'med_e':     {'lat': 33.5,  'lon':  25.0},   # Eastern Mediterranean
    # Red Sea / Arabian Sea
    'suez_n':    {'lat': 31.2,  'lon':  32.3},   # Suez Canal (north)
    'suez_s':    {'lat': 12.6,  'lon':  43.5},   # Bab-el-Mandeb
    'hormuz':    {'lat': 26.3,  'lon':  57.0},   # Strait of Hormuz
    # Indian Ocean
    'ind_nw':    {'lat': 10.0,  'lon':  62.0},   # NW Indian Ocean
    'ind_sw':    {'lat': -15.0, 'lon':  65.0},   # SW Indian Ocean
    'ind_se':    {'lat': -20.0, 'lon':  88.0},   # SE Indian Ocean
    's_afr_e':   {'lat': -26.0, 'lon':  43.0},   # East of South Africa
    'c_gh':      {'lat': -34.8, 'lon':  17.5},   # Cape of Good Hope
    # South-East Asia
    'malacca':   {'lat':  3.5,  'lon': 101.0},   # Strait of Malacca
    'se_asia':   {'lat': 10.0,  'lon': 112.0},   # South China Sea
    # East Asia / North-West Pacific
    'e_china':   {'lat': 28.0,  'lon': 124.0},   # East China Sea
    'pac_nw':    {'lat': 35.0,  'lon': 152.0},   # NW Pacific
    # Pacific Ocean
    'pac_n':     {'lat': 40.0,  'lon': 175.0},   # North Pacific (near date line)
    'pac_ne':    {'lat': 35.0,  'lon':-145.0},   # NE Pacific
    'pac_sw':    {'lat': -30.0, 'lon': 175.0},   # SW Pacific
    'pac_se':    {'lat': -30.0, 'lon':-130.0},   # SE Pacific
    # Americas
    'panama_a':  {'lat':  9.3,  'lon': -79.9},   # Panama Canal (Atlantic side)
    'panama_p':  {'lat':  8.8,  'lon': -79.5},   # Panama Canal (Pacific side)
    'c_horn':    {'lat': -56.0, 'lon': -65.0},   # Cape Horn
}

# Bidirectional ocean-safe edges between waypoints.
# Each pair is a straight-line ocean segment that does not cross land.
WAYPOINT_EDGES = [
    # North Atlantic
    ('atl_n',    'gibraltar'),
    ('atl_n',    'atl_s'),
    ('atl_n',    'panama_a'),
    # South Atlantic
    ('atl_s',    'panama_a'),
    ('atl_s',    'c_gh'),
    ('atl_s',    'c_horn'),
    # Mediterranean
    ('gibraltar', 'med_w'),
    ('med_w',    'med_e'),
    ('med_e',    'suez_n'),
    # Red Sea / Arabian Sea
    ('suez_n',   'suez_s'),
    ('suez_s',   'ind_nw'),
    ('suez_s',   'hormuz'),
    ('hormuz',   'ind_nw'),
    # Indian Ocean
    ('ind_nw',   'ind_sw'),
    ('ind_nw',   'ind_se'),
    ('ind_sw',   'ind_se'),
    ('ind_sw',   's_afr_e'),
    ('ind_sw',   'c_gh'),
    ('ind_se',   'malacca'),
    ('ind_se',   'pac_sw'),
    ('s_afr_e',  'c_gh'),
    # South-East Asia
    ('malacca',  'se_asia'),
    ('se_asia',  'e_china'),
    ('se_asia',  'pac_sw'),
    # East Asia / NW Pacific
    ('e_china',  'pac_nw'),
    # Pacific
    ('pac_nw',   'pac_n'),
    ('pac_nw',   'pac_sw'),
    ('pac_n',    'pac_ne'),
    ('pac_n',    'pac_sw'),
    ('pac_ne',   'panama_p'),
    ('pac_sw',   'pac_se'),
    ('pac_se',   'panama_p'),
    ('pac_se',   'c_horn'),
    # Panama Canal
    ('panama_a', 'panama_p'),
]

# Maps each trade port to its ocean-entry waypoint(s).
# Multiple entries mean the port can enter the routing graph via any of them;
# Dijkstra picks the cheapest combination automatically.
PORT_OCEAN_ACCESS = {
    'Shanghai':        ['e_china'],
    'Singapore':       ['malacca', 'se_asia'],
    'Rotterdam':       ['atl_n'],
    'Busan':           ['e_china', 'pac_nw'],
    'Guangzhou':       ['se_asia'],
    'Qingdao':         ['e_china'],
    'Hong Kong':       ['se_asia'],
    'Jebel Ali':       ['hormuz'],
    'Tianjin':         ['e_china'],
    'Los Angeles':     ['pac_ne'],
    'Hamburg':         ['atl_n'],
    'Antwerp':         ['atl_n'],
    'Port Klang':      ['malacca'],
    'Kaohsiung':       ['se_asia'],
    'Xiamen':          ['se_asia'],
    'Dalian':          ['e_china'],
    'New York':        ['atl_n'],
    'Tanjung Pelepas': ['malacca'],
    'Laem Chabang':    ['se_asia'],
    'Tokyo':           ['pac_nw'],
    'Felixstowe':      ['atl_n'],
    'Santos':          ['atl_s'],
    'Colombo':         ['ind_nw'],
    'Piraeus':         ['med_e'],
    'Mumbai':          ['ind_nw'],
    'Durban':          ['s_afr_e'],
    'Cape Town':       ['c_gh'],
    'Melbourne':       ['ind_se', 'pac_sw'],
    'Yokohama':        ['pac_nw'],
    'Savannah':        ['atl_n'],
}


def _haversine_rad(lat1, lon1, lat2, lon2):
    """Haversine angular distance in radians between two lat/lon pairs."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    # Clamp to [0, 1] to guard against floating-point values slightly outside the domain of asin
    return 2 * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _find_maritime_waypoint_path(origin_name, dest_name):
    """Return the list of intermediate MARITIME_WAYPOINTS dicts on the
    shortest ocean-safe path between two named trade ports.

    Uses Dijkstra on WAYPOINT_EDGES weighted by great-circle distance.
    Virtual SRC/DST nodes connect to each port's ocean-entry waypoints with
    zero cost so multiple access points are handled automatically.
    Returns an empty list when either port is unknown (caller falls back to
    the direct great-circle route).
    """
    src_wps = PORT_OCEAN_ACCESS.get(origin_name, [])
    dst_wps = PORT_OCEAN_ACCESS.get(dest_name, [])
    if not src_wps or not dst_wps:
        return []

    # Build local adjacency list (fresh each call; small graph, fast enough)
    adj = {}
    for a, b in WAYPOINT_EDGES:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)

    SRC, DST = '__src__', '__dst__'
    adj[SRC] = list(src_wps)
    for w in dst_wps:
        adj.setdefault(w, []).append(DST)

    def edge_cost(a, b):
        if a == SRC or b == DST:
            return 0.0
        wa, wb = MARITIME_WAYPOINTS[a], MARITIME_WAYPOINTS[b]
        return _haversine_rad(wa['lat'], wa['lon'], wb['lat'], wb['lon'])

    heap = [(0.0, SRC, [SRC])]
    visited = set()
    while heap:
        cost, node, path = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        if node == DST:
            inner = [n for n in path if n not in (SRC, DST)]
            return [MARITIME_WAYPOINTS[n] for n in inner]
        for nb in adj.get(node, []):
            if nb not in visited:
                heapq.heappush(heap, (cost + edge_cost(node, nb), nb, path + [nb]))

    return []


def _gc_segment(lat1, lon1, lat2, lon2, n_points):
    """Generate n_points evenly spaced along the great circle from
    (lat1, lon1) to (lat2, lon2).  Returns a list of waypoint dicts."""
    lat1r, lon1r = math.radians(lat1), math.radians(lon1)
    lat2r, lon2r = math.radians(lat2), math.radians(lon2)
    d = _haversine_rad(lat1, lon1, lat2, lon2)
    if d < 1e-10:
        return [{'lat': lat1, 'lon': lon1, 'elevation': 0.0, 'timestamp': None}] * max(n_points, 1)
    pts = []
    for i in range(n_points):
        f = i / max(n_points - 1, 1)
        a = math.sin((1 - f) * d) / math.sin(d)
        b = math.sin(f * d) / math.sin(d)
        x = a * math.cos(lat1r) * math.cos(lon1r) + b * math.cos(lat2r) * math.cos(lon2r)
        y = a * math.cos(lat1r) * math.sin(lon1r) + b * math.cos(lat2r) * math.sin(lon2r)
        z = a * math.sin(lat1r) + b * math.sin(lat2r)
        lat = math.degrees(math.atan2(z, math.sqrt(x * x + y * y)))
        lon = math.degrees(math.atan2(y, x))
        pts.append({'lat': lat, 'lon': lon, 'elevation': 0.0, 'timestamp': None})
    return pts


def generate_maritime_route(origin, destination, num_points=50):
    """Generate waypoints along an ocean-only route between two trade ports.

    Finds the shortest path through MARITIME_WAYPOINTS (ocean chokepoints and
    open-sea nodes) via Dijkstra, then distributes num_points across the
    resulting multi-segment great-circle path proportionally by segment length.
    Falls back to a direct great-circle route for unknown ports.
    """
    via_wps = _find_maritime_waypoint_path(origin['name'], destination['name'])

    nodes = (
        [{'lat': origin['lat'],      'lon': origin['lon']}]
        + via_wps
        + [{'lat': destination['lat'], 'lon': destination['lon']}]
    )

    if len(nodes) < 2:
        return generate_great_circle_waypoints(origin, destination, num_points)

    # Compute per-segment great-circle distances (in radians)
    seg_dists = [
        _haversine_rad(nodes[i]['lat'], nodes[i]['lon'],
                       nodes[i + 1]['lat'], nodes[i + 1]['lon'])
        for i in range(len(nodes) - 1)
    ]
    total_dist = sum(seg_dists) or 1.0

    # Distribute num_points proportionally; guarantee at least 2 per segment
    budgets = [max(2, round(num_points * d / total_dist)) for d in seg_dists]

    all_points = []
    for i, (a, b) in enumerate(zip(nodes[:-1], nodes[1:])):
        seg = _gc_segment(a['lat'], a['lon'], b['lat'], b['lon'], budgets[i])
        # Drop the first point of every segment after the first to avoid duplicates
        if all_points:
            seg = seg[1:]
        all_points.extend(seg)

    return all_points if all_points else generate_great_circle_waypoints(origin, destination, num_points)


# --------------- Great Circle Route Generation ---------------

def generate_great_circle_waypoints(origin, destination, num_points=50):
    """Generate waypoints along a great circle route between two ports."""
    lat1 = math.radians(origin['lat'])
    lon1 = math.radians(origin['lon'])
    lat2 = math.radians(destination['lat'])
    lon2 = math.radians(destination['lon'])

    # Angular distance (Haversine)
    d = 2 * math.asin(math.sqrt(
        math.sin((lat2 - lat1) / 2) ** 2 +
        math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    ))

    if d < 1e-10:
        return [{'lat': origin['lat'], 'lon': origin['lon'],
                 'elevation': 0.0, 'timestamp': None}]

    waypoints = []
    for i in range(num_points):
        f = i / max(num_points - 1, 1)
        a = math.sin((1 - f) * d) / math.sin(d)
        b = math.sin(f * d) / math.sin(d)
        x = a * math.cos(lat1) * math.cos(lon1) + b * math.cos(lat2) * math.cos(lon2)
        y = a * math.cos(lat1) * math.sin(lon1) + b * math.cos(lat2) * math.sin(lon2)
        z = a * math.sin(lat1) + b * math.sin(lat2)
        lat = math.degrees(math.atan2(z, math.sqrt(x * x + y * y)))
        lon = math.degrees(math.atan2(y, x))
        waypoints.append({
            'lat': lat, 'lon': lon,
            'elevation': 0.0, 'timestamp': None
        })

    return waypoints


# --------------- NMEA Parsing ---------------

def _nmea_to_decimal(nmea_str, direction):
    """Convert NMEA coordinate string to decimal degrees."""
    if not nmea_str:
        return 0.0
    if direction in ('N', 'S'):
        degrees = int(nmea_str[:2])
        minutes = float(nmea_str[2:])
    else:
        degrees = int(nmea_str[:3])
        minutes = float(nmea_str[3:])
    decimal = degrees + minutes / 60.0
    if direction in ('S', 'W'):
        decimal = -decimal
    return decimal


def parse_gprmc(sentence):
    """Parse a GPRMC NMEA sentence and extract position, speed, course."""
    body = sentence.strip().split('*')[0]
    if body.startswith('$'):
        body = body[1:]
    fields = body.split(',')
    lat = _nmea_to_decimal(fields[3], fields[4]) if len(fields) > 4 else 0.0
    lon = _nmea_to_decimal(fields[5], fields[6]) if len(fields) > 6 else 0.0
    speed = float(fields[7]) if len(fields) > 7 and fields[7] else 0.0
    course = float(fields[8]) if len(fields) > 8 and fields[8] else 0.0
    return {'lat': lat, 'lon': lon, 'speed': speed, 'course': course}


# --------------- Longitude helpers ---------------

def _lng_diff(from_lng, to_lng):
    """Normalize longitude difference to [-180, 180]."""
    d = to_lng - from_lng
    if d > 180:
        d -= 360
    if d < -180:
        d += 360
    return d


def _wrap_lng(lng):
    """Wrap longitude to [-180, 180]."""
    if lng > 180:
        lng -= 360
    if lng < -180:
        lng += 360
    return lng


def _calc_route_length_nm(waypoints):
    """Calculate approximate route length in nautical miles."""
    total = 0.0
    for i in range(len(waypoints) - 1):
        a = waypoints[i]
        b = waypoints[i + 1]
        d_lat = (b['lat'] - a['lat']) * 60
        avg_lat = math.radians((a['lat'] + b['lat']) / 2)
        d_lng = _lng_diff(a['lon'], b['lon']) * 60 * math.cos(avg_lat)
        total += math.sqrt(d_lat * d_lat + d_lng * d_lng)
    return max(total, 1.0)


# --------------- Vessel Simulator ---------------

class VesselSimulator:
    """
    Simulates a single vessel travelling along a great-circle route
    between two trade ports, using NMEA_Simulator's GPRMC generator
    to produce NMEA sentences for position data.
    """

    def __init__(self, vessel_id):
        self.id = f"VESSEL-{vessel_id:04d}"
        self.type = random.choice(VESSEL_TYPES)
        self.mmsi = str(201000000 + random.randint(0, 574999999))

        # Pick random origin and destination ports
        origin_idx = random.randint(0, len(TRADE_PORTS) - 1)
        dest_idx = origin_idx
        while dest_idx == origin_idx:
            dest_idx = random.randint(0, len(TRADE_PORTS) - 1)
        origin = TRADE_PORTS[origin_idx]
        destination = TRADE_PORTS[dest_idx]

        # Generate ocean-routed waypoints (via maritime chokepoints) for the route
        self.waypoints = generate_maritime_route(origin, destination, 50)

        # Progress along the route (0..1), with random start position
        self.progress = random.random()
        self.reverse = random.random() > 0.5

        # Small offset from the route centerline
        self.lng_offset = (random.random() - 0.5) * 1.0
        self.lat_offset = (random.random() - 0.5) * 0.5

        # Route length for speed calculation
        self.route_length_nm = _calc_route_length_nm(self.waypoints)

        # Velocity based on vessel type
        speed_min, speed_max = SPEED_RANGES[self.type]
        self.velocity = random.uniform(speed_min, speed_max)
        self.elevation = random.uniform(0, 5)

        # NMEA sentence generators (from NMEA_Simulator)
        self.gprmc = GPRMC()
        self.vhw = VHW()
        self.vhw.set_base_speed(self.velocity)

        # Initialize position
        self.latitude = 0.0
        self.longitude = 0.0
        self.direction = 0.0
        self._update_speed()
        self._update_position()

    def _update_speed(self):
        """Convert knots to progress-per-tick."""
        self.speed_per_tick = (
            (self.velocity / 3600) *
            (EMIT_INTERVAL_MS / 1000) *
            TIME_SCALE /
            self.route_length_nm
        )

    def _interpolate(self, progress):
        """Interpolate position along the route waypoints."""
        total_segments = len(self.waypoints) - 1
        if total_segments < 1:
            wp = self.waypoints[0]
            return wp['lat'], wp['lon'], 0, 0
        seg_float = progress * total_segments
        seg_index = min(int(seg_float), total_segments - 1)
        t = seg_float - seg_index
        a = self.waypoints[seg_index]
        b = self.waypoints[seg_index + 1]
        d_lng = _lng_diff(a['lon'], b['lon'])
        lat = a['lat'] + (b['lat'] - a['lat']) * t
        lon = _wrap_lng(a['lon'] + d_lng * t)
        return lat, lon, d_lng, b['lat'] - a['lat']

    def _update_position(self):
        """Update latitude, longitude, direction from current progress."""
        lat, lon, d_lng, d_lat = self._interpolate(self.progress)
        self.latitude = lat + self.lat_offset
        self.longitude = lon + self.lng_offset

        direction = math.degrees(math.atan2(d_lng, d_lat))
        self.direction = (direction + 360) % 360
        if self.reverse:
            self.direction = (self.direction + 180) % 360

        # Velocity drift
        speed_min, speed_max = SPEED_RANGES[self.type]
        self.velocity += random.uniform(-0.2, 0.2)
        self.velocity = max(speed_min, min(speed_max, self.velocity))
        self._update_speed()

        # Elevation variation
        self.elevation += random.uniform(-0.1, 0.1)
        self.elevation = max(0, min(20, self.elevation))

    def tick(self):
        """Advance vessel one tick along its route."""
        if self.reverse:
            self.progress -= self.speed_per_tick
            if self.progress < 0:
                self.progress = 0
                self.reverse = False
        else:
            self.progress += self.speed_per_tick
            if self.progress > 1:
                self.progress = 1
                self.reverse = True

        self._update_position()

        # Generate NMEA GPRMC sentence via NMEA_Simulator
        now = datetime.now(timezone.utc)
        nmea_sentence = self.gprmc.generate(
            timestamp=now,
            latitude=self.latitude,
            longitude=self.longitude,
            speed=self.velocity,
            course=self.direction
        )

        # Parse the NMEA sentence back to validate through NMEA format
        parsed = parse_gprmc(nmea_sentence)
        self.latitude = parsed['lat']
        self.longitude = parsed['lon']

        # Store last NMEA sentence for optional diagnostics
        self.last_nmea = nmea_sentence.strip()

    def to_json(self):
        """Return vessel state as a JSON-serializable dict."""
        return {
            'id': self.id,
            'type': self.type,
            'mmsi': self.mmsi,
            'longitude': round(self.longitude, 6),
            'latitude': round(self.latitude, 6),
            'elevation': round(self.elevation, 2),
            'velocity': round(self.velocity, 2),
            'direction': round(self.direction, 2),
            'timestamp': int(time.time() * 1000),
        }


# --------------- Fleet Simulation Thread ---------------

class FleetSimulator:
    """Manages fleet simulation in a background thread."""

    def __init__(self, fleet):
        self.fleet = fleet
        self.running = False
        self.lock = threading.Lock()

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._loop, daemon=True)
        thread.start()

    def _loop(self):
        interval = EMIT_INTERVAL_MS / 1000.0
        while self.running:
            with self.lock:
                for v in self.fleet:
                    v.tick()
            time.sleep(interval)

    def get_all_json(self):
        with self.lock:
            return [v.to_json() for v in self.fleet]

    def get_batch_json(self, size):
        with self.lock:
            batch = random.sample(self.fleet, min(size, len(self.fleet)))
            return [v.to_json() for v in batch]

    def stop(self):
        self.running = False


# --------------- HTTP / SSE Server ---------------

DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'docs')
DOCS_DIR = os.path.realpath(DOCS_DIR)

MIME_TYPES = {
    '.html': 'text/html',
    '.js':   'text/javascript',
    '.css':  'text/css',
    '.json': 'application/json',
    '.png':  'image/png',
    '.svg':  'image/svg+xml',
    '.ico':  'image/x-icon',
}

# Global fleet simulator (set in main)
simulator = None


class SSEHandler(BaseHTTPRequestHandler):
    """HTTP handler serving SSE stream and static files."""

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == '/stream':
            self._handle_stream()
        else:
            self._serve_static()

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _handle_stream(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self._cors_headers()
        self.end_headers()

        try:
            # Initial batch – all vessels
            data = json.dumps(simulator.get_all_json())
            self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.flush()

            # Periodic updates
            interval = EMIT_INTERVAL_MS / 1000.0
            while True:
                time.sleep(interval)
                batch_size = 50 + random.randint(0, 50)
                data = json.dumps(simulator.get_batch_json(batch_size))
                self.wfile.write(f"data: {data}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    def _serve_static(self):
        file_path = self.path if self.path != '/' else '/index.html'
        # Prevent path traversal
        full_path = os.path.realpath(os.path.join(DOCS_DIR, file_path.lstrip('/')))
        if not full_path.startswith(DOCS_DIR):
            self.send_error(403)
            return
        if not os.path.isfile(full_path):
            self.send_error(404)
            return

        ext = os.path.splitext(full_path)[1]
        content_type = MIME_TYPES.get(ext, 'application/octet-stream')

        with open(full_path, 'rb') as f:
            content = f.read()

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self._cors_headers()
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        # Only log errors, suppress routine request logs
        if args and str(args[0]).startswith('4') or str(args[0]).startswith('5'):
            super().log_message(format, *args)


# --------------- Main ---------------

def main():
    global simulator

    print(f"🚢 Initializing {VESSEL_COUNT} vessels with NMEA Simulator...")
    fleet = [VesselSimulator(i) for i in range(VESSEL_COUNT)]
    print(f"   Fleet ready: {VESSEL_COUNT} vessels on routes between "
          f"{len(TRADE_PORTS)} major trade ports")

    simulator = FleetSimulator(fleet)
    simulator.start()

    server = HTTPServer(('', PORT), SSEHandler)
    server.daemon_threads = True

    print(f"🚢 Wabbit-Eyes NMEA server running at http://localhost:{PORT}")
    print(f"   Stream endpoint: http://localhost:{PORT}/stream")
    print(f"   Serving UI from {DOCS_DIR}")
    print(f"   Powered by NMEA_Simulator (github.com/Kafkar/NMEA_Simulator)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        simulator.stop()
        server.server_close()


if __name__ == '__main__':
    main()
