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

// Major shipping lanes – waypoints placed in open water, away from coastlines
const SHIPPING_LANES = [
  // Trans-Pacific (East China Sea → Japan → Mid-Pacific → offshore San Francisco)
  [{ lng: 123.0, lat: 30.0 }, { lng: 135.0, lat: 34.0 }, { lng: 155.0, lat: 38.0 }, { lng: 180.0, lat: 40.0 }, { lng: -160.0, lat: 43.0 }, { lng: -140.0, lat: 42.0 }, { lng: -124.0, lat: 37.5 }],
  // Trans-Atlantic (offshore Gibraltar → Mid-Atlantic → offshore New York)
  [{ lng: -6.0, lat: 36.0 }, { lng: -15.0, lat: 37.0 }, { lng: -30.0, lat: 38.0 }, { lng: -50.0, lat: 39.0 }, { lng: -65.0, lat: 40.0 }, { lng: -72.0, lat: 40.0 }],
  // Red Sea → Arabian Sea → Indian Ocean → Malacca Strait
  [{ lng: 36.0, lat: 25.0 }, { lng: 40.0, lat: 18.0 }, { lng: 43.5, lat: 12.5 }, { lng: 52.0, lat: 12.0 }, { lng: 65.0, lat: 12.0 }, { lng: 76.0, lat: 8.0 }, { lng: 80.5, lat: 5.0 }, { lng: 95.0, lat: 3.0 }, { lng: 103.5, lat: 1.5 }],
  // Mediterranean (offshore Portugal → Gibraltar → Balearic → Ligurian → Tyrrhenian Sea)
  [{ lng: -9.5, lat: 38.5 }, { lng: -6.0, lat: 36.5 }, { lng: 0.0, lat: 37.0 }, { lng: 5.0, lat: 39.0 }, { lng: 7.5, lat: 42.0 }, { lng: 13.5, lat: 40.0 }],
  // South America (offshore Rio → offshore Recife → Equatorial Atlantic)
  [{ lng: -41.5, lat: -24.0 }, { lng: -36.0, lat: -14.0 }, { lng: -33.0, lat: -8.0 }, { lng: -32.0, lat: -3.0 }, { lng: -40.0, lat: 1.0 }],
  // Cape of Good Hope (offshore Cape Town → Southern Ocean → Mozambique Channel)
  [{ lng: 16.5, lat: -35.0 }, { lng: 22.0, lat: -35.5 }, { lng: 30.0, lat: -32.0 }, { lng: 36.0, lat: -24.0 }, { lng: 40.0, lat: -16.0 }, { lng: 49.0, lat: -12.0 }],
  // Northern Europe (North Sea → Kattegat → Baltic Sea)
  [{ lng: 3.0, lat: 53.0 }, { lng: 6.0, lat: 55.5 }, { lng: 11.0, lat: 56.5 }, { lng: 16.0, lat: 58.0 }, { lng: 20.0, lat: 59.5 }],
  // East Asia coastal (Singapore Strait → South China Sea → East China Sea → Korea Strait)
  [{ lng: 104.5, lat: 1.0 }, { lng: 108.0, lat: 6.0 }, { lng: 112.0, lat: 14.0 }, { lng: 116.0, lat: 20.0 }, { lng: 121.0, lat: 26.0 }, { lng: 123.0, lat: 30.0 }, { lng: 128.0, lat: 34.0 }],
];

const VESSEL_TYPES = ['cargo', 'tanker', 'container', 'bulk_carrier', 'lng_carrier', 'roro', 'passenger'];

// Realistic speed ranges by vessel type (knots)
const SPEED_RANGES = {
  cargo:        { min: 12, max: 16 },
  tanker:       { min: 12, max: 16 },
  container:    { min: 16, max: 22 },
  bulk_carrier: { min: 11, max: 15 },
  lng_carrier:  { min: 16, max: 20 },
  roro:         { min: 15, max: 20 },
  passenger:    { min: 18, max: 24 },
};

