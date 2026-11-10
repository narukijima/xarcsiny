#!/usr/bin/env python3
"""Build everything the site needs from the frozen album: streaming audio, loudness curves, scores, downloads.

Inputs are read-only and private: album masters, the frozen events of each release, track records (tools/paths.py).
Output goes to the private build folder, never to this repository: {audio,data,scores}.
A small public index stays here: data/tracks.json.

The first album has frozen events, so every track gets a score. The later albums are built voice by voice in code with no
such list. Their notes are read back from the code as it runs and each part is checked against its own audio (a private
tool); a track gets a score when that check let enough of it through, and the parts it refused are named on the page.
(--albums; their inputs are the "albums" list of the sources file.)

usage: extract.py [--only SLUG,...] [--no-audio] [--jobs N]
       extract.py --albums [--no-audio] [--jobs N]
"""
import argparse
import base64
import hashlib
from concurrent.futures import ProcessPoolExecutor
from fractions import Fraction as F
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import numpy as np
from scipy.signal import butter, sosfilt
import soundfile as sf
import verovio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import SITE, setting, source  # noqa: E402
from score_xml import Score, esc, family, to_midi  # noqa: E402

ALBUM = source("masters")
RECORDS = source("records")
OUT = source("build")
INDEX = SITE / "data" / "tracks.json"
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
MP3_KBPS = 192
FPS = 30
WAVE_POINTS = 960
SPARK_POINTS = 72
SLUGS = {"35-sine-title": "sin-x", "32-sine": "pure-sine", "11-mod-7": "mod-7", "01-euclid-7-16": "euclid-7-16"}
VEROVIO = {"pageWidth": 2400, "pageHeight": 3000, "scale": 42, "adjustPageHeight": True, "breaks": "none", "header": "none", "footer": "none",
           "font": "Bravura", "svgViewBox": True, "svgRemoveXlink": True, "pageMarginTop": 36, "pageMarginBottom": 24, "pageMarginLeft": 24,
           "pageMarginRight": 24, "minLastJustification": 0, "mnumInterval": 1}
SECTION_WORDS = re.compile(r"^(.*?)[_\s-]?(\d*)$")
# A later album's notes must line up with its released master, or it gets no score. The measure is the lag of the master's
# attacks behind the written drum hits. On the first album, whose events are exact, it reads -19 to 58 ms (a kick's loudest
# rise comes after its start), so that range is what "lined up" can mean here.
LAG_MS = (-25, 60)


def slug_of(track_id):
    return SLUGS.get(track_id, re.sub(r"^\d+-", "", track_id))


def album_order():
    """[(position, track_id, file)] and the delivered titles / hook starts from the DistroKid sheet."""
    rows, sheet = [], {}
    for line in source("sheet").read_text().splitlines():
        m = re.match(r"\|\s*(\d+)\s*\|\s*`(.+?)`.*?\|\s*`(\d\d-[^`]+)-wav24_48k\.wav`\s*\|\s*([\d:.]+)\s*\|\s*([\d:.]+)\s*\|", line)
        if m:
            title = m.group(2).replace("\\|", "|")
            sheet[int(m.group(1))] = {"title": title, "file": m.group(3), "preview": clock(m.group(5))}
    for pos in sorted(sheet):
        file_id = sheet[pos]["file"]
        rows.append((pos, re.sub(r"^\d\d-", "", file_id), file_id, sheet[pos]))
    return rows


def clock(s):
    m, sec = s.split(":")
    return int(m) * 60 + float(sec)


def beat_times(doc, beats):
    """Seconds of each requested beat, from the piecewise-constant tempo map."""
    tm = [(F(x["beat"]), F(x["bpm"])) for x in doc["tempo_map"]]
    anchors = [(tm[0][0], F(0), tm[0][1])]
    for (b0, bpm0), (b1, bpm1) in zip(tm, tm[1:]):
        anchors.append((b1, anchors[-1][1] + (b1 - b0) * 60 / bpm0, bpm1))
    zero = at_beat(anchors, F(0))
    return [float(at_beat(anchors, b) - zero) for b in beats]


def at_beat(anchors, b):
    cur = anchors[0]
    for a in anchors:
        if a[0] <= b:
            cur = a
    return cur[1] + (b - cur[0]) * 60 / cur[2]


