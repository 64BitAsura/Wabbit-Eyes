# Wabbit Eyes 🐰👀

Real-time global vessel tracking visualization built with Three.js. Renders an abstract 2D Earth map with high-performance instanced rendering, streaming vessel data, and trail history — all at 60 FPS.

![Wabbit Eyes](https://img.shields.io/badge/Three.js-2D_Earth-00e5ff?style=flat-square)

## Features

- **Abstract 2D Earth** — Clean, high-tech Mercator-style projection with simplified coastlines and grid overlay
- **Real-time streaming** — Connects to an HTTP Server-Sent Events (SSE) stream for live vessel updates
- **High performance** — Instanced rendering for 1000 vessels at 60 FPS with zero jank
- **Trail history** — Visual trail paths showing recent movement for each vessel
- **Interactive** — Pan, zoom, and hover tooltips showing vessel details
- **NMEA simulation** — Python backend generates authentic NMEA sentences for 1000 vessels on real trade routes

## Quick Start

```bash
# Clone the repository
git clone https://github.com/64BitAsura/Wabbit-Eyes.git
cd Wabbit-Eyes

# Start the server (frontend + backend together)
npm start

# Open http://localhost:3000 in your browser
```

`npm start` runs the Python NMEA simulator server which:
- Serves the UI from `docs/`
<<<<<<< Updated upstream
- Streams live vessel data at `http://localhost:3000/stream` via SSE
- Simulates 1000 vessels travelling between 30 major trade ports via great-circle routes
- Generates authentic NMEA GPRMC sentences using [NMEA_Simulator](https://github.com/Kafkar/NMEA_Simulator)
=======
- Streams vessel data at `http://localhost:3000/stream` via SSE
- Exposes highlighted sea lanes at `http://localhost:3000/routes`
- Generates 120 vessels moving along major global shipping lanes
>>>>>>> Stashed changes

### JSON Config File (Python NMEA Server)

You can run the Python simulator with a JSON configuration file:

```bash
python3 server/nmea_server.py --config server/sim-config.json
```

Or with environment variable:

```bash
NMEA_CONFIG_FILE=server/sim-config.json npm start
```

Example config:

```json
{
  "port": 3000,
  "vessel_count": 600,
  "emit_interval_ms": 250,
  "time_scale": 120,
  "lng_offset_max_deg": 0.08,
  "lat_offset_max_deg": 0.04,
  "lane_snap_factor": 0.92,
  "coastal_lane_snap_factor": 0.98,
  "coastal_progress_band": 0.12,
  "vessel_types": ["cargo", "tanker", "container"],
  "speed_ranges": {
    "cargo": {"min": 10, "max": 14},
    "tanker": [11, 15],
    "container": {"min": 16, "max": 21}
  },
  "trade_ports": [
    {"name": "Singapore", "lat": 1.26, "lon": 103.84},
    {"name": "Shanghai", "lat": 31.23, "lon": 121.47},
    {"name": "Rotterdam", "lat": 51.92, "lon": 4.48}
  ]
}
```

Environment variables still work and override JSON values:
- `PORT`
- `VESSEL_COUNT`
- `EMIT_INTERVAL_MS`
- `SIM_TIME_SCALE`
- `SIM_LNG_OFFSET_MAX_DEG`
- `SIM_LAT_OFFSET_MAX_DEG`
- `SIM_LANE_SNAP_FACTOR`
- `SIM_COASTAL_LANE_SNAP_FACTOR`
- `SIM_COASTAL_PROGRESS_BAND`

## Architecture

```
docs/              Static frontend (served by the NMEA server)
├── index.html     Main entry point
├── app.js         Three.js visualization & rendering
├── geo-data.js    Simplified world coastline data
└── styles.css     UI overlay styling

server/
├── nmea_server.py          Python NMEA simulator server (primary)
├── index.js                Node.js fallback server
└── nmea_simulator/         Vendored NMEA_Simulator library
```

## Data Format

Each vessel object in the stream contains:

```json
{
  "id": "VESSEL-0042",
  "type": "container",
  "mmsi": "412345678",
  "longitude": 121.456789,
  "latitude": 31.234567,
  "elevation": 3.14,
  "velocity": 18.5,
  "direction": 127.3,
  "timestamp": 1710000000000
}
```

## Controls

| Control | Action |
|---------|--------|
| **Scroll wheel** | Zoom in/out |
| **Click + drag** | Pan the map |
| **Hover** | Show vessel details tooltip |
| **Trails checkbox** | Toggle vessel trail rendering |
| **Grid checkbox** | Toggle map grid |

## Technology

- **Three.js** — WebGL rendering with instanced meshes
- **Server-Sent Events** — Lightweight one-way streaming protocol
- **Python** — NMEA_Simulator-powered vessel simulation server