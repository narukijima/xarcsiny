#!/usr/bin/env python3
"""Each track's own plot from cover_geometry() in its score, as a light SVG for a white page.
Run with the Python that can import the engine, because the scores do. Both are private (tools/paths.py).
"""
import importlib.util
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import SITE, source  # noqa: E402

OUT = source("build") / "figures"
MAX_POINTS = 1400
MAX_DOTS = 700


def thin(points, limit):
    if len(points) <= limit:
        return points
    step = len(points) / limit
    return [points[int(i * step)] for i in range(limit)] + [points[-1]]


def svg_of(geo):
    x0, x1, y0, y1 = geo["bounds"]
    span = max(x1 - x0, y1 - y0) or 1
    size, pad = 1000, 40
    scale = (size - 2 * pad) / span
    ox = pad + ((size - 2 * pad) - (x1 - x0) * scale) / 2
    oy = pad + ((size - 2 * pad) - (y1 - y0) * scale) / 2
    px = lambda p: (round(ox + (p[0] - x0) * scale, 1), round(size - oy - (p[1] - y0) * scale, 1))
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">']
    main = None
    for layer in geo["layers"]:
        role = layer.get("role", "curve")
        if "polyline" in layer:
            pts = [px(p) for p in thin(layer["polyline"], MAX_POINTS)]
            if len(pts) < 2:
                continue
            d = "M" + "L".join(f"{a} {b}" for a, b in pts)
            style = {"guide": 'stroke="#d4d4d4" stroke-width="1.5"', "curve": 'stroke="#0d0d0d" stroke-width="3.5"',
                     "orbit": 'stroke="#0d0d0d" stroke-width="1.5" stroke-opacity=".55"', "accent": 'stroke="#0d0d0d" stroke-width="3"'}.get(role, 'stroke="#0d0d0d" stroke-width="2"')
            cls = ' class="main"' if role == "curve" and main is None else ""
            if cls:
                main = True
            out.append(f'<path{cls} d="{d}" fill="none" {style} stroke-linejoin="round" stroke-linecap="round"/>')
        elif "points" in layer:
            pts = [px(p) for p in thin(layer["points"], MAX_DOTS)]
            radius = min(max(float(layer.get("radius", 8)) * size / 3000, 1.4), 16)
            fill = {"guide": "#c8c8c8", "orbit": "#0d0d0d"}.get(role, "#0d0d0d")
            out.append(f'<g fill="{fill}">' + "".join(f'<circle cx="{a}" cy="{b}" r="{radius:.1f}"/>' for a, b in pts) + "</g>")
    out.append("</svg>")
    return "".join(out)


def main():
    rows = json.loads((SITE / "data" / "tracks.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(source("engine")))
    missing = []
    for r in rows:
        path = source("records") / r["id"] / "score.py"
        spec = importlib.util.spec_from_file_location("track_" + r["id"].replace("-", "_"), path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            geo = mod.cover_geometry()
            svg = svg_of(geo)
            (OUT / f"{r['slug']}.svg").write_text(svg)
            print(r["slug"], len(svg) // 1024, "KB")
        except Exception as e:  # a track without a plot simply shows none
            missing.append((r["slug"], repr(e)[:120]))
    print("missing", missing)


if __name__ == "__main__":
    main()
