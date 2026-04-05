#!/usr/bin/env python3
"""
NMEA-based vessel simulation server for Wabbit Eyes.
Uses Kafkar/NMEA_Simulator (vendored in nmea_simulator/) to generate realistic
NMEA sentences for 1000 shipping vessels travelling between major trade ports.

Replaces the original Node.js mock server with NMEA_Simulator-powered data.
Serves SSE at /stream, /classified and static files from docs/.
Optionally broadcasts vessel data over WebSocket (WS_PORT) and publishes to
NATS when NATS_URL is set.
"""

import os
import sys
import json
import math
import time
import random
import asyncio
import threading
<<<<<<< Updated upstream
from collections import deque
=======
import argparse
>>>>>>> Stashed changes
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add server directory to path for nmea_simulator imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nmea_simulator import GPRMC, VHW, TrackManager
from sea_routes import build_port_route_waypoints, get_shipping_lane_polylines

# --------------- Configuration ---------------
<<<<<<< Updated upstream
PORT = int(os.environ.get('PORT', 3000))
WS_PORT = int(os.environ.get('WS_PORT', 3001))
NATS_URL = os.environ.get('NATS_URL', '')   # e.g. "nats://localhost:4222"
=======
PORT = 3000
>>>>>>> Stashed changes
VESSEL_COUNT = 1000
EMIT_INTERVAL_MS = 200
# Time compression for simulation progress. 120 means 1 real second ~= 2 sim minutes.
TIME_SCALE = 120.0

# Route jitter in degrees. Keep small to avoid vessels drifting onto land.
LNG_OFFSET_MAX_DEG = 0.08
LAT_OFFSET_MAX_DEG = 0.04

# Keep simulated positions tightly snapped to route centerlines.
LANE_SNAP_FACTOR = 0.92
COASTAL_LANE_SNAP_FACTOR = 0.98
COASTAL_PROGRESS_BAND = 0.12

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


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_speed_ranges(raw_ranges):
    """Normalize speed range config into {type: (min, max)} mapping."""
    if not isinstance(raw_ranges, dict):
        return None

    normalized = {}
    for vessel_type, spec in raw_ranges.items():
        low = None
        high = None

        if isinstance(spec, dict):
            low = spec.get('min')
            high = spec.get('max')
        elif isinstance(spec, (list, tuple)) and len(spec) >= 2:
            low, high = spec[0], spec[1]

        low = _safe_float(low, None)
        high = _safe_float(high, None)
        if low is None or high is None:
            continue
        if high < low:
            low, high = high, low
        normalized[vessel_type] = (low, high)

    return normalized if normalized else None


def _normalize_ports(raw_ports):
    """Normalize trade ports into [{'name', 'lat', 'lon'}]."""
    if not isinstance(raw_ports, list):
        return None

    ports = []
    for idx, port in enumerate(raw_ports):
        if not isinstance(port, dict):
            continue
        lat = _safe_float(port.get('lat'), None)
        lon = port.get('lon', port.get('lng'))
        lon = _safe_float(lon, None)
        if lat is None or lon is None:
            continue

        name = port.get('name') or f"Port-{idx + 1}"
        ports.append({'name': str(name), 'lat': lat, 'lon': lon})

    return ports if len(ports) >= 2 else None