def loudness_curves(wav):
    """A waveform for the seek line, a spark for lists, and 30 fps curves for what moves with the sound."""
    x, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    mono = x.mean(axis=1)
    hop = int(sr / FPS)
    n = len(mono) // hop
    low = sosfilt(butter(4, 160, "low", fs=sr, output="sos"), mono)

    def rms(sig):
        s = (sig[: n * hop] ** 2).reshape(n, hop).mean(axis=1)
        return np.sqrt(s)

    full, bass = rms(mono), rms(low)

    def to_byte(v, floor_db):
        db = 20 * np.log10(np.maximum(v, 1e-5))
        top = np.percentile(db, 99.5)
        return np.clip((db - (top - abs(floor_db))) / abs(floor_db), 0, 1)

    f8, b8 = to_byte(full, 30), to_byte(bass, 26)
    wave = bins(f8, WAVE_POINTS)
    spark = bins(f8, SPARK_POINTS)
    pack = lambda a: base64.b64encode((np.clip(a, 0, 1) * 255).astype("uint8").tobytes()).decode()
    return {"sr": sr, "duration": len(mono) / sr, "wave": [round(float(v), 3) for v in wave], "spark": [round(float(v), 2) for v in spark],
            "env": pack(f8), "bass": pack(b8), "mono": mono}


def bins(a, count):
    edges = np.linspace(0, len(a), count + 1).astype(int)
    return np.array([a[edges[i]: max(edges[i + 1], edges[i] + 1)].max() for i in range(count)])


def alignment_lag_ms(mono, sr, times):
    """Check the audio really starts at beat 0: the lag that best lines the drum/first-part onsets up with the sound."""
    if len(times) < 8:
        return None
    hop = sr // 200
    n = len(mono) // hop
    env = np.sqrt((mono[: n * hop] ** 2).reshape(n, hop).mean(axis=1))
    onset = np.maximum(np.diff(env, prepend=env[0]), 0)
    impulses = np.zeros(n)
    for t in times:
        i = int(t * 200)
        if 0 <= i < n:
            impulses[i] = 1
    best, lag_best = -1, 0
    for lag in range(-60, 61):
        s = float((onset * np.roll(impulses, lag)).sum())
        if s > best:
            best, lag_best = s, lag
    return lag_best * 5


def master_lag_ms(mono, sr, times, span_ms=120):
    """Milliseconds by which the master's attacks trail the written drum hits, searched within +-span_ms at 1 ms steps.
    A wider search would only find the next off-beat; a real offset shows as a lag away from 0 or at the edge."""
    if len(times) < 8:
        return None
    hop = sr // 1000
    n = len(mono) // hop
    env = np.sqrt((mono[: n * hop] ** 2).reshape(n, hop).mean(axis=1))
    onset = np.maximum(np.diff(env, prepend=env[0]), 0)
    impulses = np.zeros(n)
    for t in times:
        i = int(round(t * 1000))
        if 0 <= i < n:
            impulses[i] = 1
    best, lag_best = -1.0, 0
    for lag in range(-span_ms, span_ms + 1):
        v = float((onset * np.roll(impulses, lag)).sum())
        if v > best:
            best, lag_best = v, lag
    return lag_best


def section_label(name):
    s = re.sub(r"[_-]+", " ", name).strip()
    m = re.match(r"([A-Za-z' ]+?)\s*(\d+)$", s)
    if m:
        s = f"{m.group(1)} {m.group(2)}"
    return s[:1].upper() + s[1:]


def plan_lines(score):
    """Lines of bars inside sections: four bars, two when a bar is too crowded to read. Every section starts a new line."""
    marks = [(s["bar"], s["name"]) for s in score.doc.get("sections") or [] if s["bar"] < score.n_bars]
    if not marks or marks[0][0] != 0:
        marks = [(0, "")] + marks
    lines = []
    for k, (start, name) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else score.n_bars
        bar, first = start, True
        while bar < end:
            per = 2 if max(score.density(b) for b in range(bar, min(bar + 4, end))) > 26 else 4
            if score.bar_beats >= 5:
                per = min(per, 3)
            stop = min(bar + per, end)
            if end - stop == 1:
                stop = end if stop - bar + 1 <= 5 and per >= 4 else stop
            lines.append({"b0": bar, "b1": stop, "section": section_label(name) if first and name else None})
            bar, first = stop, False
    return lines