// Normalize a longitude difference to [-180, 180] for date-line-safe calculations
function lngDiff(from, to) {
  let d = to - from;
  if (d > 180) d -= 360;
  if (d < -180) d += 360;
  return d;
}

function wrapLng(lng) {
  if (lng > 180) lng -= 360;
  if (lng < -180) lng += 360;
  return lng;
}

// Approximate length of a shipping lane in nautical miles
function calcLaneLengthNM(lane) {
  let total = 0;
  for (let i = 0; i < lane.length - 1; i++) {
    const a = lane[i], b = lane[i + 1];
    const dLat = (b.lat - a.lat) * 60;
    const avgLat = ((a.lat + b.lat) / 2) * Math.PI / 180;
    const dLng = lngDiff(a.lng, b.lng) * 60 * Math.cos(avgLat);
    total += Math.sqrt(dLng * dLng + dLat * dLat);
  }
  return total;
}

const LANE_LENGTHS = SHIPPING_LANES.map(calcLaneLengthNM);

// Simulation runs faster than real-time so vessels visibly traverse lanes
const TIME_SCALE = 3000;

class Vessel {
  constructor(id) {
    this.id = `VESSEL-${String(id).padStart(4, '0')}`;
    this.type = VESSEL_TYPES[Math.floor(Math.random() * VESSEL_TYPES.length)];
    this.mmsi = String(201000000 + Math.floor(Math.random() * 574999999));
    // Pick a random shipping lane
    this.laneIndex = Math.floor(Math.random() * SHIPPING_LANES.length);
    this.lane = SHIPPING_LANES[this.laneIndex];
    this.laneLengthNM = LANE_LENGTHS[this.laneIndex];
    // Progress along the lane (0..1)
    this.progress = Math.random();
    this.reverse = Math.random() > 0.5;
    // Small offset from the lane centerline (keeps vessels on water)
    this.lngOffset = (Math.random() - 0.5) * 1.0;
    this.latOffset = (Math.random() - 0.5) * 0.5;
    this.elevation = Math.random() * 5; // meters above sea level (hull height variation)
    // Set initial velocity based on vessel type (knots)
    const range = SPEED_RANGES[this.type];
    this.velocity = range.min + Math.random() * (range.max - range.min);
    this._updateSpeed();
    this._updatePosition();
  }

  // Convert velocity (knots) to progress-per-tick using lane length
  _updateSpeed() {
    this.speed = (this.velocity / 3600) * (EMIT_INTERVAL_MS / 1000) * TIME_SCALE / this.laneLengthNM;
  }

  _interpolateLane(progress) {
    const lane = this.lane;
    const totalSegments = lane.length - 1;
    const segFloat = progress * totalSegments;
    const segIndex = Math.min(Math.floor(segFloat), totalSegments - 1);
    const t = segFloat - segIndex;
    const a = lane[segIndex];
    const b = lane[segIndex + 1];
    const dLng = lngDiff(a.lng, b.lng);
    return {
      lng: wrapLng(a.lng + dLng * t),
      lat: a.lat + (b.lat - a.lat) * t,
      dirLng: dLng,
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
    // Gradually drift velocity (±0.2 knots per tick, clamped to type range)
    const range = SPEED_RANGES[this.type];
    this.velocity += (Math.random() - 0.5) * 0.4;
    this.velocity = Math.max(range.min, Math.min(range.max, this.velocity));
    this._updateSpeed();
    // Slight elevation variation
    this.elevation += (Math.random() - 0.5) * 0.2;
    this.elevation = Math.max(0, Math.min(20, this.elevation));
  }

  tick() {
    if (this.reverse) {
      this.progress -= this.speed;
      if (this.progress < 0) {
        this.progress = 0;
        this.reverse = false;
      }
    } else {
      this.progress += this.speed;
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