def apply_runtime_config(config_path=None):
    """
    Apply runtime configuration from JSON file and environment variables.

    Priority:
    1) Built-in defaults
    2) JSON config (if provided)
    3) Environment overrides
    """
    global PORT, VESSEL_COUNT, EMIT_INTERVAL_MS, TIME_SCALE
    global LNG_OFFSET_MAX_DEG, LAT_OFFSET_MAX_DEG
    global LANE_SNAP_FACTOR, COASTAL_LANE_SNAP_FACTOR, COASTAL_PROGRESS_BAND
    global TRADE_PORTS, VESSEL_TYPES, SPEED_RANGES

    if config_path:
        with open(config_path, 'r', encoding='utf-8') as f:
            loaded = json.load(f)

        if not isinstance(loaded, dict):
            raise ValueError('Config file root must be a JSON object')

        sim_cfg = loaded.get('simulation', {})
        if not isinstance(sim_cfg, dict):
            sim_cfg = {}

        # Scalars
        PORT = _safe_int(loaded.get('port', PORT), PORT)
        VESSEL_COUNT = _safe_int(
            sim_cfg.get('vessel_count', loaded.get('vessel_count', VESSEL_COUNT)),
            VESSEL_COUNT,
        )
        EMIT_INTERVAL_MS = _safe_int(
            sim_cfg.get('emit_interval_ms', loaded.get('emit_interval_ms', EMIT_INTERVAL_MS)),
            EMIT_INTERVAL_MS,
        )
        TIME_SCALE = _safe_float(
            sim_cfg.get('time_scale', loaded.get('time_scale', TIME_SCALE)),
            TIME_SCALE,
        )
        LNG_OFFSET_MAX_DEG = _safe_float(
            sim_cfg.get('lng_offset_max_deg', loaded.get('lng_offset_max_deg', LNG_OFFSET_MAX_DEG)),
            LNG_OFFSET_MAX_DEG,
        )
        LAT_OFFSET_MAX_DEG = _safe_float(
            sim_cfg.get('lat_offset_max_deg', loaded.get('lat_offset_max_deg', LAT_OFFSET_MAX_DEG)),
            LAT_OFFSET_MAX_DEG,
        )
        LANE_SNAP_FACTOR = _safe_float(
            sim_cfg.get('lane_snap_factor', loaded.get('lane_snap_factor', LANE_SNAP_FACTOR)),
            LANE_SNAP_FACTOR,
        )
        COASTAL_LANE_SNAP_FACTOR = _safe_float(
            sim_cfg.get(
                'coastal_lane_snap_factor',
                loaded.get('coastal_lane_snap_factor', COASTAL_LANE_SNAP_FACTOR),
            ),
            COASTAL_LANE_SNAP_FACTOR,
        )
        COASTAL_PROGRESS_BAND = _safe_float(
            sim_cfg.get('coastal_progress_band', loaded.get('coastal_progress_band', COASTAL_PROGRESS_BAND)),
            COASTAL_PROGRESS_BAND,
        )

        # Collection overrides
        ports = _normalize_ports(loaded.get('trade_ports'))
        if ports:
            TRADE_PORTS = ports

        vessel_types = loaded.get('vessel_types')
        if isinstance(vessel_types, list) and vessel_types:
            VESSEL_TYPES = [str(v) for v in vessel_types if str(v).strip()]

        speed_ranges = _normalize_speed_ranges(loaded.get('speed_ranges'))
        if speed_ranges:
            SPEED_RANGES = speed_ranges

    # Environment overrides for runtime operations
    PORT = _safe_int(os.environ.get('PORT', PORT), PORT)
    VESSEL_COUNT = max(1, _safe_int(os.environ.get('VESSEL_COUNT', VESSEL_COUNT), VESSEL_COUNT))
    EMIT_INTERVAL_MS = max(10, _safe_int(os.environ.get('EMIT_INTERVAL_MS', EMIT_INTERVAL_MS), EMIT_INTERVAL_MS))
    TIME_SCALE = max(0.1, _safe_float(os.environ.get('SIM_TIME_SCALE', TIME_SCALE), TIME_SCALE))
    LNG_OFFSET_MAX_DEG = max(0.0, _safe_float(os.environ.get('SIM_LNG_OFFSET_MAX_DEG', LNG_OFFSET_MAX_DEG), LNG_OFFSET_MAX_DEG))
    LAT_OFFSET_MAX_DEG = max(0.0, _safe_float(os.environ.get('SIM_LAT_OFFSET_MAX_DEG', LAT_OFFSET_MAX_DEG), LAT_OFFSET_MAX_DEG))
    LANE_SNAP_FACTOR = min(1.0, max(0.0, _safe_float(os.environ.get('SIM_LANE_SNAP_FACTOR', LANE_SNAP_FACTOR), LANE_SNAP_FACTOR)))
    COASTAL_LANE_SNAP_FACTOR = min(
        1.0,
        max(
            LANE_SNAP_FACTOR,
            _safe_float(
                os.environ.get('SIM_COASTAL_LANE_SNAP_FACTOR', COASTAL_LANE_SNAP_FACTOR),
                COASTAL_LANE_SNAP_FACTOR,
            ),
        ),
    )
    COASTAL_PROGRESS_BAND = min(
        0.45,
        max(0.0, _safe_float(os.environ.get('SIM_COASTAL_PROGRESS_BAND', COASTAL_PROGRESS_BAND), COASTAL_PROGRESS_BAND)),
    )

    # Keep vessel type list and speed ranges in sync
    VESSEL_TYPES = [t for t in VESSEL_TYPES if t in SPEED_RANGES]
    if not VESSEL_TYPES:
        raise ValueError('No valid vessel types available after configuration')

    # Ensure at least two ports for route generation
    if len(TRADE_PORTS) < 2:
        raise ValueError('Configuration must provide at least two trade ports')


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
    Simulates a single vessel travelling along sea-lane route segments
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

        # Generate sea-lane constrained waypoints for the route
        self.waypoints = build_port_route_waypoints(origin, destination, vessel_type=self.type)

        # Progress along the route (0..1), with random start position
        self.progress = random.random()
        self.reverse = random.random() > 0.5

        # Keep small offset from route centerline so traffic stays near lanes
        self.lng_offset = random.uniform(-LNG_OFFSET_MAX_DEG, LNG_OFFSET_MAX_DEG)
        self.lat_offset = random.uniform(-LAT_OFFSET_MAX_DEG, LAT_OFFSET_MAX_DEG)

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
        # Anomaly fields (set by AnomalyInjector)
        self.anomaly_type = None
        self.anomaly_confidence = 0.0
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

        near_coast = (
            self.progress <= COASTAL_PROGRESS_BAND or
            self.progress >= (1.0 - COASTAL_PROGRESS_BAND)
        )
        snap_factor = COASTAL_LANE_SNAP_FACTOR if near_coast else LANE_SNAP_FACTOR
        offset_scale = 1.0 - snap_factor

        self.latitude = lat + (self.lat_offset * offset_scale)
        self.longitude = lon + (self.lng_offset * offset_scale)

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
            'nmea': getattr(self, 'last_nmea', ''),
            'anomaly_type': self.anomaly_type,
            'anomaly_confidence': round(self.anomaly_confidence, 4),
        }