def geometry(svg):
    """Width-normalised x ranges of each bar line by line, read back from the engraving."""
    m = re.search(r'class="definition-scale"[^>]*viewBox="0 0 (\d+) (\d+)"', svg)
    if not m:
        m = re.search(r'viewBox="0 0 (\d+) (\d+)"[^>]*class="definition-scale"', svg)
    w = float(m.group(1))
    t = re.search(r'class="page-margin"[^>]*translate\((-?\d+(?:\.\d+)?)', svg)
    if not t:
        t = re.search(r'translate\((-?\d+(?:\.\d+)?), ?(-?\d+(?:\.\d+)?)\)"[^>]*class="page-margin"', svg)
    off = float(t.group(1)) if t else 0.0
    bars = []
    pieces = re.split(r'class="measure"', svg)[1:]
    for chunk in pieces:
        line = re.search(r'class="staff".*?<path d="M(-?\d+) -?\d+ L(-?\d+) ', chunk, re.S)
        if not line:
            continue
        x0, x1 = float(line.group(1)), float(line.group(2))
        notes = [float(v) for v in re.findall(r'<use[^>]*?\sx="(-?\d+(?:\.\d+)?)"[^>]*?(?:transform="[^"]*scale\(0\.\d+)?', chunk.split('class="staff"', 2)[1])] if 'class="staff"' in chunk else []
        first = min(notes) if notes else x0
        bars.append([round((min(max(first, x0), x1) + off) / w, 4), round((x1 + off) / w, 4)])
    return bars


def tidy_svg(svg):
    svg = re.sub(r'<desc>.*?</desc>', "", svg, flags=re.S)
    svg = re.sub(r'\s+id="[^"]*"(?=[^>]*class="(?:note|rest|chord|stem|accid|artic|beam|tuplet|dots|verse|barLine|flag|notehead|tie))', "", svg) if False else svg
    svg = re.sub(r'font-family="[^"]*"', 'font-family="Helvetica Neue,Helvetica,Arial,sans-serif"', svg)
    svg = re.sub(r">\s+<", "><", svg)
    return svg.strip()


def build_score(doc, track, title, out_dir):
    score = Score(doc, track, title)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "score.musicxml").write_text(score.xml(head_marks=True), encoding="utf-8")
    (out_dir / "score.mid").write_bytes(to_midi(doc, score.parts, title))
    tk = verovio.toolkit()
    tk.setOptions(VEROVIO)
    lines = []
    for i, line in enumerate(plan_lines(score)):
        ids = score.busy_parts(line["b0"], line["b1"])
        name = f"l{i+1:03d}.svg"
        if ids:
            if not tk.loadData(score.xml(line["b0"], line["b1"], ids)):
                raise RuntimeError(f"verovio refused {title} line {i}: {tk.getLog()[:300]}")
            svg = tk.renderToSVG(1)
            bars = geometry(svg)
            svg = tidy_svg(svg)
            (out_dir / name).write_text(svg, encoding="utf-8")
            vb = re.match(r'<svg viewBox="0 0 (\d+) (\d+)"', svg)
            aspect = round(int(vb.group(1)) / int(vb.group(2)), 3)
            if len(bars) != line["b1"] - line["b0"]:
                raise RuntimeError(f"{title} line {i}: {len(bars)} bars read back for {line['b1'] - line['b0']}")
        else:
            name, aspect, bars = None, None, []
        lines.append({"f": name, "b0": line["b0"], "b1": line["b1"], "s": line["section"], "a": aspect, "x": bars})
    return score, lines


