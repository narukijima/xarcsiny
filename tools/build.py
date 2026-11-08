#!/usr/bin/env python3
"""Generate xarcsiny.com as static files.

Reads data/tracks.json (extract.py), data/stores.json (stores.py), content/*.json, and the private build folder.
Writes the private dist folder, which tools/deploy.py deploys (tools/paths.py).
"""
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import SITE, source  # noqa: E402

BUILD = source("build")
DIST = source("dist")
ORIGIN = "https://xarcsiny.com"
TRACKS = json.loads((SITE / "data/tracks.json").read_text())
COPY = json.loads((SITE / "content/tracks.json").read_text())
SECOND = json.loads((SITE / "content/album-delta.json").read_text())
STORES = json.loads((SITE / "data/stores.json").read_text())
RELEASED = "2026-10-16"
SOCIAL = [("YouTube", "https://www.youtube.com/@xarcsiny"), ("TikTok", "https://www.tiktok.com/@xarcsiny"), ("Instagram", "https://www.instagram.com/xarcsiny/")]
CONTACT = "contact@xarcsiny.com"
GITHUB = "https://github.com/narukijima/xarcsiny"
ICON_PLAY = '<svg class="i-play" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 1.5v13l11-6.5z"/></svg>'
ICON_PAUSE = '<svg class="i-pause" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 1.5h3.6v13H3zM9.4 1.5H13v13H9.4z"/></svg>'
TOTAL_S = sum(t["duration"] for t in TRACKS)
TOTAL = f"{int(TOTAL_S // 60)}:{int(TOTAL_S % 60):02d}"

T = dict(
        lib="Library", albums="Albums", scores="Scores", about="About", about_nav="About", tagline="Every equation has a sound.",
        tap="Or tap one as it falls.", play_random="Play an equation", open_track="About this track", read_score="Read the score", play="Play", listen="Listen to the album", first_album="The first album.",
        album_lede=f"35 equations, {int(TOTAL_S // 60)} minutes. Every sound in it is calculated: no recordings, no samples.",
        plots="35 tracks, 35 plots", plots_more="Open the library", excerpt_t="The scores are public", excerpt_p="All 35 scores are here to read, in real notation, moving with the sound.", all_scores="All scores",
        how_t="How it sounds like this", how=[("One equation", "Each track picks one equation and hands it the part you remember: a bass line, a rhythm, the way an echo falls."),
                                         ("Calculated, all of it", "AI composes the track and writes the code. The code computes every sample, including the voices and the accordion."),
                                         ("A person listens", "Naru Kijima listens and decides what stays. All 35 tracks here survived that.")], more_about="More about how it works",
        lib_lede="Search by equation, sound or genre. Tap a plot to hear it.", search="Search equations, genres", sort_album="Album order", sort_title="A–Z", sort_slow="Slowest", sort_fast="Fastest", sort_short="Shortest",
        view_list="List", view_grid="Plots", nothing="No equation matches that.", tempo="Tempo", key="Key", meter="Meter", length="Length", genre="Genre", album="Album", label="Label", released="Released", tracks_w="Tracks", credits="Credits",
        decides="What the equation decides", composed="What was composed", equation="The equation", score_h="Score", read_full="Read the full score", prev="Previous", next="Next", track_of="track",
        on_apple="Apple Music", all_stores="All stores", scores_lede="The notes of all 35 tracks, in standard notation. Press play and the page follows the sound.",
        score_note="This is the notation of what the code plays. Stereo copies and octave layers share one staff, empty staves are hidden, and timing is rounded to values you can read. Pitch bends, filter moves and the rest of what the equation does to the sound can't be written here. That part you have to hear.",
        follow="Follow the sound", dl_pdf="PDF", dl_xml="MusicXML", dl_mid="MIDI", silent="Rest", bars="bars", parts="parts", notes="notes", terms="Terms", privacy="Privacy", follow_h="Follow", site_h="Site",
        albums_lede="Two so far, both out.", second_lede=f"35 equations, {SECOND['minutes']} minutes. Every sound in it is calculated: no recordings, no samples.", stores_all="Stores", release_date="Release date", album_about="f(t) means a sound as a function of time, the one thing all 35 tracks have in common. It opens on the plainest curve there is, y=sin(x), and closes on a problem nobody has solved, n→3n+1.",
        about_title="About", not_found="This equation has no solution.", not_found_p="The page you asked for isn't here.", home="Back to the start",
        now_loading="Loading", desc_home="x=arcsin y makes music from equations. Tap an equation to hear it, read every score, and see what the math decides.", desc_lib="All tracks by x=arcsin y: equations you can play, search and read.",
        desc_albums="Albums by x=arcsin y.", desc_scores="Sheet music for every x=arcsin y track, in standard notation, moving with the sound.", desc_about="How x=arcsin y turns equations into music, and who is behind it.",
        score_title="Score", free_use="Free to read, study and play.", sheet_for="Sheet music", desc_score="Read the sheet music of {t} by x=arcsin y: {p} parts, {b} bars, moving with the sound.", play_score="Play along", terms_title="Terms", privacy_title="Privacy")


