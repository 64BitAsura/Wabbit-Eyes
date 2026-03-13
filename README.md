# Wabbit Eyes 🐰👀

Real-time global vessel tracking visualization built with Three.js. Renders an abstract 2D Earth map with high-performance instanced rendering, streaming vessel data, and trail history — all at 60 FPS.

![Wabbit Eyes](https://img.shields.io/badge/Three.js-2D_Earth-00e5ff?style=flat-square)

## Features

- **Abstract 2D Earth** — Clean, high-tech Mercator-style projection with simplified coastlines and grid overlay
- **Real-time streaming** — Connects to an HTTP Server-Sent Events (SSE) stream for live vessel updates
- **High performance** — Instanced rendering for hundreds of vessels at 60 FPS with zero jank
- **Trail history** — Visual trail paths showing recent movement for each vessel
- **Interactive** — Pan, zoom, and hover tooltips showing vessel details
- **Mock server** — Built-in Node.js server generating realistic NMEA-like shipping data
- **GitHub Pages ready** — Client-side demo mode works without a server

## Quick Start

### Demo Mode (GitHub Pages)

Visit the [live demo](https://64BitAsura.github.io/Wabbit-Eyes/) — runs entirely in the browser with mock data.

### With Mock Server

```bash
# Clone the repository
git clone https://github.com/64BitAsura/Wabbit-Eyes.git
cd Wabbit-Eyes

# Start the mock streaming server
npm start

# Open http://localhost:3000 in your browser
```

The server:
- Serves the UI from `docs/`
- Streams vessel data at `http://localhost:3000/stream` via SSE
- Generates 120 vessels moving along major global shipping lanes

## Architecture

```
docs/              GitHub Pages root — static frontend
├── index.html     Main entry point
├── app.js         Three.js visualization & rendering
├── geo-data.js    Simplified world coastline data
├── mock-client.js Client-side mock data generator (for demo mode)
└── styles.css     UI overlay styling

server/
└── index.js       Node.js SSE streaming server with mock vessel data
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
| **Demo Mode checkbox** | Switch to client-side mock data |

## Technology

- **Three.js** — WebGL rendering with instanced meshes
- **Server-Sent Events** — Lightweight one-way streaming protocol
- **Node.js** — Zero-dependency mock data server