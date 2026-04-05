"""Maritime trade-lane routing helpers for Wabbit-Eyes.

Defines major sea waypoints/chokepoints and builds vessel paths along
connected ocean corridors instead of direct great-circle cuts over land.
"""

import heapq
import math

SEA_NODES = {
    # Asia-Pacific
    'SINGAPORE_STRAIT': {'lon': 103.8, 'lat': 1.2},
    'MALACCA': {'lon': 99.8, 'lat': 4.5},
    'SOUTH_CHINA_SEA': {'lon': 114.0, 'lat': 15.0},
    'EAST_CHINA_SEA': {'lon': 124.0, 'lat': 30.0},
    'JAPAN_PACIFIC': {'lon': 142.0, 'lat': 35.0},
    'NORTH_PAC_W': {'lon': 170.0, 'lat': 40.0},
    'NORTH_PAC_E': {'lon': -140.0, 'lat': 38.0},
    'LA_APPROACH': {'lon': -122.0, 'lat': 33.5},

    # Panama / Atlantic
    'PANAMA_PAC': {'lon': -79.8, 'lat': 8.8},
    'PANAMA_ATL': {'lon': -79.6, 'lat': 9.5},
    'CARIBBEAN': {'lon': -75.0, 'lat': 16.0},
    'NORTH_ATL_W': {'lon': -50.0, 'lat': 40.0},
    'NORTH_ATL_E': {'lon': -10.0, 'lat': 48.0},
    'ENGLISH_CHANNEL': {'lon': -1.0, 'lat': 50.5},

    # Mediterranean / Suez / Indian Ocean
    'GIBRALTAR': {'lon': -5.6, 'lat': 36.0},
    'WEST_MED': {'lon': 5.0, 'lat': 38.0},
    'EAST_MED': {'lon': 26.0, 'lat': 34.0},
    'SUEZ': {'lon': 32.5, 'lat': 30.0},
    'RED_SEA_N': {'lon': 36.0, 'lat': 22.0},
    'BAB_EL_MANDEB': {'lon': 43.0, 'lat': 12.5},
    'ARABIAN_SEA': {'lon': 58.0, 'lat': 20.0},
    'INDIA_SOUTH': {'lon': 80.0, 'lat': 6.0},
    'BAY_OF_BENGAL': {'lon': 88.0, 'lat': 15.0},

    # Southern corridors
    'JAVA_SEA': {'lon': 108.0, 'lat': -6.0},
    'EAST_AFRICA': {'lon': 40.0, 'lat': -5.0},
    'SOUTH_EAST_AFRICA': {'lon': 36.0, 'lat': -22.0},
    'CAPE_OF_GOOD_HOPE': {'lon': 18.0, 'lat': -34.0},
    'SOUTH_ATL': {'lon': -5.0, 'lat': -25.0},
    'BRAZIL_OFFSHORE': {'lon': -40.0, 'lat': -23.0},
}

SEA_EDGES = [
    # Asia network
    ('SINGAPORE_STRAIT', 'MALACCA', 'strait'),
    ('SINGAPORE_STRAIT', 'SOUTH_CHINA_SEA', 'open_ocean'),
    ('SINGAPORE_STRAIT', 'JAVA_SEA', 'open_ocean'),
    ('MALACCA', 'BAY_OF_BENGAL', 'strait'),
    ('BAY_OF_BENGAL', 'INDIA_SOUTH', 'open_ocean'),
    ('INDIA_SOUTH', 'ARABIAN_SEA', 'open_ocean'),
    ('SOUTH_CHINA_SEA', 'EAST_CHINA_SEA', 'open_ocean'),
    ('EAST_CHINA_SEA', 'JAPAN_PACIFIC', 'open_ocean'),
    ('JAPAN_PACIFIC', 'NORTH_PAC_W', 'open_ocean'),
    ('NORTH_PAC_W', 'NORTH_PAC_E', 'open_ocean'),
    ('NORTH_PAC_E', 'LA_APPROACH', 'open_ocean'),

    # Panama + Atlantic
    ('LA_APPROACH', 'PANAMA_PAC', 'open_ocean'),
    ('PANAMA_PAC', 'PANAMA_ATL', 'canal'),
    ('PANAMA_ATL', 'CARIBBEAN', 'open_ocean'),
    ('CARIBBEAN', 'NORTH_ATL_W', 'open_ocean'),
    ('NORTH_ATL_W', 'NORTH_ATL_E', 'open_ocean'),
    ('NORTH_ATL_E', 'ENGLISH_CHANNEL', 'open_ocean'),

    # Med/Suez
    ('NORTH_ATL_E', 'GIBRALTAR', 'strait'),
    ('GIBRALTAR', 'WEST_MED', 'strait'),
    ('WEST_MED', 'EAST_MED', 'open_ocean'),
    ('EAST_MED', 'SUEZ', 'open_ocean'),
    ('SUEZ', 'RED_SEA_N', 'canal'),
    ('RED_SEA_N', 'BAB_EL_MANDEB', 'strait'),
    ('BAB_EL_MANDEB', 'ARABIAN_SEA', 'strait'),

    # Southern alternatives
    ('ARABIAN_SEA', 'EAST_AFRICA', 'open_ocean'),
    ('EAST_AFRICA', 'SOUTH_EAST_AFRICA', 'open_ocean'),
    ('SOUTH_EAST_AFRICA', 'CAPE_OF_GOOD_HOPE', 'cape_route'),
    ('CAPE_OF_GOOD_HOPE', 'SOUTH_ATL', 'cape_route'),
    ('SOUTH_ATL', 'NORTH_ATL_W', 'open_ocean'),
    ('SOUTH_ATL', 'BRAZIL_OFFSHORE', 'open_ocean'),
    ('BRAZIL_OFFSHORE', 'NORTH_ATL_W', 'open_ocean'),

    # Asia to Africa direct corridor
    ('JAVA_SEA', 'INDIA_SOUTH', 'open_ocean'),
    ('INDIA_SOUTH', 'EAST_AFRICA', 'open_ocean'),
]