def one_track(args):
    pos, track_id, file_id, sheet, skip_audio = args
    slug = slug_of(track_id)
    track = json.loads((RECORDS / track_id / "track.json").read_text())
    doc = json.loads(Path(setting("events").format(track_id=track_id)).expanduser().read_text())
    wav = ALBUM / f"{file_id}-wav24_48k.wav"
    curves = loudness_curves(wav)
    mono, sr = curves.pop("mono"), curves.pop("sr")
    score, lines = build_score(doc, track, sheet["title"], OUT / "scores" / slug)
    bar_beats = score.bar_beats
    bar_list = [F(b * bar_beats) for b in range(score.n_bars + 1)]
    bar_t = beat_times(doc, bar_list)
    onsets = sorted({float(F(e["beat"])) for e in doc["events"] if F(e["beat"]) >= 0 and re.search("kick|drum|808|bass|sub", e["inst"], re.I)})
    onset_t = beat_times(doc, [F(o).limit_denominator(960) for o in onsets[:1200]])
    lag = alignment_lag_ms(mono, sr, onset_t)
    data = {"slug": slug, "fps": FPS, "duration": round(curves["duration"], 3), "wave": curves["wave"], "env": curves["env"], "bass": curves["bass"],
            "bars": [round(t, 4) for t in bar_t], "barBeats": bar_beats, "lines": lines}
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    (OUT / "data" / f"{slug}.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    if not skip_audio:
        (OUT / "audio").mkdir(parents=True, exist_ok=True)
        mp3 = OUT / "audio" / f"{slug}.mp3"
        if not mp3.exists():
            subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(wav), "-ac", "2", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", f"{MP3_KBPS}k", "-id3v2_version", "3",
                            "-metadata", f"title={sheet['title']}", "-metadata", "artist=x=arcsin y", "-metadata", "album=f(t)", "-metadata", f"track={pos}/35", str(mp3)], check=True)
    n_notes = sum(len(p.notes) for p in score.parts)
    return {"n": pos, "id": track_id, "slug": slug, "title": sheet["title"], "exact": track["title"].get("unicode"), "reading": track["title"].get("reading"),
            "bpm": track.get("bpm"), "key": track.get("key"), "meter": track.get("meter"), "duration": round(curves["duration"], 2), "hook": round(sheet["preview"], 2),
            "spark": curves["spark"], "bars": score.n_bars, "parts": [p.name for p in score.parts], "notes": n_notes, "lines": len(lines), "lag_ms": lag}


def later_albums():
    """Jobs for the albums without events: positions, titles as delivered, the masters (checked against the sheet's hashes)."""
    taken = {r["slug"] for r in json.loads(INDEX.read_text()) if r.get("album", "f-t") == "f-t"}
    content = {a["slug"]: a for a in (json.loads(f.read_text()) for f in sorted((SITE / "content").glob("album-*.json")))}
    jobs = []
    for album in setting("albums"):
        sheet = json.loads(Path(album["sheet"]).expanduser().read_text())
        titles = {}
        for line in Path(album["titles"]).expanduser().read_text().splitlines():
            m = re.match(r"\|\s*(\d+)\s*\|\s*`((?:\\.|[^`\\])+)`", line)
            if m:
                titles.setdefault(int(m.group(1)), m.group(2).replace("\\|", "|"))
        if len(sheet["tracks"]) != 35 or sorted(titles) != list(range(1, 36)):
            raise SystemExit(f"{album['slug']}: expected 35 tracks and 35 titles")
        for t in sheet["tracks"]:
            track_id = t["track_id"]
            slug = album["slugs"].get(track_id) or re.sub(r"^[a-z]+\d*-(\d+-)?", "", track_id)
            if slug in taken:
                raise SystemExit(f"{album['slug']} {t['position']}: the slug {slug} is taken; name another in the sources file")
            taken.add(slug)
            wav = Path(album["masters"]).expanduser() / t["distribution_file"]["file"]
            if hashlib.sha256(wav.read_bytes()).hexdigest() != t["distribution_file"]["sha256"]:
                raise SystemExit(f"{album['slug']} {t['position']}: the master is not the delivered file")
            record = json.loads((RECORDS / track_id / "track.json").read_text())
            job = {"album": album["slug"], "album_title": content[album["slug"]]["title"], "n": t["position"], "slug": slug, "title": titles[t["position"]], "wav": str(wav),
                   "reading": t.get("reading"), "bpm": t.get("bpm"), "key": t.get("key"), "meter": record.get("meter"), "hook": float(t.get("preview_start_s") or 0)}
            notes = Path(album["notes"].format(track_id=track_id)).expanduser() if album.get("notes") else None
            if notes and (notes / "report.json").exists():
                summary = json.loads((notes / "report.json").read_text())["summary"]
                if summary.get("publish"):
                    job.update(notes=str(notes / "events.json"), unwritten=summary.get("unwritten") or [], record={"meter": record.get("meter"), "key": record.get("key")})
            jobs.append(job)
    return jobs