# --------------- Fleet Simulation Thread ---------------

class FleetSimulator:
    """Manages fleet simulation in a background thread."""

    def __init__(self, fleet):
        self.fleet = fleet
        self.running = False
        self.lock = threading.Lock()
        self.anomaly_injector = None
        self.ws_broadcaster = None
        self.nats_publisher = None

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
                if self.anomaly_injector:
                    self.anomaly_injector.tick()
            # Broadcast a batch every tick (WS + NATS are decoupled from SSE clients)
            if self.ws_broadcaster or self.nats_publisher:
                batch_size = 50 + random.randint(0, 50)
                batch_json = self.get_batch_json(batch_size)
                if self.ws_broadcaster:
                    self.ws_broadcaster.broadcast(batch_json)
                if self.nats_publisher:
                    self.nats_publisher.publish_batch(batch_json)
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


# --------------- Anomaly Injector ---------------

ANOMALY_TYPES = ['velocity_spike', 'heading_deviation', 'route_digression', 'stop']

ANOMALY_FIELDS = {
    'velocity_spike':    ['velocity'],
    'heading_deviation': ['direction'],
    'route_digression':  ['latitude', 'longitude'],
    'stop':              ['velocity'],
}


class AnomalyInjector:
    """
    Randomly injects anomaly state into fleet vessels and emits classification
    events into a thread-safe deque consumed by the /classified SSE endpoint.
    Runs in the same thread as the fleet tick (called from FleetSimulator._loop).
    """

    def __init__(self, fleet):
        self.fleet = fleet
        # Maps vessel id -> (anomaly_type, expiry_monotonic)
        self._active = {}
        self._next_inject = time.monotonic() + 5.0  # 5 s warmup
        # Classification event queue for the /classified SSE handler
        self.events = deque(maxlen=500)
        self._lock = threading.Lock()

    def tick(self):
        now = time.monotonic()

        # Expire old anomalies
        expired = [vid for vid, (_, exp) in self._active.items() if now >= exp]
        for vid in expired:
            vessel = next((v for v in self.fleet if v.id == vid), None)
            if vessel:
                vessel.anomaly_type = None
                vessel.anomaly_confidence = 0.0
                # Emit NORMAL classification event
                self._emit(vessel, 'NORMAL', 0.0, None, [])
            del self._active[vid]

        # Inject new anomalies periodically
        if now >= self._next_inject:
            self._next_inject = now + random.uniform(5.0, 15.0)
            count = random.randint(2, 5)
            candidates = [v for v in self.fleet if v.id not in self._active]
            if candidates:
                for vessel in random.sample(candidates, min(count, len(candidates))):
                    atype = random.choice(ANOMALY_TYPES)
                    duration = random.uniform(30.0, 90.0)
                    confidence = round(random.uniform(0.75, 0.99), 4)
                    vessel.anomaly_type = atype
                    vessel.anomaly_confidence = confidence
                    self._active[vessel.id] = (atype, now + duration)
                    self._emit(vessel, 'ANOMALY', confidence, atype, ANOMALY_FIELDS[atype])

    def _emit(self, vessel, classification, confidence, label, anomalous_fields):
        event = {
            'mmsi': vessel.mmsi,
            'id': vessel.id,
            'classification': classification,
            'confidence': confidence,
            'label': label,
            'anomalous_fields': anomalous_fields,
            'phase': 1,
            'timestamp': int(time.time() * 1000),
        }
        with self._lock:
            self.events.append(event)

    def pop_events(self):
        """Return and clear all pending classification events (thread-safe)."""
        with self._lock:
            batch = list(self.events)
            self.events.clear()
        return batch


