#!/usr/bin/env python3
"""One printable PDF per score: the engraved lines in order, under a plain title. Written to the build folder, pdf/<slug>.pdf.

usage: pdf.py [SLUG ...]
"""
from concurrent.futures import ThreadPoolExecutor
import html
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import SITE, source  # noqa: E402

COPY = json.loads((SITE / "content" / "tracks.json").read_text())
BUILD = source("build")
ALBUMS = {a["slug"]: a["title"] for a in (json.loads(f.read_text()) for f in sorted((SITE / "content").glob("album-*.json")))}
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CSS = """@page { size: A4 landscape; margin: 12mm 12mm 12mm; } body { margin: 0; font: 11pt 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #0d0d0d; }
h1 { font-size: 28pt; font-weight: 500; margin: 0 0 2pt; letter-spacing: -.01em; } p { margin: 0 0 12pt; color: #6b6b6b; font-size: 9pt; }
.f { font-size: 13pt; font-weight: 500; color: #0d0d0d; } sup, sub { font-size: .66em; line-height: 0; }
h2 { font: 9pt ui-monospace, Menlo, monospace; color: #6b6b6b; margin: 10pt 0 2pt; break-after: avoid; } img { width: 100%; display: block; break-inside: avoid; }"""


def one(r):
    slug = r["slug"]
    data = json.loads((BUILD / "data" / f"{slug}.json").read_text())
    out = BUILD / "pdf" / f"{slug}.pdf"
    parts = []
    for line in data["lines"]:
        if line["s"]:
            parts.append(f"<h2>{html.escape(line['s'])}</h2>")
        if line["f"]:
            parts.append(f'<img src="{(BUILD / "scores" / slug / line["f"]).as_uri()}">')
    page = f"<!doctype html><meta charset=utf-8><style>{CSS}</style><h1>{html.escape(r['title'])}</h1><p>x=arcsin y · {html.escape(ALBUMS.get(r.get('album', 'f-t'), 'f(t)'))} · {r['n']} / 35 · {r['bpm']} BPM · xarcsiny.com</p><p class=\"f\">{COPY[slug]['exact']}</p>{''.join(parts)}"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "s.html"
        src.write_text(page, encoding="utf-8")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--allow-file-access-from-files", f"--user-data-dir={tmp}/p", "--no-pdf-header-footer", f"--print-to-pdf={out}", src.as_uri()],
                       check=True, capture_output=True, timeout=240)
    return slug, out.stat().st_size


def main():
    (BUILD / "pdf").mkdir(exist_ok=True)
    only = set(sys.argv[1:])  # slugs; none means every score
    rows = [r for r in json.loads((SITE / "data" / "tracks.json").read_text()) if r.get("bars") and (not only or r["slug"] in only)]
    with ThreadPoolExecutor(6) as ex:
        results = list(ex.map(one, rows))
    print(len(results), "PDFs", sum(s for _, s in results) // 1_000_000, "MB", max(s for _, s in results) // 1_000_000, "MB largest")


if __name__ == "__main__":
    main()
