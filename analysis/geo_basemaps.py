"""
Basemaps for the portfolio maps -> data/geo.js  (window.DATA_GEO)

Two maps, one projection routine (spherical Lambert azimuthal equal-area, each map centred on
its own area, so Hawaii, Alaska and American Samoa sit in their true positions; no insets):

  pacific  every airport Alaska (AS) or Hawaiian (HA) served in the 2024 BTS data, over land
           (Natural Earth 50m via world-atlas, clipped to the frame), US interior state borders
           and international borders as lines.
  west     the states that hold the fleet-project cities plus their western neighbours, one
           named path per state (Natural Earth via us-atlas 10m), and x,y for each fleet city.

TopoJSON is decoded here (delta-decoded quantized arcs + transform). Shared borders are simplified
once per arc (Douglas-Peucker in screen pixels) so neighbouring states still meet exactly.
Path strings use relative SVG commands with 0.1 px precision.

Usage
  python -I analysis/geo_basemaps.py <countries-50m.json> <states-10m.json> <data/airline_real.js>
                                     <city_hotspots.csv> <out data/geo.js>
"""
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

COUNTRIES, STATES, AIRLINE_JS, HOTSPOTS, OUT = (Path(a) for a in sys.argv[1:6])


# ---------------------------------------------------------------- TopoJSON
def decode_arcs(topo):
    """Quantized, delta-encoded arcs -> list of (n,2) arrays of lon/lat."""
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    out = []
    for arc in topo["arcs"]:
        a = np.cumsum(np.asarray(arc, dtype=float), axis=0)
        out.append(np.column_stack([a[:, 0] * sx + tx, a[:, 1] * sy + ty]))
    return out


def polygons(geom):
    """Geometry -> list of polygons, each a list of rings, each a list of arc indices."""
    if geom["type"] == "Polygon":
        return [geom["arcs"]]
    if geom["type"] == "MultiPolygon":
        return geom["arcs"]
    return []


def ring_points(ring, arcs):
    """Arc indices (negative = reversed, ~i) -> one (n,2) array; drops repeated joints."""
    parts = []
    for k, i in enumerate(ring):
        p = arcs[i] if i >= 0 else arcs[~i][::-1]
        parts.append(p if k == 0 else p[1:])
    return np.vstack(parts)


# ---------------------------------------------------------------- projection
class LAEA:
    """Spherical Lambert azimuthal equal-area, then a scale/offset into a pixel frame.
    JS equivalent (all angles in radians, R = 1):
      k = sqrt(2 / (1 + sin(p0)sin(p) + cos(p0)cos(p)cos(l - l0)))
      x = k cos(p) sin(l - l0);  y = k (cos(p0)sin(p) - sin(p0)cos(p)cos(l - l0))
      X = (x - x0) * s;          Y = (y0 - y) * s
    """

    def __init__(self, lon0, lat0):
        self.l0, self.p0 = math.radians(lon0), math.radians(lat0)
        self.x0 = self.y0 = 0.0
        self.s = 1.0

    def raw(self, lonlat):
        ll = np.radians(np.asarray(lonlat, dtype=float).reshape(-1, 2))
        lam, phi = ll[:, 0] - self.l0, ll[:, 1]
        c = 1 + math.sin(self.p0) * np.sin(phi) + math.cos(self.p0) * np.cos(phi) * np.cos(lam)
        k = np.sqrt(2 / np.maximum(c, 1e-12))
        x = k * np.cos(phi) * np.sin(lam)
        y = k * (math.cos(self.p0) * np.sin(phi) - math.sin(self.p0) * np.cos(phi) * np.cos(lam))
        return np.column_stack([x, y])

    def fit(self, lonlat_points, width, pad):
        """Choose scale/offset so the points fill `width` px with `pad` px margins."""
        p = self.raw(lonlat_points)
        (xmin, ymin), (xmax, ymax) = p.min(0), p.max(0)
        self.s = (width - 2 * pad) / (xmax - xmin)
        self.x0, self.y0 = xmin - pad / self.s, ymax + pad / self.s
        self.height = (ymax - ymin) * self.s + 2 * pad
        return self

    def __call__(self, lonlat):
        p = self.raw(lonlat)
        return np.column_stack([(p[:, 0] - self.x0) * self.s, (self.y0 - p[:, 1]) * self.s])

    def params(self):
        return {"type": "laea", "lon0": round(math.degrees(self.l0), 4), "lat0": round(math.degrees(self.p0), 4),
                "x0": round(self.x0, 6), "y0": round(self.y0, 6), "s": round(self.s, 4)}


