/**
 * Mock NMEA-like shipping data streaming server.
 * Generates realistic vessel objects with position, velocity, direction, and elevation.
 * Streams data via Server-Sent Events (SSE) at configurable rates.
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 3000;
const VESSEL_COUNT = 120;
const EMIT_INTERVAL_MS = 200; // 5 updates/sec

// Major shipping lanes (lng, lat pairs as waypoints)
const SHIPPING_LANES = [
  // Trans-Pacific
  [{ lng: 121.5, lat: 31.2 }, { lng: 140.0, lat: 35.0 }, { lng: 180.0, lat: 40.0 }, { lng: -150.0, lat: 45.0 }, { lng: -122.4, lat: 37.8 }],
  // Trans-Atlantic
  [{ lng: -5.0, lat: 36.0 }, { lng: -20.0, lat: 38.0 }, { lng: -40.0, lat: 38.0 }, { lng: -60.0, lat: 40.0 }, { lng: -74.0, lat: 40.7 }],
  // Suez to Asia
  [{ lng: 32.3, lat: 30.0 }, { lng: 43.0, lat: 12.5 }, { lng: 55.0, lat: 10.0 }, { lng: 73.0, lat: 10.0 }, { lng: 80.0, lat: 6.0 }, { lng: 103.8, lat: 1.3 }],
  // Europe coastal
  [{ lng: -9.0, lat: 38.7 }, { lng: -5.0, lat: 36.0 }, { lng: 3.0, lat: 43.0 }, { lng: 10.0, lat: 44.0 }, { lng: 15.0, lat: 42.0 }],
  // South America
  [{ lng: -43.2, lat: -22.9 }, { lng: -38.5, lat: -12.9 }, { lng: -34.8, lat: -8.0 }, { lng: -35.0, lat: 0.0 }, { lng: -50.0, lat: 5.0 }],
  // Cape of Good Hope
  [{ lng: 18.4, lat: -33.9 }, { lng: 25.0, lat: -34.0 }, { lng: 35.0, lat: -25.0 }, { lng: 40.0, lat: -15.0 }, { lng: 49.0, lat: -12.0 }],
  // Northern Europe
  [{ lng: 4.5, lat: 51.9 }, { lng: 8.0, lat: 54.0 }, { lng: 12.0, lat: 56.0 }, { lng: 18.0, lat: 59.0 }, { lng: 25.0, lat: 60.0 }],
  // East Asia coastal
  [{ lng: 103.8, lat: 1.3 }, { lng: 110.0, lat: 10.0 }, { lng: 114.2, lat: 22.3 }, { lng: 121.5, lat: 31.2 }, { lng: 129.0, lat: 35.0 }],
];

const VESSEL_TYPES = ['cargo', 'tanker', 'container', 'bulk_carrier', 'lng_carrier', 'roro', 'passenger'];

class Vessel {
  constructor(id) {
    this.id = `VESSEL-${String(id).padStart(4, '0')}`;
    this.type = VESSEL_TYPES[Math.floor(Math.random() * VESSEL_TYPES.length)];
    this.mmsi = String(201000000 + Math.floor(Math.random() * 574999999));
    // Pick a random shipping lane
    this.laneIndex = Math.floor(Math.random() * SHIPPING_LANES.length);
    this.lane = SHIPPING_LANES[this.laneIndex];
    // Progress along the lane (0..1)
    this.progress = Math.random();
    this.speed = 0.0002 + Math.random() * 0.0006; // progress units per tick
    this.reverse = Math.random() > 0.5;
    // Slight offset from the lane
    this.lngOffset = (Math.random() - 0.5) * 4;
    this.latOffset = (Math.random() - 0.5) * 2;
    this.elevation = Math.random() * 5; // meters above sea level (hull height variation)
    this._updatePosition();
  }

  _interpolateLane(progress) {
    const lane = this.lane;
    const totalSegments = lane.length - 1;
    const segFloat = progress * totalSegments;
    const segIndex = Math.min(Math.floor(segFloat), totalSegments - 1);
    const t = segFloat - segIndex;
    const a = lane[segIndex];
    const b = lane[segIndex + 1];
    return {
      lng: a.lng + (b.lng - a.lng) * t,
      lat: a.lat + (b.lat - a.lat) * t,
      dirLng: b.lng - a.lng,
      dirLat: b.lat - a.lat,
    };
  }

  _updatePosition() {
    const pos = this._interpolateLane(this.progress);
    this.longitude = pos.lng + this.lngOffset;
    this.latitude = pos.lat + this.latOffset;
    // Direction in degrees (bearing)
    this.direction = (Math.atan2(pos.dirLng, pos.dirLat) * 180 / Math.PI + 360) % 360;
    if (this.reverse) this.direction = (this.direction + 180) % 360;
    // Velocity in knots (10-25 knots typical)
    this.velocity = 10 + Math.random() * 15;
    // Slight elevation variation
    this.elevation += (Math.random() - 0.5) * 0.2;
    this.elevation = Math.max(0, Math.min(20, this.elevation));
  }

  tick() {
    if (this.reverse) {
      this.progress -= this.speed * (0.8 + Math.random() * 0.4);
      if (this.progress < 0) {
        this.progress = 0;
        this.reverse = false;
      }
    } else {
      this.progress += this.speed * (0.8 + Math.random() * 0.4);
      if (this.progress > 1) {
        this.progress = 1;
        this.reverse = true;
      }
    }
    this._updatePosition();
  }

  toJSON() {
    return {
      id: this.id,
      type: this.type,
      mmsi: this.mmsi,
      longitude: parseFloat(this.longitude.toFixed(6)),
      latitude: parseFloat(this.latitude.toFixed(6)),
      elevation: parseFloat(this.elevation.toFixed(2)),
      velocity: parseFloat(this.velocity.toFixed(2)),
      direction: parseFloat(this.direction.toFixed(2)),
      timestamp: Date.now(),
    };
  }
}

// Initialize fleet
const fleet = [];
for (let i = 0; i < VESSEL_COUNT; i++) {
  fleet.push(new Vessel(i));
}

// MIME types for static files
const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

const server = http.createServer((req, res) => {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // SSE stream endpoint
  if (req.url === '/stream') {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    });

    // Send initial batch
    const allData = fleet.map(v => v.toJSON());
    res.write(`data: ${JSON.stringify(allData)}\n\n`);

    const interval = setInterval(() => {
      // Tick all vessels
      fleet.forEach(v => v.tick());
      // Send a batch of updated vessels (random subset for realism)
      const batchSize = 10 + Math.floor(Math.random() * 30);
      const indices = new Set();
      while (indices.size < batchSize) {
        indices.add(Math.floor(Math.random() * fleet.length));
      }
      const batch = [...indices].map(i => fleet[i].toJSON());
      res.write(`data: ${JSON.stringify(batch)}\n\n`);
    }, EMIT_INTERVAL_MS);

    req.on('close', () => {
      clearInterval(interval);
    });
    return;
  }

  // Static file serving from docs/
  let filePath = req.url === '/' ? '/index.html' : req.url;
  filePath = path.join(__dirname, '..', 'docs', filePath);

  const ext = path.extname(filePath);
  const contentType = MIME_TYPES[ext] || 'application/octet-stream';

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not Found');
      return;
    }
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(data);
  });
});

server.listen(PORT, () => {
  console.log(`🚢 Wabbit-Eyes server running at http://localhost:${PORT}`);
  console.log(`   Stream endpoint: http://localhost:${PORT}/stream`);
  console.log(`   Serving UI from docs/`);
});
