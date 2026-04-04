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
- Streams live vessel data at `http://localhost:3000/stream` via SSE
- Simulates 1000 vessels travelling between 30 major trade ports via great-circle routes
- Generates authentic NMEA GPRMC sentences using [NMEA_Simulator](https://github.com/Kafkar/NMEA_Simulator)

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