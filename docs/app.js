/**
 * Wabbit Eyes — Main Application
 *
 * Three.js 2D abstract Earth visualization with high-performance
 * instanced rendering for vessel plotting and trail history.
 */

(function () {
  'use strict';

  // --------------- Configuration ---------------
  const MAX_VESSELS = 1000;
  const TRAIL_LENGTH = 40;          // points per trail
  const TRAIL_FADE_TIME = 30000;    // ms before oldest trail point fades
  const MAP_WIDTH = 360;
  const MAP_HEIGHT = 180;
  const PADDING = 20;

  // --------------- Color palette ---------------
  const COLORS = {
    bg: 0x0a0e17,
    grid: 0x131b2b,
    gridBright: 0x1c2740,
    coastline: 0x1e3a5f,
    coastlineBright: 0x2a5080,
    vessel: {
      cargo: new THREE.Color(0x00e5ff),
      tanker: new THREE.Color(0xff6d00),
      container: new THREE.Color(0x00e676),
      bulk_carrier: new THREE.Color(0xaa00ff),
      lng_carrier: new THREE.Color(0xffea00),
      roro: new THREE.Color(0xff1744),
      passenger: new THREE.Color(0xf50057),
      default: new THREE.Color(0x00e5ff),
    },
    trail: 0x00e5ff,
  };

  // --------------- DOM elements ---------------
  const canvas = document.getElementById('main-canvas');
  const fpsEl = document.getElementById('fps-counter');
  const vesselCountEl = document.getElementById('vessel-count');
  const streamStatusEl = document.getElementById('stream-status');
  const intelStatusEl = document.getElementById('intel-status');
  const classificationHudEl = document.getElementById('classification-hud');
  const hudNormalEl = document.getElementById('hud-normal');
  const hudAnomalyEl = document.getElementById('hud-anomaly');
  const hudWarmingEl = document.getElementById('hud-warming');
  const tooltipEl = document.getElementById('tooltip');
  const anomalyFeedEl = document.getElementById('anomaly-feed');
  const anomalyFeedListEl = document.getElementById('anomaly-feed-list');
  const toggleTrails = document.getElementById('toggle-trails');
  const toggleGrid = document.getElementById('toggle-grid');
  const toggleDemo = document.getElementById('toggle-demo');
  const toggleFeed = document.getElementById('toggle-feed');
  const toggleHeatmap = document.getElementById('toggle-heatmap');

  // --------------- Three.js setup ---------------
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(COLORS.bg);

  const scene = new THREE.Scene();

  // Orthographic camera for 2D view
  let camW, camH;
  function updateCameraSize() {
    const aspect = window.innerWidth / window.innerHeight;
    const viewH = MAP_HEIGHT + PADDING * 2;
    const viewW = viewH * aspect;
    camW = viewW;
    camH = viewH;
    return { viewW, viewH };
  }

  const { viewW, viewH } = updateCameraSize();
  const camera = new THREE.OrthographicCamera(-viewW / 2, viewW / 2, viewH / 2, -viewH / 2, 0.1, 100);
  camera.position.set(0, 0, 10);
  camera.lookAt(0, 0, 0);

  // --------------- Pan & Zoom ---------------
  let panOffset = { x: 0, y: 0 };
  let zoomLevel = 1;
  let isPanning = false;
  let panStart = { x: 0, y: 0 };

  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY > 0 ? 1.1 : 0.9;
    zoomLevel = Math.max(0.5, Math.min(5, zoomLevel * zoomFactor));
    updateCamera();
  }, { passive: false });

  canvas.addEventListener('mousedown', (e) => {
    if (e.button === 0) {
      isPanning = true;
      panStart = { x: e.clientX, y: e.clientY };
    }
  });

  canvas.addEventListener('mousemove', (e) => {
    if (isPanning) {
      const dx = (e.clientX - panStart.x) * (camW / zoomLevel) / window.innerWidth;
      const dy = -(e.clientY - panStart.y) * (camH / zoomLevel) / window.innerHeight;
      panOffset.x -= dx;
      panOffset.y -= dy;
      panStart = { x: e.clientX, y: e.clientY };
      updateCamera();
    }
    updateTooltip(e);
  });

  canvas.addEventListener('mouseup', () => { isPanning = false; });
  canvas.addEventListener('mouseleave', () => { isPanning = false; tooltipEl.classList.add('hidden'); });

  function updateCamera() {
    const { viewW: vw, viewH: vh } = updateCameraSize();
    const hw = (vw / 2) / zoomLevel;
    const hh = (vh / 2) / zoomLevel;
    camera.left = -hw + panOffset.x;
    camera.right = hw + panOffset.x;
    camera.top = hh + panOffset.y;
    camera.bottom = -hh + panOffset.y;
    camera.updateProjectionMatrix();
  }

  function onResize() {
    renderer.setSize(window.innerWidth, window.innerHeight);
    updateCamera();
  }
  window.addEventListener('resize', onResize);
  onResize();

  // --------------- Build Map Layers ---------------

  // Grid lines
  const gridGroup = new THREE.Group();
  scene.add(gridGroup);

  function buildGrid() {
    const gridMat = new THREE.LineBasicMaterial({ color: COLORS.grid, transparent: true, opacity: 0.4 });
    const gridBrightMat = new THREE.LineBasicMaterial({ color: COLORS.gridBright, transparent: true, opacity: 0.6 });

    // Longitude lines
    for (let lng = -180; lng <= 180; lng += 10) {
      const isMajor = lng % 30 === 0;
      const geo = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(lng, -90, 0),
        new THREE.Vector3(lng, 90, 0),
      ]);
      gridGroup.add(new THREE.Line(geo, isMajor ? gridBrightMat : gridMat));
    }
    // Latitude lines
    for (let lat = -90; lat <= 90; lat += 10) {
      const isMajor = lat % 30 === 0;
      const geo = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(-180, lat, 0),
        new THREE.Vector3(180, lat, 0),
      ]);
      gridGroup.add(new THREE.Line(geo, isMajor ? gridBrightMat : gridMat));
    }
    // Equator
    const eqGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(-180, 0, 0),
      new THREE.Vector3(180, 0, 0),
    ]);
    gridGroup.add(new THREE.Line(eqGeo, new THREE.LineBasicMaterial({ color: 0x2a4060, transparent: true, opacity: 0.8 })));
  }
  buildGrid();

  // Coastlines
  const coastGroup = new THREE.Group();
  scene.add(coastGroup);

  function buildCoastlines() {
    const mat = new THREE.LineBasicMaterial({ color: COLORS.coastlineBright, transparent: true, opacity: 0.7 });
    GeoData.coastlines.forEach(line => {
      const points = line.map(p => new THREE.Vector3(p[0], p[1], 0));
      const geo = new THREE.BufferGeometry().setFromPoints(points);
      coastGroup.add(new THREE.Line(geo, mat));
    });

    // Fill landmasses with subtle polygons
    const fillMat = new THREE.MeshBasicMaterial({ color: COLORS.coastline, transparent: true, opacity: 0.15, side: THREE.DoubleSide });
    GeoData.coastlines.forEach(line => {
      if (line.length < 4) return;
      const shape = new THREE.Shape();
      shape.moveTo(line[0][0], line[0][1]);
      for (let i = 1; i < line.length; i++) {
        shape.lineTo(line[i][0], line[i][1]);
      }
      shape.closePath();
      const geo = new THREE.ShapeGeometry(shape);
      coastGroup.add(new THREE.Mesh(geo, fillMat));
    });
  }
  buildCoastlines();

  // Map border
  const borderGeo = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(-180, -90, 0),
    new THREE.Vector3(180, -90, 0),
    new THREE.Vector3(180, 90, 0),
    new THREE.Vector3(-180, 90, 0),
    new THREE.Vector3(-180, -90, 0),
  ]);
  scene.add(new THREE.Line(borderGeo, new THREE.LineBasicMaterial({ color: COLORS.gridBright, transparent: true, opacity: 0.8 })));

  // --------------- Vessel Layer (Instanced) ---------------
  const vesselGeometry = new THREE.CircleGeometry(0.8, 8);
  const vesselMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.95 });
  const vesselMesh = new THREE.InstancedMesh(vesselGeometry, vesselMaterial, MAX_VESSELS);
  vesselMesh.count = 0;
  vesselMesh.frustumCulled = false;
  scene.add(vesselMesh);

  // Glow ring (slightly larger, dimmer)
  const glowGeometry = new THREE.RingGeometry(0.8, 1.6, 12);
  const glowMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.3 });
  const glowMesh = new THREE.InstancedMesh(glowGeometry, glowMaterial, MAX_VESSELS);
  glowMesh.count = 0;
  glowMesh.frustumCulled = false;
  scene.add(glowMesh);

  // Anomaly ring (pulsing, classification-colored)
  const anomalyRingGeometry = new THREE.RingGeometry(1.4, 2.8, 16);
  const anomalyRingMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.85 });
  const anomalyRingMesh = new THREE.InstancedMesh(anomalyRingGeometry, anomalyRingMaterial, MAX_VESSELS);
  anomalyRingMesh.count = 0;
  anomalyRingMesh.frustumCulled = false;
  scene.add(anomalyRingMesh);

  // Anomaly heatmap points
  const heatPositions = new Float32Array(MAX_VESSELS * 3);
  const heatColors = new Float32Array(MAX_VESSELS * 3);
  const heatGeo = new THREE.BufferGeometry();
  heatGeo.setAttribute('position', new THREE.BufferAttribute(heatPositions, 3));
  heatGeo.setAttribute('color', new THREE.BufferAttribute(heatColors, 3));
  const heatMat = new THREE.PointsMaterial({
    size: 4,
    vertexColors: true,
    transparent: true,
    opacity: 0.55,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: false,
  });
  const anomalyHeatMesh = new THREE.Points(heatGeo, heatMat);
  anomalyHeatMesh.frustumCulled = false;
  scene.add(anomalyHeatMesh);

  // --------------- Trail Layer ---------------
  const trailGroup = new THREE.Group();
  scene.add(trailGroup);

  // --------------- Data Store ---------------
  const vessels = new Map(); // id -> vessel data
  const trailLines = new Map(); // id -> { line, buffer, len }
  const mmsiToId = new Map(); // mmsi -> vessel id (for classification lookup)
  let trailsDirty = false; // only rebuild trails when new data arrives

  // Classification summary counts
  const classStats = { NORMAL: 0, ANOMALY: 0, WARMING: 0 };

  // Anomaly label colors (Three.js Color)
  const ANOMALY_COLORS = {
    velocity_spike:    new THREE.Color(0xe040fb),
    heading_deviation: new THREE.Color(0xff6d00),
    route_digression:  new THREE.Color(0xff1744),
    stop:              new THREE.Color(0xffca28),
    regime_change:     new THREE.Color(0xaa00ff),
  };
  const ANOMALY_COLOR_DEFAULT = new THREE.Color(0xe040fb);

  function getVesselColor(type) {
    return COLORS.vessel[type] || COLORS.vessel.default;
  }

  // --------------- Update vessels from incoming data ---------------
  function processData(batch) {
    const now = Date.now();
    batch.forEach(obj => {
      let existing = vessels.get(obj.id);
      if (!existing) {
        existing = {
          id: obj.id,
          type: obj.type || 'cargo',
          mmsi: obj.mmsi || '',
          trail: [],
          classification: null,
          confidence: 0,
          label: null,
          anomalousFields: [],
          classifiedAt: 0,
        };
        vessels.set(obj.id, existing);
        if (obj.mmsi) mmsiToId.set(obj.mmsi, obj.id);
      }
      existing.longitude = obj.longitude;
      existing.latitude = obj.latitude;
      existing.elevation = obj.elevation;
      existing.velocity = obj.velocity;
      existing.direction = obj.direction;
      existing.timestamp = obj.timestamp || now;

      // Add trail point
      existing.trail.push({ x: obj.longitude, y: obj.latitude, t: now });
      if (existing.trail.length > TRAIL_LENGTH) {
        existing.trail.shift();
      }
    });

    trailsDirty = true;
    vesselCountEl.textContent = `${vessels.size} vessels`;
  }

  // --------------- Classification events ---------------
  function processClassification(event) {
    const id = mmsiToId.get(event.mmsi);
    if (!id) return;
    const v = vessels.get(id);
    if (!v) return;

    const prev = v.classification;
    v.classification = event.classification;
    v.confidence = event.confidence || 0;
    v.label = event.label || null;
    v.anomalousFields = event.anomalous_fields || [];
    v.classifiedAt = Date.now();

    // Update stats
    if (prev && classStats[prev] !== undefined) classStats[prev]--;
    if (classStats[v.classification] !== undefined) classStats[v.classification]++;
    updateClassHUD();

    if (v.classification === 'ANOMALY') {
      addFeedEntry(v, event);
    }
  }

  function updateClassHUD() {
    const hasData = classStats.NORMAL + classStats.ANOMALY + classStats.WARMING > 0;
    if (hasData) classificationHudEl.classList.remove('hidden');
    hudNormalEl.textContent = classStats.NORMAL;
    hudAnomalyEl.textContent = classStats.ANOMALY;
    hudWarmingEl.textContent = classStats.WARMING;
  }

  // --------------- Anomaly Feed ---------------
  const MAX_FEED_ENTRIES = 20;

  function addFeedEntry(vessel, event) {
    const now = Date.now();
    const label = event.label || 'unknown';
    const conf = Math.round((event.confidence || 0) * 100);
    const fillW = Math.round((event.confidence || 0) * 36);

    const el = document.createElement('div');
    el.className = 'feed-entry';
    el.dataset.id = vessel.id;
    el.innerHTML =
      `<span class="feed-dot dot-${label}"></span>` +
      `<span class="feed-vessel-id">${vessel.id}</span>` +
      `<span class="label-chip chip-${label}">${label.replace(/_/g, ' ')}</span>` +
      `<span class="confidence-bar"><span class="confidence-fill" style="width:${fillW}px"></span></span>` +
      `<span class="feed-time" data-ts="${now}">0s ago</span>`;

    el.addEventListener('click', () => {
      const v = vessels.get(vessel.id);
      if (v) {
        panOffset.x = v.longitude;
        panOffset.y = v.latitude;
        zoomLevel = 2.5;
        updateCamera();
      }
    });

    anomalyFeedListEl.insertBefore(el, anomalyFeedListEl.firstChild);
    while (anomalyFeedListEl.children.length > MAX_FEED_ENTRIES) {
      anomalyFeedListEl.removeChild(anomalyFeedListEl.lastChild);
    }
  }

  // Update relative timestamps in feed every second
  setInterval(() => {
    const now = Date.now();
    anomalyFeedListEl.querySelectorAll('.feed-time').forEach(el => {
      const ts = parseInt(el.dataset.ts, 10);
      const secs = Math.floor((now - ts) / 1000);
      el.textContent = secs < 60 ? `${secs}s ago` : `${Math.floor(secs / 60)}m ago`;
    });
  }, 1000);

  // Toggle feed visibility
  if (toggleFeed) {
    toggleFeed.addEventListener('change', () => {
      if (toggleFeed.checked) {
        anomalyFeedEl.classList.remove('hidden');
      } else {
        anomalyFeedEl.classList.add('hidden');
      }
    });
    // Start visible (matches checked default)
    anomalyFeedEl.classList.remove('hidden');
  }

  // --------------- Render loop helpers ---------------
  const dummy = new THREE.Object3D();
  const tempColor = new THREE.Color();

  function updateInstancedMeshes() {
    let i = 0;
    let ri = 0;
    const now = performance.now();
    vessels.forEach(v => {
      if (i >= MAX_VESSELS) return;
      dummy.position.set(v.longitude, v.latitude, 1);
      dummy.updateMatrix();
      vesselMesh.setMatrixAt(i, dummy.matrix);
      glowMesh.setMatrixAt(i, dummy.matrix);

      const col = getVesselColor(v.type);
      vesselMesh.setColorAt(i, col);
      tempColor.copy(col).multiplyScalar(0.5);
      glowMesh.setColorAt(i, tempColor);
      i++;

      // Anomaly ring pass
      if (v.classification === 'ANOMALY' && ri < MAX_VESSELS) {
        const elapsed = now - (v.classifiedAt || 0);
        const scale = 0.85 + 0.25 * Math.sin(elapsed / 400);
        dummy.position.set(v.longitude, v.latitude, 1.5);
        dummy.scale.set(scale, scale, scale);
        dummy.updateMatrix();
        anomalyRingMesh.setMatrixAt(ri, dummy.matrix);
        const acol = ANOMALY_COLORS[v.label] || ANOMALY_COLOR_DEFAULT;
        anomalyRingMesh.setColorAt(ri, acol);
        ri++;
      }
    });
    // Reset dummy scale
    dummy.scale.set(1, 1, 1);
    vesselMesh.count = i;
    glowMesh.count = i;
    anomalyRingMesh.count = ri;
    vesselMesh.instanceMatrix.needsUpdate = true;
    glowMesh.instanceMatrix.needsUpdate = true;
    anomalyRingMesh.instanceMatrix.needsUpdate = true;
    if (vesselMesh.instanceColor) vesselMesh.instanceColor.needsUpdate = true;
    if (glowMesh.instanceColor) glowMesh.instanceColor.needsUpdate = true;
    if (anomalyRingMesh.instanceColor) anomalyRingMesh.instanceColor.needsUpdate = true;
  }

  function updateHeatmap() {
    const showHeatmap = toggleHeatmap && toggleHeatmap.checked;
    anomalyHeatMesh.visible = showHeatmap;
    if (!showHeatmap) return;

    const posAttr = heatGeo.getAttribute('position');
    const colAttr = heatGeo.getAttribute('color');
    const now = Date.now();
    const FADE_MS = 120000;
    let hi = 0;

    vessels.forEach(v => {
      if (v.classification !== 'ANOMALY' || hi >= MAX_VESSELS) return;
      const age = now - (v.classifiedAt || 0);
      if (age > FADE_MS) return;
      const alpha = 1 - age / FADE_MS;
      const acol = ANOMALY_COLORS[v.label] || ANOMALY_COLOR_DEFAULT;
      posAttr.setXYZ(hi, v.longitude, v.latitude, 2);
      colAttr.setXYZ(hi, acol.r * alpha, acol.g * alpha, acol.b * alpha);
      hi++;
    });
    heatGeo.setDrawRange(0, hi);
    posAttr.needsUpdate = true;
    colAttr.needsUpdate = true;
  }

  function updateTrails() {
    const showTrails = toggleTrails.checked;
    trailGroup.visible = showTrails;
    if (!showTrails || !trailsDirty) return;
    trailsDirty = false;

    vessels.forEach((v, id) => {
      if (v.trail.length < 2) {
        // Remove trail line if vessel has too few points
        const existing = trailLines.get(id);
        if (existing) {
          trailGroup.remove(existing.line);
          existing.line.geometry.dispose();
          existing.line.material.dispose();
          trailLines.delete(id);
        }
        return;
      }

      let entry = trailLines.get(id);

      if (entry) {
        // Update existing buffer in-place
        const posAttr = entry.line.geometry.getAttribute('position');
        const trail = v.trail;
        let i = 0;
        for (; i < trail.length; i++) {
          posAttr.setXYZ(i, trail[i].x, trail[i].y, 0.5);
        }
        entry.line.geometry.setDrawRange(0, i);
        posAttr.needsUpdate = true;
      } else {
        // Create new trail line with pre-allocated buffer
        const col = getVesselColor(v.type);
        const mat = new THREE.LineBasicMaterial({
          color: col,
          transparent: true,
          opacity: 0.4,
        });
        const positions = new Float32Array(TRAIL_LENGTH * 3);
        const trail = v.trail;
        for (let i = 0; i < trail.length; i++) {
          positions[i * 3] = trail[i].x;
          positions[i * 3 + 1] = trail[i].y;
          positions[i * 3 + 2] = 0.5;
        }
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geo.setDrawRange(0, trail.length);
        const line = new THREE.Line(geo, mat);
        trailGroup.add(line);
        trailLines.set(id, { line });
      }
    });

    // Clean up trails for removed vessels
    trailLines.forEach((entry, id) => {
      if (!vessels.has(id)) {
        trailGroup.remove(entry.line);
        entry.line.geometry.dispose();
        entry.line.material.dispose();
        trailLines.delete(id);
      }
    });
  }

  // --------------- Tooltip ---------------

  function updateTooltip(event) {
    // Convert screen to world coords
    const rect = canvas.getBoundingClientRect();
    const ndcX = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    const ndcY = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    // Map NDC to world
    const worldX = camera.left + (ndcX + 1) / 2 * (camera.right - camera.left);
    const worldY = camera.bottom + (ndcY + 1) / 2 * (camera.top - camera.bottom);

    // Find closest vessel
    let closest = null;
    let closestDist = Infinity;
    const threshold = 3 / zoomLevel;

    vessels.forEach(v => {
      const dx = v.longitude - worldX;
      const dy = v.latitude - worldY;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < threshold && dist < closestDist) {
        closestDist = dist;
        closest = v;
      }
    });

    if (closest) {
      tooltipEl.classList.remove('hidden');
      tooltipEl.style.left = (event.clientX + 15) + 'px';
      tooltipEl.style.top = (event.clientY - 10) + 'px';
      const latHemi = closest.latitude >= 0 ? 'N' : 'S';
      const lngHemi = closest.longitude >= 0 ? 'E' : 'W';
      let tip =
        `${closest.id}  [${closest.type.toUpperCase()}]\n` +
        `MMSI: ${closest.mmsi}\n` +
        `Pos:  ${Math.abs(closest.latitude).toFixed(4)}°${latHemi}  ${Math.abs(closest.longitude).toFixed(4)}°${lngHemi}\n` +
        `Vel:  ${closest.velocity.toFixed(1)} kn\n` +
        `Dir:  ${closest.direction.toFixed(1)}°\n` +
        `Elev: ${closest.elevation.toFixed(1)} m`;
      if (closest.classification) {
        tip +=
          `\n── INTEL ──────────────────\n` +
          `Status: ${closest.classification}  [${closest.confidence.toFixed(2)}]\n` +
          `Label:  ${closest.label || '—'}\n` +
          `Fields: ${(closest.anomalousFields || []).join(', ') || '—'}`;
      }
      tooltipEl.textContent = tip;
    } else {
      tooltipEl.classList.add('hidden');
    }
  }

  // --------------- FPS counter ---------------
  let frameCount = 0;
  let lastFpsTime = performance.now();

  function updateFPS() {
    frameCount++;
    const now = performance.now();
    if (now - lastFpsTime >= 1000) {
      const fps = Math.round(frameCount * 1000 / (now - lastFpsTime));
      fpsEl.textContent = `${fps} FPS`;
      frameCount = 0;
      lastFpsTime = now;
    }
  }

  // --------------- Animation loop ---------------
  function animate() {
    requestAnimationFrame(animate);
    updateInstancedMeshes();
    updateTrails();
    updateHeatmap();
    gridGroup.visible = toggleGrid.checked;
    renderer.render(scene, camera);
    updateFPS();
  }
  animate();

  // --------------- Streaming Connection ---------------
  let eventSource = null;
  let classifiedSource = null;
  let demoMode = false;

  function connectStream(url) {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }

    streamStatusEl.textContent = 'CONNECTING';
    streamStatusEl.className = 'disconnected';

    eventSource = new EventSource(url);

    eventSource.onopen = () => {
      streamStatusEl.textContent = 'LIVE';
      streamStatusEl.className = 'connected';
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        processData(Array.isArray(data) ? data : [data]);
      } catch (e) {
        // ignore parse errors
      }
    };

    eventSource.onerror = () => {
      streamStatusEl.textContent = 'OFFLINE';
      streamStatusEl.className = 'disconnected';
      // Auto-retry is built into EventSource, but fall back to demo mode after a while
      setTimeout(() => {
        if (eventSource && eventSource.readyState === EventSource.CLOSED) {
          startDemoMode();
        }
      }, 5000);
    };
  }

  function connectClassifiedStream(url) {
    if (classifiedSource) {
      classifiedSource.close();
      classifiedSource = null;
    }

    intelStatusEl.textContent = 'INTEL …';
    intelStatusEl.className = 'disconnected';

    classifiedSource = new EventSource(url);

    classifiedSource.onopen = () => {
      intelStatusEl.textContent = 'INTEL LIVE';
      intelStatusEl.className = 'connected';
    };

    classifiedSource.onmessage = (evt) => {
      try {
        const event = JSON.parse(evt.data);
        processClassification(event);
      } catch (e) {
        // ignore parse errors
      }
    };

    classifiedSource.onerror = () => {
      intelStatusEl.textContent = 'INTEL OFF';
      intelStatusEl.className = 'disconnected';
    };
  }

  function startDemoMode() {
    if (demoMode) return;
    demoMode = true;
    toggleDemo.checked = true;
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    if (classifiedSource) {
      classifiedSource.close();
      classifiedSource = null;
    }
    streamStatusEl.textContent = 'DEMO';
    streamStatusEl.className = 'connected';
    intelStatusEl.textContent = 'INTEL DEMO';
    intelStatusEl.className = 'connected';
    MockClient.start(
      (data) => { processData(data); },
      (event) => { processClassification(event); }
    );
  }

  function stopDemoMode() {
    demoMode = false;
    MockClient.stop();
    intelStatusEl.textContent = 'INTEL OFF';
    intelStatusEl.className = 'disconnected';
  }

  // Toggle demo mode
  toggleDemo.addEventListener('change', () => {
    if (toggleDemo.checked) {
      startDemoMode();
    } else {
      stopDemoMode();
      // Try to reconnect to server
      tryConnect();
    }
  });

  // Detect environment and connect
  function tryConnect() {
    // If served from GitHub Pages or file://, go straight to demo mode
    const isGitHubPages = window.location.hostname === 'github.io' ||
      window.location.hostname.endsWith('.github.io');
    const isFile = window.location.protocol === 'file:';

    if (isGitHubPages || isFile) {
      startDemoMode();
      return;
    }

    // Try connecting to same-origin /stream and /classified
    connectStream(`${window.location.origin}/stream`);
    connectClassifiedStream(`${window.location.origin}/classified`);
  }

  tryConnect();

})();
