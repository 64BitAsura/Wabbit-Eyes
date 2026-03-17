/**
 * Node.js fallback server for Wabbit Eyes.
 * Simulates 1000 shipping vessels travelling between major trade ports
 * via great-circle routes. Streams data via Server-Sent Events (SSE).
 *
 * Primary server: server/nmea_server.py (uses NMEA_Simulator)
 * This file mirrors the same trade-port routing for environments without Python.
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 3000;
const VESSEL_COUNT = 1000;
const EMIT_INTERVAL_MS = 200; // 5 updates/sec

// --------------- Major Trade Ports ---------------
const TRADE_PORTS = [
  { name: 'Shanghai',        lat: 31.23,  lng: 121.47 },
  { name: 'Singapore',       lat:  1.26,  lng: 103.84 },
  { name: 'Rotterdam',       lat: 51.92,  lng:   4.48 },
  { name: 'Busan',           lat: 35.10,  lng: 129.04 },
  { name: 'Guangzhou',       lat: 23.12,  lng: 113.25 },
  { name: 'Qingdao',         lat: 36.07,  lng: 120.38 },
  { name: 'Hong Kong',       lat: 22.29,  lng: 114.17 },
  { name: 'Jebel Ali',       lat: 25.01,  lng:  55.06 },
  { name: 'Tianjin',         lat: 38.99,  lng: 117.73 },
  { name: 'Los Angeles',     lat: 33.74,  lng: -118.27 },
  { name: 'Hamburg',         lat: 53.55,  lng:   9.99 },
  { name: 'Antwerp',         lat: 51.26,  lng:   4.42 },
  { name: 'Port Klang',      lat:  3.00,  lng: 101.39 },
  { name: 'Kaohsiung',       lat: 22.62,  lng: 120.30 },
  { name: 'Xiamen',          lat: 24.47,  lng: 118.08 },
  { name: 'Dalian',          lat: 38.91,  lng: 121.60 },
  { name: 'New York',        lat: 40.68,  lng: -74.05 },
  { name: 'Tanjung Pelepas', lat:  1.36,  lng: 103.55 },
  { name: 'Laem Chabang',    lat: 13.09,  lng: 100.88 },
  { name: 'Tokyo',           lat: 35.65,  lng: 139.77 },
  { name: 'Felixstowe',      lat: 51.96,  lng:   1.30 },
  { name: 'Santos',          lat: -23.95, lng: -46.33 },
  { name: 'Colombo',         lat:  6.93,  lng:  79.85 },
  { name: 'Piraeus',         lat: 37.94,  lng:  23.64 },
  { name: 'Mumbai',          lat: 18.95,  lng:  72.84 },
  { name: 'Durban',          lat: -29.87, lng:  31.03 },
  { name: 'Cape Town',       lat: -33.92, lng:  18.42 },
  { name: 'Melbourne',       lat: -37.81, lng: 144.97 },
  { name: 'Yokohama',        lat: 35.44,  lng: 139.64 },
  { name: 'Savannah',        lat: 32.08,  lng: -81.09 },
];

const VESSEL_TYPES = ['cargo', 'tanker', 'container', 'bulk_carrier', 'lng_carrier', 'roro', 'passenger'];

const SPEED_RANGES = {
  cargo:        { min: 12, max: 16 },
  tanker:       { min: 12, max: 16 },
  container:    { min: 16, max: 22 },
  bulk_carrier: { min: 11, max: 15 },
  lng_carrier:  { min: 16, max: 20 },
  roro:         { min: 15, max: 20 },
  passenger:    { min: 18, max: 24 },
};

const TIME_SCALE = 3000;

// --------------- Great Circle Route Generation ---------------

function generateGreatCircleWaypoints(origin, dest, numPoints) {
  numPoints = numPoints || 50;
  const lat1 = origin.lat * Math.PI / 180;
  const lon1 = origin.lng * Math.PI / 180;
  const lat2 = dest.lat * Math.PI / 180;
  const lon2 = dest.lng * Math.PI / 180;

  const d = 2 * Math.asin(Math.sqrt(
    Math.pow(Math.sin((lat2 - lat1) / 2), 2) +
    Math.cos(lat1) * Math.cos(lat2) * Math.pow(Math.sin((lon2 - lon1) / 2), 2)
  ));

  if (d < 1e-10) {
    return [{ lat: origin.lat, lng: origin.lng }];
  }

  const waypoints = [];
  for (let i = 0; i < numPoints; i++) {
    const f = i / Math.max(numPoints - 1, 1);
    const a = Math.sin((1 - f) * d) / Math.sin(d);
    const b = Math.sin(f * d) / Math.sin(d);
    const x = a * Math.cos(lat1) * Math.cos(lon1) + b * Math.cos(lat2) * Math.cos(lon2);
    const y = a * Math.cos(lat1) * Math.sin(lon1) + b * Math.cos(lat2) * Math.sin(lon2);
    const z = a * Math.sin(lat1) + b * Math.sin(lat2);
    waypoints.push({
      lat: Math.atan2(z, Math.sqrt(x * x + y * y)) * 180 / Math.PI,
      lng: Math.atan2(y, x) * 180 / Math.PI,
    });
  }
  return waypoints;
}

// --------------- Helpers ---------------

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

function calcRouteLengthNM(waypoints) {
  let total = 0;
  for (let i = 0; i < waypoints.length - 1; i++) {
    const a = waypoints[i], b = waypoints[i + 1];
    const dLat = (b.lat - a.lat) * 60;
    const avgLat = ((a.lat + b.lat) / 2) * Math.PI / 180;
    const dLng = lngDiff(a.lng, b.lng) * 60 * Math.cos(avgLat);
    total += Math.sqrt(dLng * dLng + dLat * dLat);
  }
  return Math.max(total, 1);
}

// --------------- Vessel ---------------

class Vessel {
  constructor(id) {
    this.id = `VESSEL-${String(id).padStart(4, '0')}`;
    this.type = VESSEL_TYPES[Math.floor(Math.random() * VESSEL_TYPES.length)];
    this.mmsi = String(201000000 + Math.floor(Math.random() * 574999999));

    // Pick random origin and destination ports
    const originIdx = Math.floor(Math.random() * TRADE_PORTS.length);
    let destIdx = originIdx;
    while (destIdx === originIdx) {
      destIdx = Math.floor(Math.random() * TRADE_PORTS.length);
    }

    this.waypoints = generateGreatCircleWaypoints(TRADE_PORTS[originIdx], TRADE_PORTS[destIdx], 50);
    this.routeLengthNM = calcRouteLengthNM(this.waypoints);

    this.progress = Math.random();
    this.reverse = Math.random() > 0.5;
    this.lngOffset = (Math.random() - 0.5) * 1.0;
    this.latOffset = (Math.random() - 0.5) * 0.5;
    this.elevation = Math.random() * 5;

    const range = SPEED_RANGES[this.type];
    this.velocity = range.min + Math.random() * (range.max - range.min);
    this._updateSpeed();
    this._updatePosition();
  }

  _updateSpeed() {
    this.speed = (this.velocity / 3600) * (EMIT_INTERVAL_MS / 1000) * TIME_SCALE / this.routeLengthNM;
  }

  _interpolate(progress) {
    const wps = this.waypoints;
    const totalSegments = wps.length - 1;
    if (totalSegments < 1) return { lng: wps[0].lng, lat: wps[0].lat, dirLng: 0, dirLat: 0 };
    const segFloat = progress * totalSegments;
    const segIndex = Math.min(Math.floor(segFloat), totalSegments - 1);
    const t = segFloat - segIndex;
    const a = wps[segIndex];
    const b = wps[segIndex + 1];
    const dLng = lngDiff(a.lng, b.lng);
    return {
      lng: wrapLng(a.lng + dLng * t),
      lat: a.lat + (b.lat - a.lat) * t,
      dirLng: dLng,
      dirLat: b.lat - a.lat,
    };
  }

  _updatePosition() {
    const pos = this._interpolate(this.progress);
    this.longitude = pos.lng + this.lngOffset;
    this.latitude = pos.lat + this.latOffset;
    this.direction = (Math.atan2(pos.dirLng, pos.dirLat) * 180 / Math.PI + 360) % 360;
    if (this.reverse) this.direction = (this.direction + 180) % 360;

    const range = SPEED_RANGES[this.type];
    this.velocity += (Math.random() - 0.5) * 0.4;
    this.velocity = Math.max(range.min, Math.min(range.max, this.velocity));
    this._updateSpeed();

    this.elevation += (Math.random() - 0.5) * 0.2;
    this.elevation = Math.max(0, Math.min(20, this.elevation));
  }

  tick() {
    if (this.reverse) {
      this.progress -= this.speed;
      if (this.progress < 0) { this.progress = 0; this.reverse = false; }
    } else {
      this.progress += this.speed;
      if (this.progress > 1) { this.progress = 1; this.reverse = true; }
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
console.log(`🚢 Initializing ${VESSEL_COUNT} vessels...`);
const fleet = [];
for (let i = 0; i < VESSEL_COUNT; i++) {
  fleet.push(new Vessel(i));
}
console.log(`   Fleet ready: ${VESSEL_COUNT} vessels on routes between ${TRADE_PORTS.length} major trade ports`);

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
      fleet.forEach(v => v.tick());
      const batchSize = 50 + Math.floor(Math.random() * 50);
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
