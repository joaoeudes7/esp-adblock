#!/usr/bin/env python3
"""Build web/world.svg from Natural Earth 110m countries (public domain).

One <path data-iso="XX"> per country, equirectangular projection, Douglas-Peucker
simplified so the whole map fits in ~50 KB. Served by the firmware at /world.svg and
recoloured by the dashboard (no runtime projection library, no CDN).

  python3 tools/build_world_svg.py ne_110m_admin_0_countries.geojson
  python3 tools/build_world_svg.py --fixture   # tiny inline polygon, no input file
"""
import argparse
import json
import math
import os

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "world.svg")
W, H = 800, 330           # 2.42:1 — crops the empty poles, keeps the map readable
LAT_MIN, LAT_MAX = -58.0, 84.0
TOL = 0.35                # degrees; ~0.8 px at this width


def project(lon, lat):
    x = (lon + 180.0) * W / 360.0
    y = (LAT_MAX - lat) * H / (LAT_MAX - LAT_MIN)
    return x, y


def simplify(points, tol):
    """Douglas-Peucker on (lon, lat) tuples; keeps the ring closed."""
    if len(points) < 4:
        return points
    closed = [tuple(p) for p in points]
    if closed[0] != closed[-1]:
        closed.append(closed[0])

    def dp(lo, hi):
        ax, ay = closed[lo]
        bx, by = closed[hi]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        keep, best, best_i = [], -1.0, -1
        for i in range(lo + 1, hi):
            px, py = closed[i]
            d = abs(dx * (ay - py) - (ax - px) * dy) / norm if norm else math.hypot(px - ax, py - ay)
            if d > best:
                best, best_i = d, i
        if best > tol:
            keep += dp(lo, best_i)
            keep.append(best_i)
            keep += dp(best_i, hi)
        return keep

    idx = sorted(set([0, len(closed) - 1] + dp(0, len(closed) - 1)))
    return [closed[i] for i in idx]


def ring_to_path(ring, tol):
    pts = simplify([(p[0], p[1]) for p in ring], tol)
    out = []
    for i, (lon, lat) in enumerate(pts):
        x, y = project(lon, lat)
        out.append(("M" if i == 0 else "L") + ("%.1f %.1f" % (x, y)).replace(".0", ""))
    return "".join(out) + "Z"


def feature_iso(props):
    for key in ("ISO_A2", "ISO_A2_EH"):
        cc = str(props.get(key, "")).strip().upper()
        if len(cc) == 2 and cc.isalpha():
            return cc
    return ""


def build(geo, tol=TOL):
    paths = []
    for f in geo["features"]:
        cc = feature_iso(f.get("properties", {}))
        if not cc or cc == "AQ":  # no ISO / Antarctica: dead space, not a destination
            continue
        geom = f.get("geometry") or {}
        gtype = geom.get("type")
        polys = []
        if gtype == "Polygon":
            polys = [geom["coordinates"]]
        elif gtype == "MultiPolygon":
            polys = geom["coordinates"]
        else:
            continue
        d = "".join(ring_to_path(ring, tol) for poly in polys for ring in poly if len(ring) >= 4)
        if d:
            paths.append('<path data-iso="%s" d="%s"/>' % (cc, d))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 330" '
            'role="img" aria-label="World map of estimated traffic destinations">'
            '<g fill-rule="evenodd">%s</g></svg>' % "".join(sorted(paths)))


def fixture():
    geo = {"features": [
        {"properties": {"ISO_A2": "AA"},
         "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}},
        {"properties": {"ISO_A2_EH": "BB"},
         "geometry": {"type": "MultiPolygon", "coordinates": [[[[20, 20], [30, 20], [30, 30], [20, 30], [20, 20]]]]}},
        {"properties": {"ISO_A2": "-99"}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 1], [0, 0]]]}},
    ]}
    svg = build(geo)
    assert 'data-iso="AA"' in svg and 'data-iso="BB"' in svg
    assert "-99" not in svg and svg.count("<path") == 2
    return svg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("geojson", nargs="?")
    ap.add_argument("-o", "--out", default=DEFAULT_OUT)
    ap.add_argument("--tol", type=float, default=TOL)
    ap.add_argument("--fixture", action="store_true")
    args = ap.parse_args()

    if args.fixture:
        print("fixture ok: %d bytes" % len(fixture()))
        return
    if not args.geojson:
        ap.error("missing GeoJSON (or use --fixture)")

    with open(args.geojson, encoding="utf-8") as f:
        geo = json.load(f)
    svg = build(geo, args.tol)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(svg)
    print("wrote %s: %d countries, %d bytes" % (args.out, svg.count("<path"), len(svg)))


if __name__ == "__main__":
    main()