def esc(s):
    return html.escape(str(s), quote=True)


def clock(sec):
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def short_key(k):
    k = re.split(r"\s*\(|;", k or "")[0].strip()
    k = k.replace("-flat", "♭").replace("-sharp", "♯").replace("pelog-like", "pelog")
    return re.sub(r"([A-G])b\b", "\\1♭", re.sub(r"([A-G])#", "\\1♯", k))


def short_meter(m):
    return re.split(r"\s*\(", m or "")[0].strip()


def spark_svg(values):
    """The track's loudness shape. Mastered music sits near the top, so each spark is stretched to its own range."""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    n = len(values)
    pts = " ".join(f"{i * 100 / (n - 1):.1f} {27 - ((v - lo) / span) ** 1.4 * 25:.1f}" for i, v in enumerate(values))
    return f'<svg class="spark" viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true"><path d="M{pts}"/></svg>'


def json_ld(data):
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def shell(path, title, desc, body, og="home", ld=None, nav=None):
    t = T
    canon = ORIGIN + (path)
    items = [("lib", "/library/"), ("albums", "/albums/"), ("scores", "/scores/"), ("about_nav", "/about/")]
    links = "".join(f'<a href="{(p)}"{" aria-current=page" if nav == k.replace("_nav", "") else ""}>{t[k]}</a>' for k, p in items)
    data = json.dumps([[r["n"], r["slug"], r["title"], r["hook"], r["duration"]] for r in TRACKS], ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    socials = "".join(f'<li><a href="{h}" rel="noopener">{n}</a></li>' for n, h in SOCIAL)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="theme-color" content="#ffffff">
<link rel="canonical" href="{canon}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="x=arcsin y">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canon}">
<meta property="og:image" content="{ORIGIN}/assets/og/{og}.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/assets/img/icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/assets/img/apple-touch-icon.png">
<link rel="stylesheet" href="/assets/site.css?v={VERSION}">
<script id="tracks" type="application/json">{data}</script>
<script src="/assets/app.js?v={VERSION}" defer></script>
{json_ld(ld) if ld else ''}
</head>
<body>
<header class="site-head">
<a class="wordmark eq" href="/">x=arcsin y</a>
<nav class="nav">{links}</nav>
</header>
<main>{body}</main>
<footer class="site-foot">
<div><p class="say">{t['tagline']}</p><p class="credit">Math × Music × Code × AI = Math Sound<br>label y=sin(x)<br>artist x=arcsin y<br>prod. Naru Kijima</p></div>
<div><p class="label">{t['follow_h']}</p><ul>{socials}<li><a href="{STORES['album']['apple']}" rel="noopener">Apple Music</a></li><li><a href="{STORES['album']['spotify']}" rel="noopener">Spotify</a></li></ul></div>
<div><p class="label">{t['site_h']}</p><ul><li><a href="/about/">{t['about']}</a></li><li><a href="/terms/">{t['terms']}</a></li><li><a href="/privacy/">{t['privacy']}</a></li><li><a href="{GITHUB}" rel="noopener">GitHub</a></li><li><a href="mailto:{CONTACT}">{CONTACT}</a></li></ul></div>
</footer>
<div class="player" id="player" aria-label="Player">
<div class="ctl"><button id="prev" aria-label="{esc(t['prev'])}"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 2h2v12H3zM14 2v12L6 8z"/></svg></button><button id="toggle" class="main" aria-label="{esc(t['play'])}">{ICON_PLAY}{ICON_PAUSE}</button><button id="next" aria-label="{esc(t['next'])}"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M11 2h2v12h-2zM2 2v12l8-6z"/></svg></button></div>
<div class="now"><a id="now-title" class="eq" href="#"></a><span id="now-sub"></span></div>
<div class="seek-wrap"><canvas id="seek" class="seek" role="slider" tabindex="0" aria-label="Position" aria-valuemin="0" aria-valuemax="0" aria-valuenow="0"></canvas></div>
<div class="time" id="time"></div>
</div>
</body>
</html>
"""


def thumb(r, extra=""):
    t = T
    return (f'<button class="thumb" data-play="{r["slug"]}" aria-label="{esc(t["play"])} {esc(r["title"])}"{extra}><img src="/figures/{r["slug"]}.svg" alt="" loading="lazy" width="56" height="56">'
            f'<i>{ICON_PLAY}{ICON_PAUSE}</i></button>')


def home():
    t = T
    field = "".join(f'<li><a class="eq" href="{("/tracks/" + r["slug"] + "/")}" data-play="{r["slug"]}" data-from="hook" data-what="{esc(COPY[r["slug"]]["what"])}">{esc(r["title"])}</a></li>' for r in TRACKS)
    plots = "".join(f'<li><a href="{("/tracks/" + r["slug"] + "/")}" aria-label="{esc(r["title"])}"><img src="/figures/{r["slug"]}.svg" alt="" loading="lazy" width="200" height="200"><span class="cap eq">{esc(r["title"])}</span></a></li>' for r in TRACKS)
    how = "".join(f"<li><h3>{esc(a)}</h3><p>{esc(b)}</p></li>" for a, b in t["how"])
    sinc = next(r for r in TRACKS if r["slug"] == "sinc")
    tag = t["tagline"]
    lead = 'Every equation<span class="br"> has a sound.</span>'
    first = TRACKS[0]["slug"]
    body = f"""
<section class="hero">
<canvas class="rain" aria-hidden="true"></canvas>
<ul class="field" aria-label="All equations">{field}</ul>
<div class="stage">
<div class="stage-idle"><h1 class="stage-lead">{lead}</h1><p class="stage-cta"><button class="button" data-random>{ICON_PLAY}{t['play_random']}</button></p><p class="stage-sub">{t['tap']}</p></div>
<div class="stage-now"><a class="stage-title eq" href="#"></a><p class="stage-what"></p><p class="stage-actions"><a class="link stage-score" href="#">{t['read_score']}</a></p></div>
</div>
<canvas class="scope" aria-hidden="true"></canvas>
</section>
<section class="section">
<div class="album-split">
<a href="/albums/f-t/"><img src="/assets/img/cover-f-t-r2-1200.jpg" alt="f(t)" width="1200" height="1200" loading="lazy"></a>
<div><p class="label">{t['first_album']}</p><h2 class="eq"><a href="/albums/f-t/">f(t)</a></h2><p class="lede">{t['album_lede']}</p>
<p class="stores"><button class="button" data-play="{first}">{ICON_PLAY}{ICON_PAUSE}{t['listen']}</button></p>
<p class="stores"><a class="link" href="{STORES['album']['spotify']}" rel="noopener">Spotify</a><a class="link" href="{STORES['album']['apple']}" rel="noopener">{t['on_apple']}</a><a class="link" href="{STORES['album']['amazon']}" rel="noopener">Amazon Music</a><a class="link" href="{STORES['album']['all']}" rel="noopener">{t['all_stores']}</a></p></div>
</div>
</section>
<section class="section">
<div class="section-head"><h2>{t['plots']}</h2><a class="link" href="/library/">{t['plots_more']}</a></div>
<ul class="plots">{plots}</ul>
</section>
<section class="section">
<div class="section-head"><h2>{t['excerpt_t']}</h2><a class="link" href="/scores/">{t['all_scores']}</a></div>
<a class="excerpt" href="/scores/sinc/" aria-label="{esc(sinc['title'])}"><img src="/scores/sinc/l007.svg" alt="" loading="lazy"></a>
<p class="mute" style="margin-top:16px;max-width:34em">{t['excerpt_p']}</p>
</section>
<section class="section">
<div class="section-head"><h2>{t['how_t']}</h2><a class="link" href="/about/">{t['more_about']}</a></div>
<ul class="how">{how}</ul>
</section>"""
    ld = {"@context": "https://schema.org", "@type": "MusicGroup", "name": "x=arcsin y", "url": ORIGIN + "/", "genre": ["Electronic", "Dance"], "slogan": "Every equation has a sound.",
          "sameAs": [h for _, h in SOCIAL] + [STORES["album"]["apple"], STORES["album"]["spotify"], GITHUB], "album": {"@type": "MusicAlbum", "name": "f(t)", "url": ORIGIN + "/albums/f-t/"}}
    return shell("/", "x=arcsin y — " + tag, t["desc_home"], body, "home", ld)


def row(r):
    c = COPY[r["slug"]]
    style = c["style"]
    q = f"{r['title']} {c['style']} {re.sub('<[^>]+>', '', c['exact'])} {r.get('reading') or ''} {r['slug']}".lower()
    return f"""<li class="row" data-slug="{r['slug']}" data-n="{r['n']}" data-title="{esc(r['title'])}" data-bpm="{r['bpm']}" data-duration="{r['duration']}" data-q="{esc(q)}">
{thumb(r)}
<div class="row-main"><a class="row-title eq" href="{('/tracks/' + r['slug'] + '/')}"><span class="row-n num">{r['n']}</span>{esc(r['title'])}</a></div>
<span class="c-style mute">{esc(style)}</span><span class="c-spark">{spark_svg(r['spark'])}</span>
<span class="c-bpm mute num">{r['bpm']}</span><span class="c-key mute">{esc(short_key(r['key']))}</span><span class="mute num">{clock(r['duration'])}</span></li>"""


def library():
    t = T
    rows = "".join(row(r) for r in TRACKS)
    body = f"""<div class="page-head"><h1>{t['lib']}</h1><p>{t['lib_lede']}</p></div>
<div class="tools"><input class="search" type="search" placeholder="{esc(t['search'])}" aria-label="{esc(t['search'])}">
<div class="sort"><button class="on" data-sort="n">{t['sort_album']}</button><button data-sort="title">{t['sort_title']}</button><button data-sort="bpm">{t['sort_slow']}</button><button data-sort="bpmd">{t['sort_fast']}</button><button data-sort="duration">{t['sort_short']}</button></div>
<div class="views"><button class="on" data-view="list">{t['view_list']}</button><button data-view="grid">{t['view_grid']}</button></div></div>
<ul class="rows">{rows}</ul><p class="empty" hidden>{t['nothing']}</p><div style="height:var(--section)"></div>"""
    return shell("/library/", f"{t['lib']} — x=arcsin y", t["desc_lib"], body, "home", nav="lib")


def albums():
    t = T
    body = f"""<div class="page-head"><h1>{t['albums']}</h1><p>{t['albums_lede']}</p></div>
<div class="albums"><div class="album-split"><a href="/albums/f-t/"><img src="/assets/img/cover-f-t-r2-1200.jpg" alt="f(t)" width="1200" height="1200" loading="lazy"></a>
<div><p class="label">Album 01 · {RELEASED}</p><h2 class="eq"><a href="/albums/f-t/">f(t)</a></h2><p class="lede">{t['album_lede']}</p>
<p class="stores"><button class="button" data-play="{TRACKS[0]['slug']}">{ICON_PLAY}{ICON_PAUSE}{t['listen']}</button></p></div></div>
<div class="album-split album-long"><a href="/albums/{SECOND['slug']}/"><img src="/assets/img/cover-{SECOND['slug']}-r2-1200.jpg" alt="{esc(SECOND['title'])}" width="1200" height="1200" loading="lazy"></a>
<div><p class="label">Album 02 · {SECOND['release_date']}</p><h2 class="eq"><a href="/albums/{SECOND['slug']}/">{esc(SECOND['title'])}</a></h2><p class="lede">{t['second_lede']}</p>
<p class="stores"><a class="link" href="{SECOND['stores']}" rel="noopener">{t['stores_all']}</a></p></div></div></div>"""
    return shell("/albums/", f"{t['albums']} — x=arcsin y", t["desc_albums"], body, "album-f-t", nav="albums")


def album():
    t = T
    rows = "".join(row(r) for r in TRACKS)
    meta = [(t["released"], RELEASED), (t["tracks_w"], "35"), (t["length"], TOTAL), (t["label"], "y=sin(x)"), (t["genre"], "Electronic, Dance"), (t["credits"], "prod. Naru Kijima / AI")]
    dl = "".join(f"<dt>{esc(a)}</dt><dd>{esc(b)}</dd>" for a, b in meta)
    body = f"""<div class="section" style="padding-top:clamp(32px,6vw,80px)"><div class="album-split"><img src="/assets/img/cover-f-t-r2-1200.jpg" alt="f(t)" width="1200" height="1200">
<div><p class="label">Album 01 · x=arcsin y</p><h1 class="eq">f(t)</h1>
<p class="stores"><button class="button" data-play="{TRACKS[0]['slug']}">{ICON_PLAY}{ICON_PAUSE}{t['listen']}</button></p>
<p class="stores"><a class="link" href="{STORES['album']['spotify']}" rel="noopener">Spotify</a><a class="link" href="{STORES['album']['apple']}" rel="noopener">{t['on_apple']}</a><a class="link" href="{STORES['album']['amazon']}" rel="noopener">Amazon Music</a><a class="link" href="{STORES['album']['all']}" rel="noopener">{t['all_stores']}</a></p></div></div></div>
<div class="album-meta"><p>{esc(t['album_about'])}</p><dl class="meta">{dl}</dl></div>
<div style="height:calc(var(--u)*6)"></div>
<ul class="rows">{rows}</ul><div style="height:var(--section)"></div>"""
    ld = {"@context": "https://schema.org", "@type": "MusicAlbum", "name": "f(t)", "url": ORIGIN + "/albums/f-t/", "image": ORIGIN + "/assets/img/cover-f-t-r2-1200.jpg", "datePublished": RELEASED, "numTracks": 35,
          "byArtist": {"@type": "MusicGroup", "name": "x=arcsin y"}, "track": [{"@type": "MusicRecording", "name": r["title"], "url": f"{ORIGIN}/tracks/{r['slug']}/", "position": r["n"]} for r in TRACKS]}
    return shell("/albums/f-t/", f"f(t) — x=arcsin y", f"f(t), the first album by x=arcsin y. {t['album_lede']}", body, "album-f-t", ld, nav="albums")


def second_album():
    """Album 02 before its audio and scores are on this site: the list, the release date and DistroKid's page, which gains the store links when they go live."""
    t = T
    a = SECOND
    rows = "".join(f'<li><span class="row-n num">{r["n"]}</span><div><span class="row-title eq">{esc(r["title"])}</span><p>{esc(r["what"])}</p></div></li>' for r in a["tracks"])
    meta = [(t["release_date"], a["release_date"]), (t["tracks_w"], str(len(a["tracks"]))), (t["length"], a["total"]), (t["label"], "y=sin(x)"), (t["genre"], "Electronic, Dance"), (t["credits"], "prod. Naru Kijima / AI")]
    dl = "".join(f"<dt>{esc(x)}</dt><dd>{esc(y)}</dd>" for x, y in meta)
    path = f"/albums/{a['slug']}/"
    image = f"/assets/img/cover-{a['slug']}-r2-1200.jpg"
    body = f"""<div class="section" style="padding-top:clamp(32px,6vw,80px)"><div class="album-split album-long"><img src="{image}" alt="{esc(a['title'])}" width="1200" height="1200">
<div><p class="label">Album 02 · x=arcsin y</p><h1 class="eq">{esc(a['title'])}</h1><p class="lede">{t['second_lede']}</p>
<p class="stores"><a class="link" href="{a['stores']}" rel="noopener">{t['stores_all']}</a></p></div></div></div>
<div class="album-meta"><p>{esc(a['about'])}</p><dl class="meta">{dl}</dl></div>
<div style="height:calc(var(--u)*6)"></div>
<ol class="rows-text">{rows}</ol><div style="height:var(--section)"></div>"""
    ld = {"@context": "https://schema.org", "@type": "MusicAlbum", "name": a["title"], "url": ORIGIN + path, "image": ORIGIN + image, "datePublished": a["release_date"], "numTracks": len(a["tracks"]),
          "byArtist": {"@type": "MusicGroup", "name": "x=arcsin y"}, "track": [{"@type": "MusicRecording", "name": r["title"], "position": r["n"]} for r in a["tracks"]]}
    return shell(path, f"{a['title']} — x=arcsin y", f"{a['title']}, the second album by x=arcsin y. {t['second_lede']}", body, "album-" + a["slug"], ld, nav="albums")


def track(r):
    t = T
    c = COPY[r["slug"]]
    prev_r, next_r = TRACKS[r["n"] - 2] if r["n"] > 1 else None, TRACKS[r["n"]] if r["n"] < 35 else None
    fig = (BUILD / "figures" / f"{r['slug']}.svg").read_text()
    meta = [(t["genre"], c["style"]), (t["tempo"], f"{r['bpm']} BPM"), (t["key"], short_key(r["key"])), (t["meter"], short_meter(r["meter"])), (t["length"], clock(r["duration"])), (t["album"], f"f(t) · {r['n']} / 35")]
    dl = "".join(f"<dt>{esc(a)}</dt><dd>{esc(b)}</dd>" for a, b in meta)
    pager = []
    if prev_r:
        pager.append(f'<a class="eq" href="{("/tracks/" + prev_r["slug"] + "/")}"><span>{t["prev"]}</span>{esc(prev_r["title"])}</a>')
    else:
        pager.append("<span></span>")
    if next_r:
        pager.append(f'<a class="eq" href="{("/tracks/" + next_r["slug"] + "/")}"><span>{t["next"]}</span>{esc(next_r["title"])}</a>')
    first_line = next((f"l{k+1:03d}.svg" for k, l in enumerate(json.loads((BUILD / "data" / f"{r['slug']}.json").read_text())["lines"]) if l["f"]), "l001.svg")
    body = f"""<article>
<header class="track-head"><p class="crumb"><a class="link" href="/albums/f-t/">f(t)</a><span class="num">{r['n']} / 35</span><span>{esc(c['style'])}</span></p>
<h1 class="track-title eq">{esc(r['title'])}</h1><p class="track-what">{esc(c['what'])}</p>
<p class="track-actions"><button class="button" data-play="{r['slug']}">{ICON_PLAY}{ICON_PAUSE}{t['play']}</button><a class="link" href="{('/scores/' + r['slug'] + '/')}">{t['read_score']}</a><a class="link" href="{STORES['tracks'].get(str(r['n'])) or STORES['album']['apple']}" rel="noopener">{t['on_apple']}</a></p></header>
<canvas class="track-scope" data-slug="{r['slug']}" aria-hidden="true"></canvas>
<div class="track-body"><div>
<section class="fact"><h2>{t['equation']}</h2><p class="formula eq">{c['exact']}</p></section>
<section class="fact"><h2>{t['decides']}</h2><p>{esc(c['decides'])}</p></section>
<section class="fact"><h2>{t['composed']}</h2><p class="small">{esc(c['composed'])}</p></section>
</div><div>
<div class="figure">{fig}</div>
<dl class="meta" style="margin-top:24px">{dl}</dl></div></div>
<section class="section"><div class="section-head"><h2>{t['score_h']}</h2><a class="link" href="{('/scores/' + r['slug'] + '/')}">{t['read_full']}</a></div>
<a class="peek" href="{('/scores/' + r['slug'] + '/')}" aria-label="{esc(t['read_full'])}"><img src="/scores/{r['slug']}/{first_line}" alt="" loading="lazy"></a></section>
<nav class="pager">{''.join(pager)}</nav></article>"""
    ld = {"@context": "https://schema.org", "@type": "MusicRecording", "name": r["title"], "url": f"{ORIGIN}/tracks/{r['slug']}/", "duration": f"PT{int(r['duration'] // 60)}M{int(r['duration'] % 60)}S", "position": r["n"],
          "byArtist": {"@type": "MusicGroup", "name": "x=arcsin y"}, "inAlbum": {"@type": "MusicAlbum", "name": "f(t)", "url": ORIGIN + "/albums/f-t/"}, "audio": {"@type": "AudioObject", "contentUrl": f"{ORIGIN}/audio/{r['slug']}.mp3", "encodingFormat": "audio/mpeg"}}
    return shell(f"/tracks/{r['slug']}/", f"{r['title']} — x=arcsin y", c["what"], body, r["slug"], ld, nav="lib")


def scores_index():
    t = T
    items = []
    for r in TRACKS:
        d = json.loads((BUILD / "data" / f"{r['slug']}.json").read_text())
        first = next((l["f"] for l in d["lines"] if l["f"]), None)
        items.append(f"""<li class="score-item"><div><a class="row-title eq" href="{('/scores/' + r['slug'] + '/')}"><span class="row-n num">{r['n']}</span>{esc(r['title'])}</a>
<span class="list-eq eq">{COPY[r['slug']]['exact']}</span><span class="stat">{r['bars']} {t['bars']} · {len(r['parts'])} {t['parts']} · {r['notes']:,} {t['notes']}</span></div>
<a class="score-thumb" href="{('/scores/' + r['slug'] + '/')}" aria-label="{esc(r['title'])}"><img src="/scores/{r['slug']}/{first}" alt="" loading="lazy"></a></li>""")
    body = f"""<div class="page-head"><h1>{t['scores']}</h1><p>{t['scores_lede']}</p></div><ul class="score-list">{''.join(items)}</ul><div style="height:var(--section)"></div>"""
    return shell("/scores/", f"{t['scores']} — x=arcsin y", t["desc_scores"], body, "scores", nav="scores")


def score_page(r):
    t = T
    d = json.loads((BUILD / "data" / f"{r['slug']}.json").read_text())
    lines = []
    for k, l in enumerate(d["lines"]):
        if l["s"]:
            lines.append(f'<h2>{esc(l["s"])}</h2>')
        if l["f"]:
            lines.append(f'<figure class="line"><img src="/scores/{r["slug"]}/{l["f"]}" alt="" loading="{"eager" if k < 3 else "lazy"}" style="aspect-ratio:{l["a"]}"><i class="tint"></i><i class="head"></i></figure>')
        else:
            lines.append(f'<figure class="line"><p class="silent">{t["silent"]} · {l["b1"] - l["b0"]} {t["bars"]}</p><i class="tint"></i><i class="head"></i></figure>')
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", r["slug"])
    body = f"""<div class="track-head"><p class="crumb"><a class="link" href="/scores/">{t['scores']}</a><a class="link" href="{('/tracks/' + r['slug'] + '/')}">{t['open_track']}</a><span class="num">{r['bars']} {t['bars']} · {len(r['parts'])} {t['parts']} · {r['bpm']} BPM · {esc(short_key(r['key']))}</span></p>
<h1 class="track-title score-title eq">{esc(r['title'])}</h1>
<p class="track-actions"><button class="button" data-play="{r['slug']}">{ICON_PLAY}{ICON_PAUSE}{t['play_score']}</button><label class="follow"><input type="checkbox" checked>{t['follow']}</label></p></div>
<section class="score-eq"><h2>{t['equation']}</h2><p class="formula eq">{COPY[r['slug']]['exact']}</p><h2>{t['decides']}</h2><p class="decides">{esc(COPY[r['slug']]['decides'])}</p></section>
<p class="score-note">{esc(t['score_note'])}</p>
<p class="dl"><a class="link" href="/scores/{r['slug']}/score.pdf" download="x-arcsin-y-{safe}.pdf">{t['dl_pdf']}</a><a class="link" href="/scores/{r['slug']}/score.musicxml" download="x-arcsin-y-{safe}.musicxml">{t['dl_xml']}</a><a class="link" href="/scores/{r['slug']}/score.mid" download="x-arcsin-y-{safe}.mid">{t['dl_mid']}</a><a class="mute" href="/terms/">{t['free_use']}</a></p>
<div class="sheet" data-slug="{r['slug']}"><div class="sheet-in">{''.join(lines)}</div></div>"""
    ld = {"@context": "https://schema.org", "@type": "MusicComposition", "name": r["title"], "url": f"{ORIGIN}/scores/{r['slug']}/", "composer": {"@type": "MusicGroup", "name": "x=arcsin y"}}
    return shell(f"/scores/{r['slug']}/", f"{r['title']} {t['sheet_for']} — x=arcsin y", t["desc_score"].format(t=r["title"], p=len(r["parts"]), b=r["bars"]), body, r["slug"], ld, nav="scores")


def prose_page(name):
    content = json.loads((SITE / "content/pages.json").read_text())[name]
    t = T
    body = f'<div class="page-head tight"><h1>{esc(content["title"])}</h1>{"<p>" + esc(content["lede"]) + "</p>" if content.get("lede") else ""}</div><div class="prose">{content["html"].replace("{CONTACT}", CONTACT)}</div>'
    return shell(f"/{name}/", f"{content['title']} — x=arcsin y", content["desc"], body, "home", nav="about" if name == "about" else None)


def not_found():
    t = T
    body = f"""<div class="page-head"><h1 class="eq">1/0</h1><p>{t['not_found']} {t['not_found_p']}</p><p><a class="link" href="/">{t['home']}</a></p></div>"""
    page = shell("/", "1/0 — x=arcsin y", t["not_found"], body)
    page = re.sub(r'<link rel="(canonical|alternate)"[^>]*>\n', "", page)
    return page.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n<meta name="robots" content="noindex">', 1)


def og_image(name, title, spark=None, sub="x=arcsin y"):
    out = DIST / "assets/og" / f"{name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    S = 2
    W, H = 1200 * S, 630 * S
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    path = "/System/Library/Fonts/HelveticaNeue.ttc"
    size = 200 * S
    font = ImageFont.truetype(path, size, index=10)
    while d.textlength(title, font=font) > W * .84 and size > 40:
        size -= 4 * S
        font = ImageFont.truetype(path, size, index=10)
    box = d.textbbox((0, 0), title, font=font)
    base = H * .46
    d.text(((W - (box[2] - box[0])) / 2 - box[0], base - (box[3] + box[1]) / 2), title, font=font, fill="#0d0d0d")
    if spark:
        n = len(spark)
        x0, x1, y0, h = W * .08, W * .92, H * .84, H * .14
        head = int(n * .382)
        pts = [(x0 + (x1 - x0) * i / (n - 1), y0 - spark[i] ** 2 * h) for i in range(n)]
        d.line(pts[head:], fill="#dcdcdc", width=3 * S, joint="curve")
        d.line(pts[:head + 1], fill="#0d0d0d", width=3 * S, joint="curve")
        r = 11 * S
        d.ellipse([pts[head][0] - r, pts[head][1] - r, pts[head][0] + r, pts[head][1] + r], fill="#0d0d0d")
    small = ImageFont.truetype(path, 30 * S, index=10)
    d.text((W * .08, H * .885), sub, font=small, fill="#6b6b6b")
    im.resize((1200, 630), Image.LANCZOS).save(out, optimize=True)


def write(path, text):
    p = DIST / path.lstrip("/")
    if path.endswith("/"):
        p = p / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def sync_tree(src, dst):
    """Hard-link large generated files so a rebuild costs nothing."""
    for root, _, files in os.walk(src):
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for f in files:
            a, b = Path(root) / f, dst / rel / f
            if b.exists():
                b.unlink()
            os.link(a, b)


def main():
    global VERSION
    keep = DIST / "assets" / "og"
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "assets" / "fonts").mkdir(parents=True)
    (DIST / "assets" / "img").mkdir(parents=True)
    for name in ("audio", "data", "figures", "scores"):
        sync_tree(BUILD / name, DIST / name)
    pdf = BUILD / "pdf"
    if pdf.exists():
        for f in pdf.glob("*.pdf"):
            os.link(f, DIST / "scores" / f.stem / "score.pdf")
    shutil.copy(SITE / "src/site.css", DIST / "assets/site.css")
    shutil.copy(SITE / "src/app.js", DIST / "assets/app.js")
    shutil.copy(SITE / "src/fonts/inter.woff2", DIST / "assets/fonts/inter.woff2")
    shutil.copy(SITE / "src/_headers", DIST / "_headers")
    VERSION = hashlib.sha256((SITE / "src/app.js").read_bytes() + (SITE / "src/site.css").read_bytes()).hexdigest()[:10]
    # /assets is cached as immutable: a new cover needs a new file name (the -r2 in these names)
    cover = source("cover")
    for size in (1200, 600):
        Image.open(cover).convert("RGB").resize((size, size), Image.LANCZOS).save(DIST / f"assets/img/cover-f-t-r2-{size}.jpg", quality=88, optimize=True)
    for size in (1200, 600):
        Image.open(source("cover_delta")).convert("RGB").resize((size, size), Image.LANCZOS).save(DIST / f"assets/img/cover-{SECOND['slug']}-r2-{size}.jpg", quality=88, optimize=True)
    icon = Image.new("RGB", (360, 360), "white")
    font = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", 150, index=10)
    d = ImageDraw.Draw(icon)
    box = d.textbbox((0, 0), "x=", font=font)
    d.text(((360 - box[2] + box[0]) / 2 - box[0], (360 - box[3] + box[1]) / 2 - box[1]), "x=", font=font, fill="#0d0d0d")
    icon.resize((180, 180), Image.LANCZOS).save(DIST / "assets/img/apple-touch-icon.png", optimize=True)
    (DIST / "assets/img/icon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" fill="#fff"/><path d="M4 26C4 12 10 16 16 16s12 4 12-10" fill="none" stroke="#0d0d0d" stroke-width="3" stroke-linecap="round"/><circle cx="16" cy="16" r="4" fill="#0d0d0d"/></svg>')
    pages = []
    write("/", home())
    write("/library/", library())
    write("/albums/", albums())
    write("/albums/f-t/", album())
    write(f"/albums/{SECOND['slug']}/", second_album())
    write("/scores/", scores_index())
    for name in ("about", "terms", "privacy"):
        write(f"/{name}/", prose_page(name))
    for r in TRACKS:
        write(f"/tracks/{r['slug']}/", track(r))
        write(f"/scores/{r['slug']}/", score_page(r))
    (DIST / "404.html").write_text(not_found(), encoding="utf-8")
    for r in TRACKS:
        og_image(r["slug"], r["title"], r["spark"], "x=arcsin y · f(t)")
    og_image("home", "x=arcsin y", TRACKS[33]["spark"], "Every equation has a sound.")
    og_image("album-f-t", "f(t)", None, "x=arcsin y · 35 tracks")
    og_image("album-" + SECOND["slug"], SECOND["title"], None, "x=arcsin y · 35 tracks")
    og_image("scores", "x=arcsin y", None, "All 35 scores are public.")
    paths = ["/", "/library/", "/albums/", "/albums/f-t/", f"/albums/{SECOND['slug']}/", "/scores/", "/about/", "/terms/", "/privacy/"] + [f"/tracks/{r['slug']}/" for r in TRACKS] + [f"/scores/{r['slug']}/" for r in TRACKS]
    urls = "".join(f"<url><loc>{ORIGIN}{p}</loc></url>" for p in paths)
    (DIST / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {ORIGIN}/sitemap.xml\n")
    n = sum(1 for _ in DIST.rglob("*") if _.is_file())
    size = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"{n} files, {size / 1e6:.0f} MB, largest {max((p.stat().st_size for p in DIST.rglob('*') if p.is_file())) / 1e6:.1f} MB")


VERSION = "dev"

if __name__ == "__main__":
    main()