# --------------- WebSocket Broadcaster ---------------

class WSBroadcaster:
    """
    Broadcasts vessel fleet data over WebSocket on WS_PORT.
    Runs an asyncio event loop in a dedicated daemon thread.
    """

    def __init__(self, fleet_simulator):
        self._fleet = fleet_simulator
        self._clients = set()
        self._loop = None
        self._enabled = False

    def start(self):
        try:
            import websockets  # noqa: F401
        except ImportError:
            print("   [WSBroadcaster] 'websockets' package not installed — WS disabled.")
            return
        self._enabled = True
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self):
        import websockets

        async def handler(ws):
            self._clients.add(ws)
            try:
                # Send initial full fleet
                data = json.dumps(self._fleet.get_all_json())
                await ws.send(data)
                await ws.wait_closed()
            finally:
                self._clients.discard(ws)

        print(f"   [WSBroadcaster] WebSocket server on ws://localhost:{WS_PORT}")
        async with websockets.serve(handler, '', WS_PORT):
            await asyncio.Future()  # run forever

    def broadcast(self, batch_json):
        """Called from the fleet tick thread to push a batch to all WS clients."""
        if not self._enabled or not self._loop or not self._clients:
            return
        payload = json.dumps(batch_json)
        clients = list(self._clients)

        async def _send_all():
            import websockets
            for ws in clients:
                try:
                    await ws.send(payload)
                except websockets.exceptions.ConnectionClosed:
                    self._clients.discard(ws)

        asyncio.run_coroutine_threadsafe(_send_all(), self._loop)


# --------------- NATS Publisher ---------------

class NATSPublisher:
    """
    Publishes vessel data to NATS when NATS_URL is configured.
    Activated only when the NATS_URL environment variable is set.
    Also subscribes to pattern.classified.> and forwards events to
    the supplied classification_callback.
    """

    def __init__(self, classification_callback=None):
        self._nc = None
        self._loop = None
        self._enabled = bool(NATS_URL)
        self._classification_callback = classification_callback

    def start(self):
        if not self._enabled:
            return
        try:
            import nats  # noqa: F401
        except ImportError:
            print("   [NATSPublisher] 'nats-py' package not installed — NATS disabled.")
            self._enabled = False
            return
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect())

    async def _connect(self):
        import nats
        try:
            self._nc = await nats.connect(NATS_URL)
            print(f"   [NATSPublisher] Connected to {NATS_URL}")
            if self._classification_callback:
                await self._nc.subscribe(
                    'pattern.classified.>',
                    cb=self._on_classified
                )
            await asyncio.Future()
        except Exception as exc:
            print(f"   [NATSPublisher] Connection failed: {exc} — NATS disabled.")
            self._enabled = False

    async def _on_classified(self, msg):
        try:
            event = json.loads(msg.data.decode())
            if self._classification_callback:
                self._classification_callback(event)
        except Exception:
            pass

    def publish_batch(self, batch_json):
        """Publish each vessel in the batch to pattern.monitor.vessel.{mmsi}."""
        if not self._enabled or not self._nc or not self._loop:
            return

        async def _pub():
            for vessel in batch_json:
                try:
                    subject = f"pattern.monitor.vessel.{vessel['mmsi']}"
                    await self._nc.publish(subject, json.dumps(vessel).encode())
                except Exception:
                    pass

        asyncio.run_coroutine_threadsafe(_pub(), self._loop)


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
<<<<<<< Updated upstream
# Global NATS classification event queue (populated by NATSPublisher callback)
_nats_classified_events = deque(maxlen=500)
_nats_classified_lock = threading.Lock()