def angular_dist(lonlat, lon0, lat0):
    ll = np.radians(lonlat)
    l0, p0 = math.radians(lon0), math.radians(lat0)
    c = math.sin(p0) * np.sin(ll[:, 1]) + math.cos(p0) * np.cos(ll[:, 1]) * np.cos(ll[:, 0] - l0)
    return np.degrees(np.arccos(np.clip(c, -1, 1)))


def densify(p, step=0.5):
    """Insert points so no lon/lat segment is longer than `step` degrees (straight parallels
    such as the 49th must curve in an azimuthal projection). Longitudes are unwrapped first:
    a ring stepping from +179.9 to -179.9 would otherwise be filled in the long way round the
    globe (the projection is periodic in longitude, so unwrapped values are fine)."""
    p = np.column_stack([np.degrees(np.unwrap(np.radians(p[:, 0]))), p[:, 1]])
    out = [p[:1]]
    for a, b in zip(p[:-1], p[1:]):
        n = int(np.ceil(np.abs(b - a).max() / step))
        if n > 1:
            t = np.linspace(0, 1, n + 1)[1:, None]
            out.append(a + (b - a) * t)
        else:
            out.append(b[None])
    return np.vstack(out)


# ---------------------------------------------------------------- geometry ops (pixel space)
def clip_ring(p, x0, y0, x1, y1):
    """Sutherland-Hodgman clip of a closed ring (n,2) to a rectangle."""
    pts = [tuple(q) for q in p]
    for axis, val, keep_ge in ((0, x0, True), (0, x1, False), (1, y0, True), (1, y1, False)):
        if not pts:
            break
        res = []
        prev = pts[-1]
        for cur in pts:
            cin = cur[axis] >= val if keep_ge else cur[axis] <= val
            pin = prev[axis] >= val if keep_ge else prev[axis] <= val
            if cin != pin:
                t = (val - prev[axis]) / (cur[axis] - prev[axis])
                res.append((prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1])))
            if cin:
                res.append(cur)
            prev = cur
        pts = res
    return np.asarray(pts) if len(pts) >= 3 else None


def clip_line(p, x0, y0, x1, y1):
    """Split an open polyline into the runs that fall inside the rectangle (vertex test,
    with the crossing segment kept so lines reach the frame)."""
    inside = (p[:, 0] >= x0) & (p[:, 0] <= x1) & (p[:, 1] >= y0) & (p[:, 1] <= y1)
    runs, cur = [], []
    for i in range(len(p)):
        if inside[i] or (i > 0 and inside[i - 1]) or (i + 1 < len(p) and inside[i + 1]):
            cur.append(p[i])
        elif cur:
            runs.append(np.asarray(cur))
            cur = []
    if cur:
        runs.append(np.asarray(cur))
    return [r for r in runs if len(r) >= 2]


def dp(p, eps):
    """Douglas-Peucker on an open polyline (first and last points kept)."""
    n = len(p)
    if n < 3:
        return p
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = p[i], p[j]
        seg = b - a
        L = math.hypot(*seg)
        q = p[i + 1:j] - a
        d = np.abs(seg[0] * q[:, 1] - seg[1] * q[:, 0]) / L if L > 0 else np.hypot(q[:, 0], q[:, 1])
        k = int(np.argmax(d))
        if d[k] > eps:
            m = i + 1 + k
            keep[m] = True
            stack += [(i, m), (m, j)]
    return p[keep]


def dp_ring(p, eps):
    """Douglas-Peucker on a closed ring: split at the point farthest from the first one."""
    if len(p) < 4:
        return p
    if np.allclose(p[0], p[-1]):
        p = p[:-1]
    far = int(np.argmax(np.hypot(*(p - p[0]).T)))
    a = dp(np.vstack([p[:far + 1]]), eps)
    b = dp(np.vstack([p[far:], p[:1]]), eps)
    return np.vstack([a, b[1:-1]])