VESSEL_ROUTE_PREFS = {
    'container': {'canal': 0.72, 'cape_route': 1.35, 'strait': 1.0, 'open_ocean': 1.0},
    'passenger': {'canal': 0.80, 'cape_route': 1.30, 'strait': 1.0, 'open_ocean': 1.0},
    'tanker': {'canal': 2.40, 'cape_route': 0.82, 'strait': 1.0, 'open_ocean': 1.0},
    'lng_carrier': {'canal': 2.10, 'cape_route': 0.86, 'strait': 1.0, 'open_ocean': 1.0},
    'bulk_carrier': {'canal': 1.90, 'cape_route': 0.90, 'strait': 1.0, 'open_ocean': 1.0},
    'cargo': {'canal': 1.00, 'cape_route': 1.00, 'strait': 1.0, 'open_ocean': 1.0},
    'roro': {'canal': 0.95, 'cape_route': 1.05, 'strait': 1.0, 'open_ocean': 1.0},
}


def _lng_diff(a, b):
    d = b - a
    if d > 180:
        d -= 360
    if d < -180:
        d += 360
    return d


def _wrap_lng(lng):
    if lng > 180:
        lng -= 360
    if lng < -180:
        lng += 360
    return lng


def _distance_nm(a, b):
    """Approximate nautical miles between two lon/lat points."""
    d_lat = (b['lat'] - a['lat']) * 60.0
    avg_lat = math.radians((a['lat'] + b['lat']) / 2.0)
    d_lng = _lng_diff(a['lon'], b['lon']) * 60.0 * math.cos(avg_lat)
    return math.sqrt(d_lat * d_lat + d_lng * d_lng)


def _interpolate_segment(a, b, step_nm=180.0):
    """Densify one segment using wrapped linear interpolation."""
    dist = max(_distance_nm(a, b), 1.0)
    n = max(2, int(math.ceil(dist / step_nm)) + 1)
    out = []
    d_lng = _lng_diff(a['lon'], b['lon'])

    for i in range(n):
        t = i / (n - 1)
        out.append({
            'lon': _wrap_lng(a['lon'] + d_lng * t),
            'lat': a['lat'] + (b['lat'] - a['lat']) * t,
            'elevation': 0.0,
            'timestamp': None,
        })
    return out


def _edge_multiplier(tag, vessel_type):
    profile = VESSEL_ROUTE_PREFS.get(vessel_type, VESSEL_ROUTE_PREFS['cargo'])
    return profile.get(tag, 1.0)


def _build_graph(vessel_type='cargo'):
    graph = {name: [] for name in SEA_NODES}
    for a, b, tag in SEA_EDGES:
        w = _distance_nm(SEA_NODES[a], SEA_NODES[b]) * _edge_multiplier(tag, vessel_type)
        graph[a].append((b, w))
        graph[b].append((a, w))
    return graph


def _nearest_node(port):
    best = None
    best_dist = float('inf')
    for name, node in SEA_NODES.items():
        d = _distance_nm(port, node)
        if d < best_dist:
            best_dist = d
            best = name
    return best


def _shortest_path(start, goal, graph):
    heap = [(0.0, start)]
    dist = {start: 0.0}
    prev = {}

    while heap:
        d, u = heapq.heappop(heap)
        if u == goal:
            break
        if d > dist.get(u, float('inf')):
            continue

        for v, w in graph.get(u, []):
            nd = d + w
            if nd < dist.get(v, float('inf')):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))

    if goal not in dist:
        return [start, goal]

    path = [goal]
    cur = goal
    while cur != start:
        cur = prev[cur]
        path.append(cur)
    path.reverse()
    return path


def build_port_route_waypoints(origin, destination, vessel_type='cargo'):
    """Build a route from origin to destination constrained to sea-lane graph."""
    direct_nm = _distance_nm(origin, destination)

    # Keep very short regional hops direct (coastal traffic).
    if direct_nm <= 700.0:
        return _interpolate_segment(origin, destination, step_nm=80.0)

    graph = _build_graph(vessel_type=vessel_type)
    start_node = _nearest_node(origin)
    end_node = _nearest_node(destination)
    node_path = _shortest_path(start_node, end_node, graph)

    anchors = [
        {'lon': origin['lon'], 'lat': origin['lat']},
    ]
    anchors.extend([SEA_NODES[n] for n in node_path])
    anchors.append({'lon': destination['lon'], 'lat': destination['lat']})

    # Remove direct duplicates
    compact = [anchors[0]]
    for p in anchors[1:]:
        q = compact[-1]
        if abs(_lng_diff(q['lon'], p['lon'])) < 1e-6 and abs(q['lat'] - p['lat']) < 1e-6:
            continue
        compact.append(p)

    waypoints = []
    for i in range(len(compact) - 1):
        seg = _interpolate_segment(compact[i], compact[i + 1], step_nm=140.0)
        if i > 0:
            seg = seg[1:]
        waypoints.extend(seg)

    return waypoints


def get_shipping_lane_polylines():
    """Return densified lane polylines for frontend overlay."""
    lines = []
    for a, b, _tag in SEA_EDGES:
        seg = _interpolate_segment(SEA_NODES[a], SEA_NODES[b], step_nm=220.0)
        lines.append(seg)
    return lines