def _nats_classification_callback(event):
    with _nats_classified_lock:
        _nats_classified_events.append(event)
=======
SHIPPING_LANES = get_shipping_lane_polylines()
>>>>>>> Stashed changes


class SSEHandler(BaseHTTPRequestHandler):
    """HTTP handler serving SSE stream, /classified SSE, and static files."""

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == '/stream':
            self._handle_stream()
<<<<<<< Updated upstream
        elif self.path == '/classified':
            self._handle_classified()
=======
        elif self.path == '/routes':
            self._handle_routes()
>>>>>>> Stashed changes
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

        if not simulator:
            return

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

<<<<<<< Updated upstream
    def _handle_classified(self):
        """
        SSE endpoint that streams classification events.
        In standalone mode (no NATS_URL): drains AnomalyInjector.events.
        When NATS_URL is set: drains the _nats_classified_events deque
        populated by NATSPublisher's subscription to pattern.classified.>.
        """
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self._cors_headers()
        self.end_headers()

        poll_interval = 0.1  # 100 ms polling
        try:
            if not simulator:
                return
            while True:
                if NATS_URL:
                    with _nats_classified_lock:
                        events = list(_nats_classified_events)
                        _nats_classified_events.clear()
                else:
                    events = (simulator.anomaly_injector.pop_events()
                              if simulator.anomaly_injector else [])
                for event in events:
                    data = json.dumps(event)
                    self.wfile.write(f"data: {data}\n\n".encode())
                self.wfile.flush()
                time.sleep(poll_interval)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
=======
    def _handle_routes(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._cors_headers()
        self.end_headers()
        payload = {
            'lanes': SHIPPING_LANES,
            'source': 'major-maritime-chokepoints',
        }
        self.wfile.write(json.dumps(payload).encode())
>>>>>>> Stashed changes

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

def main(argv=None):
    global simulator

    parser = argparse.ArgumentParser(description='Wabbit-Eyes NMEA server')
    parser.add_argument(
        '--config',
        dest='config_path',
        default=os.environ.get('NMEA_CONFIG_FILE'),
        help='Path to JSON config file',
    )
    args = parser.parse_args(argv)

    try:
        apply_runtime_config(args.config_path)
    except Exception as e:
        print(f"Configuration error: {e}")
        return 1

    print(f"🚢 Initializing {VESSEL_COUNT} vessels with NMEA Simulator...")
    fleet = [VesselSimulator(i) for i in range(VESSEL_COUNT)]
    print(f"   Fleet ready: {VESSEL_COUNT} vessels on routes between "
          f"{len(TRADE_PORTS)} major trade ports")

    simulator = FleetSimulator(fleet)

    # Wire anomaly injector (standalone classification source)
    simulator.anomaly_injector = AnomalyInjector(fleet)

    # Wire optional WebSocket broadcaster
    ws = WSBroadcaster(simulator)
    ws.start()
    simulator.ws_broadcaster = ws

    # Wire optional NATS publisher / classified subscriber
    nats_pub = NATSPublisher(classification_callback=_nats_classification_callback)
    nats_pub.start()
    simulator.nats_publisher = nats_pub

    simulator.start()

    server = HTTPServer(('', PORT), SSEHandler)
    server.daemon_threads = True

    print(f"🚢 Wabbit-Eyes NMEA server running at http://localhost:{PORT}")
    print(f"   Stream endpoint:     http://localhost:{PORT}/stream")
    print(f"   Classified endpoint: http://localhost:{PORT}/classified")
    print(f"   WebSocket endpoint:  ws://localhost:{WS_PORT}")
    print(f"   Serving UI from {DOCS_DIR}")
    if args.config_path:
        print(f"   Loaded config: {args.config_path}")
    print(f"   Tick interval: {EMIT_INTERVAL_MS} ms | Time scale: {TIME_SCALE}")
    print(f"   Powered by NMEA_Simulator (github.com/Kafkar/NMEA_Simulator)")
    if NATS_URL:
        print(f"   NATS: {NATS_URL}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        simulator.stop()
        server.server_close()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