def later_score(job, mono, sr):
    """Score files and the bar clock of a later album's track, or None when its notes do not line up with the master."""
    doc = json.loads(Path(job["notes"]).read_text())
    out_dir = OUT / "scores" / job["slug"]
    score, lines = build_score(doc, job["record"], job["title"], out_dir)
    bar_t = beat_times(doc, [F(b * score.bar_beats) for b in range(score.n_bars + 1)])
    def onsets(rx):
        return sorted({F(e["beat"]) for e in doc["events"] if re.search(rx, e["inst"], re.I) and ("midi" in e) == (rx == ".")})
    beats = next((b for b in (onsets("kick|bd|thump|stomp|surdo"), onsets("snare|clap|hat|tom|perc|drum|open|shaker|crash|cym|ride|tick|stick|tamb|feet"), onsets(".")) if len(b) >= 8), [])
    lag = master_lag_ms(mono, sr, beat_times(doc, beats[:2000]))
    if lag is None or not LAG_MS[0] <= lag <= LAG_MS[1]:
        shutil.rmtree(out_dir)
        return None, lag
    names = []
    for stem in job["unwritten"]:
        name = family(stem)
        if name not in names:
            names.append(name)
    return {"data": {"bars": [round(t, 4) for t in bar_t], "barBeats": score.bar_beats, "lines": lines},
            "row": {"bars": score.n_bars, "parts": [p.name for p in score.parts], "notes": sum(len(p.notes) for p in score.parts), "lines": len(lines), "lag_ms": lag, "unwritten": names}}, lag


def one_later(job, skip_audio=False):
    curves = loudness_curves(job["wav"])
    mono, sr = curves.pop("mono"), curves.pop("sr")
    slug = job["slug"]
    data = {"slug": slug, "fps": FPS, "duration": round(curves["duration"], 3), "wave": curves["wave"], "env": curves["env"], "bass": curves["bass"], "lines": []}
    scored, lag = later_score(job, mono, sr) if job.get("notes") else (None, None)
    if scored:
        data.update(scored["data"])
    elif (OUT / "scores" / slug).exists():
        shutil.rmtree(OUT / "scores" / slug)   # a score from an earlier run that no longer passes
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    (OUT / "data" / f"{slug}.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    mp3 = OUT / "audio" / f"{slug}.mp3"
    if not skip_audio and not mp3.exists():
        mp3.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", job["wav"], "-ac", "2", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", f"{MP3_KBPS}k", "-id3v2_version", "3",
                        "-metadata", f"title={job['title']}", "-metadata", "artist=x=arcsin y", "-metadata", f"album={job['album_title']}", "-metadata", f"track={job['n']}/35", str(mp3)], check=True)
    row = {"n": job["n"], "album": job["album"], "slug": slug, "title": job["title"], "reading": job["reading"], "bpm": job["bpm"], "key": job["key"], "meter": job["meter"],
           "duration": round(curves["duration"], 2), "hook": round(job["hook"], 2), "spark": curves["spark"]}
    if scored:
        row.update(scored["row"])
    elif job.get("notes"):
        row["held_lag_ms"] = lag
    return row


def one_later_quiet(job):
    return one_later(job, True)


def main_later(a):
    jobs = later_albums()
    with ProcessPoolExecutor(a.jobs) as ex:
        rows = list(ex.map(one_later_quiet if a.no_audio else one_later, jobs))
    first = [r for r in json.loads(INDEX.read_text()) if r.get("album", "f-t") == "f-t"]
    INDEX.write_text(json.dumps(first + rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rows:
        print(r["album"], r["n"], r["slug"], r["title"], r["duration"], f"score: {r['bars']} bars, {len(r['parts'])} parts, {r['notes']} notes, lag {r['lag_ms']} ms" if r.get("bars") else f"no score (lag {r['held_lag_ms']} ms)" if "held_lag_ms" in r else "no score")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--albums", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--jobs", type=int, default=10)
    a = ap.parse_args()
    if a.albums:
        return main_later(a)
    order = album_order()
    if len(order) != 35:
        raise SystemExit(f"expected 35 rows in the sheet, got {len(order)}")
    only = {s for s in a.only.split(",") if s}
    jobs = [(p, t, f, s, a.no_audio) for p, t, f, s in order if not only or slug_of(t) in only]
    with ProcessPoolExecutor(a.jobs) as ex:
        rows = list(ex.map(one_track, jobs))
    if only and INDEX.exists():
        keep = {r["slug"]: r for r in json.loads(INDEX.read_text()) if r.get("album", "f-t") == "f-t"}
        keep.update({r["slug"]: r for r in rows})
        rows = sorted(keep.values(), key=lambda r: r["n"])
    if INDEX.exists():  # the later albums stay in the index
        rows += [r for r in json.loads(INDEX.read_text()) if r.get("album", "f-t") != "f-t"]
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rows:
        print(r["n"], r["slug"], r["title"], r["bars"], "bars", r["lines"], "lines", len(r["parts"]), "parts", r["notes"], "notes", "lag", r["lag_ms"], "ms")


if __name__ == "__main__":
    main()