def area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def path(p, closed=True):
    """(n,2) px -> compact SVG subpath on a 0.1 px grid: absolute start, relative steps
    ('M x y l dx dy dx dy ... z'), so subpaths can be concatenated safely."""
    q = np.round(np.asarray(p) * 10).astype(int)
    keep = np.ones(len(q), bool)
    keep[1:] = np.any(q[1:] != q[:-1], axis=1)                  # drop repeats after rounding
    q = q[keep]
    if closed and len(q) > 1 and (q[0] == q[-1]).all():
        q = q[:-1]
    if len(q) < (3 if closed else 2):
        return ""
    d = np.vstack([q[:1], np.diff(q, axis=0)])

    def f(v):
        s = f"{v / 10:.1f}".rstrip("0").rstrip(".") if v % 10 else str(v // 10)
        return s.replace("0.", ".", 1) if s.startswith("0.") else s.replace("-0.", "-.", 1)

    out = "M" + f(int(d[0, 0])) + ("" if f(int(d[0, 1])).startswith("-") else " ") + f(int(d[0, 1])) + "l"
    for dx, dy in d[1:]:
        for v in (dx, dy):
            s = f(int(v))
            out += s if (out[-1] == "l" or s.startswith("-")) else " " + s
    return out + ("z" if closed else "")


def pt(x):
    return [round(float(x[0]), 1), round(float(x[1]), 1)]


# ---------------------------------------------------------------- inputs
world = json.loads(COUNTRIES.read_text(encoding="utf-8"))
usa = json.loads(STATES.read_text(encoding="utf-8"))
w_arcs, s_arcs = decode_arcs(world), decode_arcs(usa)
js = AIRLINE_JS.read_text(encoding="utf-8")
air = json.loads(js[js.index("{"):js.rindex("}") + 1])
ap_tab = air["network"]["airports"]
ci = {c: i for i, c in enumerate(ap_tab["cols"])}
airports = {r[ci["code"]]: (r[ci["lon"]], r[ci["lat"]]) for r in ap_tab["rows"]}
with open(HOTSPOTS, newline="", encoding="utf-8") as f:
    cities = list(csv.DictReader(f))

# ================================================================ pacific
W_PAC, PAD = 1000, 22
ll = np.array(list(airports.values()))
lon0 = float((ll[:, 0].min() + ll[:, 0].max()) / 2)
lat0 = float((ll[:, 1].min() + ll[:, 1].max()) / 2)
P = LAEA(lon0, lat0)
# frame: every airport, plus the Aleutians, Maine, the Bahamas and the Arctic coast for context
anchors = np.vstack([ll, [[-178.0, 51.5], [-67.0, 45.0], [-77.0, 25.0], [-157.0, 72.0]]])
P.fit(anchors, W_PAC, PAD)
H_PAC = math.ceil(P.height)
EPS = 0.45                                      # simplification tolerance, px
M = 6                                           # clip a few px outside the frame (no edge strokes)
frame = (-M, -M, W_PAC + M, H_PAC + M)

land = []                                       # one d string per land polygon (outer ring + holes)
for geom in world["objects"]["land"]["geometries"]:
    for poly in polygons(geom):
        d_poly = ""
        for ri, ring in enumerate(poly):
            g = ring_points(ring, w_arcs)
            if angular_dist(g, lon0, lat0).min() > 80:          # far side of the globe: skip
                continue
            c = clip_ring(P(densify(g)), *frame)
            if c is None:
                continue
            s = dp_ring(c, EPS)
            if len(s) >= 3 and area(s) >= 2.0:
                d_poly += path(s)
            elif ri == 0:
                break                                           # outer ring gone: drop its holes
        if d_poly:
            land.append(d_poly)


def mesh(topo_obj, arcs, proj, frame_, eps, shared_only=True):
    """Arcs used by two different geometries (= interior borders) as open polylines."""
    owners = {}
    for gi, geom in enumerate(topo_obj["geometries"]):
        for poly in polygons(geom):
            for ring in poly:
                for i in ring:
                    owners.setdefault(i if i >= 0 else ~i, set()).add(gi)
    lines = []
    for a, who in owners.items():
        if shared_only and len(who) < 2:
            continue
        g = arcs[a]
        for run in clip_line(proj(densify(g)), *frame_):
            d = path(dp(run, eps), closed=False)
            if d:
                lines.append(d)
    return lines


states_lines = mesh(usa["objects"]["states"], s_arcs, P, frame, EPS)
# international borders in the frame (US-Canada, US-Mexico, Mexico-Guatemala ...)
border_lines = []
keep_c = {"United States of America", "Canada", "Mexico", "Guatemala", "Belize", "Honduras",
          "El Salvador", "Nicaragua", "Costa Rica", "Panama", "Cuba", "Russia", "Haiti", "Dominican Rep."}
sub = {"geometries": [g for g in world["objects"]["countries"]["geometries"]
                      if g.get("properties", {}).get("name") in keep_c]}
border_lines = mesh(sub, w_arcs, P, frame, EPS)

pac_airports = {c: pt(P(np.array([xy]))[0]) for c, xy in airports.items()}
off_frame = [c for c, (x, y) in pac_airports.items() if not (0 <= x <= W_PAC and 0 <= y <= H_PAC)]
# Pago Pago (American Samoa, HA only) is the one airport south of 19N and stretches the frame
# into empty ocean. viewBoxMain is a crop of the same frame without it (paths are already clipped
# to the full frame, so the UI can switch viewBox without other changes).
south = [c for c, (lon, lat) in airports.items() if lat < 15]
main_y = max(y for c, (x, y) in pac_airports.items() if c not in south) + 40
pacific = {"viewBox": f"0 0 {W_PAC} {H_PAC}", "viewBoxMain": f"0 0 {W_PAC} {math.ceil(min(main_y, H_PAC))}",
           "outside_main": south, "proj": P.params(), "land": land, "borders": border_lines,
           "states": states_lines, "airports": pac_airports}

# ================================================================ west
W_W, PAD_W = 800, 14
st_geoms = usa["objects"]["states"]["geometries"]
name_of = {i: g["properties"]["name"] for i, g in enumerate(st_geoms)}
fleet_states = sorted({c["state"] for c in cities})
gi_of = {v: k for k, v in name_of.items()}
missing_states = [s for s in fleet_states if s not in gi_of]
# neighbours = states sharing at least one arc with a fleet state
arc_owner = {}
for gi, geom in enumerate(st_geoms):
    for poly in polygons(geom):
        for ring in poly:
            for i in ring:
                arc_owner.setdefault(i if i >= 0 else ~i, set()).add(gi)
nbr = set()
for who in arc_owner.values():
    if any(name_of[g] in fleet_states for g in who):
        nbr |= who


def centroid_lon(gi):
    """Mean longitude of the outer-ring vertices (good enough to tell west from east)."""
    pts = np.vstack([ring_points(poly[0], s_arcs) for poly in polygons(st_geoms[gi])])
    return float(pts[:, 0].mean())


# keep the neighbours that are still "west": centroid west of 89.5 W (drops IL, KY, TN)
west_ids = sorted({gi_of[s] for s in fleet_states} | {g for g in nbr if centroid_lon(g) < -89.5})
west_pts = np.vstack([ring_points(r, s_arcs) for gi in west_ids for poly in polygons(st_geoms[gi]) for r in poly])
Q = LAEA(float((west_pts[:, 0].min() + west_pts[:, 0].max()) / 2),
         float((west_pts[:, 1].min() + west_pts[:, 1].max()) / 2))
Q.fit(west_pts, W_W, PAD_W)
H_W = math.ceil(Q.height)
EPS_W = 0.35
# simplify each arc once so shared borders stay identical in both neighbouring states
used = {i if i >= 0 else ~i for gi in west_ids for poly in polygons(st_geoms[gi]) for r in poly for i in r}
simp = {a: dp(Q(densify(s_arcs[a])), EPS_W) for a in used}
west_states = []
for gi in west_ids:
    parts = []
    for poly in polygons(st_geoms[gi]):
        for ring in poly:
            segs = [simp[i] if i >= 0 else simp[~i][::-1] for i in ring]
            p = np.vstack([s if k == 0 else s[1:] for k, s in enumerate(segs)])
            if len(p) >= 4 and area(p) >= 1.0:
                parts.append(path(p))
    west_states.append({"name": name_of[gi], "fleet": name_of[gi] in fleet_states, "d": "".join(parts)})
west_cities = []
for c in cities:
    x, y = Q(np.array([[float(c["lon"]), float(c["lat"])]]))[0]
    west_cities.append({"city": c["city"], "state": c["state"], "x": round(float(x), 1), "y": round(float(y), 1),
                        "pings": int(c["pings"]), "abnormal": int(c["abnormal"]),
                        "rate": round(float(c["per_1000_pings"]), 2)})
west = {"viewBox": f"0 0 {W_W} {H_W}", "proj": Q.params(), "states": west_states, "cities": west_cities}

# ================================================================ write
out = {"pacific": pacific, "west": west,
       "meta": {"source": "Natural Earth via world-atlas@2 countries-50m and us-atlas@3 states-10m (TopoJSON, ISC); "
                          "airport x,y from data/airline_real.js (OurAirports); cities from the fleet project",
                "projection": "Lambert azimuthal equal-area (sphere), centred per map; X=(x-x0)*s, Y=(y0-y)*s",
                "simplify_px": {"pacific": EPS, "west": EPS_W}, "pacific_airports_off_frame": off_frame,
                "missing_states": missing_states}}
txt = json.dumps(out, separators=(",", ":"), ensure_ascii=False)
OUT.write_text("/* generated by analysis/geo_basemaps.py: do not edit by hand */\n"
               f"window.DATA_GEO = {txt};\n", encoding="utf-8")
print(f"pacific {W_PAC}x{H_PAC}: {len(land)} land rings, {len(states_lines)} state lines, "
      f"{len(border_lines)} border lines, {len(pac_airports)} airports, off-frame {off_frame}")
print(f"west {W_W}x{H_W}: {len(west_states)} states {[s['name'] for s in west_states]}, {len(west_cities)} cities")
print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
