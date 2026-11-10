#!/usr/bin/env python3
"""Each track's own figure, as a light SVG for a white page.

First album: the plot from cover_geometry() in the track's score. Run with the Python that can import the engine,
because the scores do. Both are private (tools/paths.py).
Later albums: the track's own part of its album cover, drawn by the same rule as the cover.
  delta=r-V: one row of the cover. The level of the sound against a running expectation, in 35 slices of the track.
  0.123456789101112: the title's digits walk a turtle that turns 36 degrees per unit of the digit and steps forward.

usage: figures.py [--later]   (--later draws only the later albums and needs numpy and soundfile, not the engine)
"""
import importlib.util
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import SITE, setting, source  # noqa: E402

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


def rosette_svg(title):
    """The cover of 0.123456789101112, one title: per digit d turn d * 36 degrees, then step 1; repeat until the walk closes."""
    digits = [int(c) for c in title if c.isdigit()] or [0]
    extra = 1 if sum(digits) % 10 == 0 else 0  # a digit sum that is a multiple of 10 would walk off in a line
    periods = 10 // math.gcd(sum(digits) + extra, 10)
    h, x, y, pts = 0.0, 0.0, 0.0, [(0.0, 0.0)]
    for _ in range(periods):
        for d in digits:
            h += d * math.pi / 5
            x, y = x + math.cos(h), y + math.sin(h)
            pts.append((x, y))
        h += extra * math.pi / 5
    assert math.hypot(x, y) < 1e-6, title
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    half = max(max(abs(a - cx) for a in xs), max(abs(b - cy) for b in ys), 1e-9)
    d = "M" + "L".join(f"{500 + 440 * (a - cx) / half:.1f} {500 + 440 * (b - cy) / half:.1f}" for a, b in pts) + "Z"
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000"><path d="{d}" fill="none" stroke="#0d0d0d" stroke-width="5" stroke-linejoin="round"/></svg>'


def delta_rows(wavs, cols=35, hop_s=0.05, tau_s=8.0):
    """The cover of delta=r-V: delta = level - expectation per 50 ms, the expectation carried from track to track, in 35 slices per track."""
    import numpy as np
    import soundfile as sf
    a, v, rows = hop_s / tau_s, None, []
    for wav in wavs:
        x, sr = sf.read(str(wav), dtype="float32", always_2d=True)
        m = np.abs(x.mean(axis=1))
        hop = int(round(hop_s * sr))
        level = m[:len(m) // hop * hop].reshape(-1, hop).mean(axis=1).astype(np.float64)
        v = level[0] if v is None else v
        d = np.empty_like(level)
        for i, r in enumerate(level):
            d[i] = r - v
            v += a * d[i]
        edges = np.linspace(0, len(d), cols + 1).astype(np.int64)
        rows.append([float(d[edges[k]:edges[k + 1]].mean()) for k in range(cols)])
    top = float(np.quantile(np.abs(np.array(rows)), 0.97))
    return rows, top


def dots_svg(row, top, per_line=6, r_min=0.28, r_max=0.70, power=0.7):
    """One row of that cover, wrapped into a square: left to right, top to bottom. Filled: louder than expected. Ring: quieter."""
    cell = 880 / per_line
    lines = math.ceil(len(row) / per_line)
    y0 = 500 - cell * lines / 2
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">']
    for i, d in enumerate(row):
        r = (r_min + (r_max - r_min) * min(abs(d) / top, 1.0) ** power) * cell / 2
        cx, cy = 60 + cell * (i % per_line + 0.5), y0 + cell * (i // per_line + 0.5)
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="#0d0d0d"/>' if d >= 0 else
                   f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r - 2.5:.1f}" fill="none" stroke="#0d0d0d" stroke-width="5"/>')
    out.append("</svg>")
    return "".join(out)


def later(rows):
    by_album = {}
    for r in rows:
        if r.get("album", "f-t") != "f-t":
            by_album.setdefault(r["album"], []).append(r)
    for album in setting("albums"):
        mine = sorted(by_album.get(album["slug"], []), key=lambda r: r["n"])
        if album["slug"] == "delta-r-v":
            sheet = json.loads(Path(album["sheet"]).expanduser().read_text())
            wavs = [Path(album["masters"]).expanduser() / t["distribution_file"]["file"] for t in sorted(sheet["tracks"], key=lambda t: t["position"])]
            levels, top = delta_rows(wavs)
            for r in mine:
                (OUT / f"{r['slug']}.svg").write_text(dots_svg(levels[r["n"] - 1], top))
        else:
            for r in mine:
                (OUT / f"{r['slug']}.svg").write_text(rosette_svg(r["title"]))
        print(album["slug"], len(mine), "figures")


def main():
    rows = json.loads((SITE / "data" / "tracks.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    if "--later" in sys.argv:
        return later(rows)
    rows = [r for r in rows if r.get("album", "f-t") == "f-t"]
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
