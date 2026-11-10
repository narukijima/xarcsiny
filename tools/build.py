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
COPY = json.loads((SITE / "content/tracks.json").read_text())
STORES = json.loads((SITE / "data/stores.json").read_text())
RELEASED = "2026-10-16"
# Every track of the first album has a score: its tracks were frozen as lists of notes. The later ones are built voice by voice in code;
# a track of theirs has a score (r["bars"]) when its notes could be read back from the code and checked against its audio.
FIRST = {"title": "f(t)", "slug": "f-t", "ordinal": "first", "number": "01", "image": "cover-f-t-r2", "cover": "cover", "release_date": RELEASED, "stores": STORES["album"],
         "about": "f(t) means a sound as a function of time, the one thing all 35 tracks have in common. It opens on the plainest curve there is, y=sin(x), and closes on a problem nobody has solved, n→3n+1."}
LATER = [json.loads((SITE / f"content/{name}.json").read_text()) for name in ("album-delta", "album-champernowne")]
ALBUMS = [FIRST] + LATER
ALBUM = {a["slug"]: a for a in ALBUMS}
_rows = json.loads((SITE / "data/tracks.json").read_text())
for i, a in enumerate(ALBUMS):
    a["index"] = i
    a["tracks"] = sorted((r for r in _rows if r.get("album", "f-t") == a["slug"]), key=lambda r: r["n"])
    assert [r["n"] for r in a["tracks"]] == list(range(1, 36)), a["slug"]
    seconds = sum(r["duration"] for r in a["tracks"])
    a["total"], a["minutes"] = f"{int(seconds // 60)}:{int(seconds % 60):02d}", int(seconds // 60)
    a["track_links"] = STORES["tracks"] if a is FIRST else STORES["albums"][a["slug"]]["tracks"]
    for r in a["tracks"]:
        r["album"] = a["slug"]
TRACKS = [r for a in ALBUMS for r in a["tracks"]]  # every track, album by album
SCORED = [r for r in TRACKS if r.get("bars")]
# what a figure is when a track has no plot of its own formula (figures.py falls back to its part of the album cover)
FIGURE_NOTE = {"delta-r-v": "This track's row of the album cover: the level of the sound against what came before, in 35 slices read left to right, top to bottom. Filled: louder than expected. Ring: quieter.",
               "0-123456789101112": "This track's flower on the album cover: the digits of the title walk a line that turns 36° per unit of each digit, until it closes."}
FIGURE_KIND = json.loads((BUILD / "figure-kinds.json").read_text()) if (BUILD / "figure-kinds.json").exists() else {}
PLOTTED = [r for r in TRACKS if FIGURE_KIND.get(r["slug"]) == "formula"]
SOCIAL = [("YouTube", "https://www.youtube.com/@xarcsiny"), ("TikTok", "https://www.tiktok.com/@xarcsiny"), ("Instagram", "https://www.instagram.com/xarcsiny/")]
CONTACT = "contact@xarcsiny.com"
GITHUB = "https://github.com/narukijima/xarcsiny"
ICON_PLAY = '<svg class="i-play" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 1.5v13l11-6.5z"/></svg>'
ICON_PAUSE = '<svg class="i-pause" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 1.5h3.6v13H3zM9.4 1.5H13v13H9.4z"/></svg>'

T = dict(
        lib="Library", albums="Albums", scores="Scores", about="About", about_nav="About", tagline="Every equation has a sound.",
        tap="Or tap one as it falls.", play_random="Play an equation", open_track="About this track", read_score="Read the score", play="Play", listen="Listen to the album", first_album="The first album.",
        album_lede="35 equations, {m} minutes. Every sound in it is calculated: no recordings, no samples.",
        plots="{n} plots, one per equation", plots_more="Open the library", excerpt_t="The scores are public", excerpt_p="{n} scores are here to read, in real notation, moving with the sound.", all_scores="All scores",
        how_t="How it sounds like this", how=[("One equation", "Each track picks one equation and hands it the part you remember: a bass line, a rhythm, the way an echo falls."),
                                         ("Calculated, all of it", "AI composes the track and writes the code. The code computes every sample, including the voices and the accordion."),
                                         ("A person listens", "Naru Kijima listens and decides what stays. Every track here survived that.")], more_about="More about how it works",
        lib_lede="Search by equation, sound or genre. Tap a plot to hear it.", search="Search equations, genres", sort_album="Album order", sort_title="A–Z", sort_slow="Slowest", sort_fast="Fastest", sort_short="Shortest",
        view_list="List", view_grid="Plots", nothing="No equation matches that.", tempo="Tempo", key="Key", meter="Meter", length="Length", genre="Genre", album="Album", label="Label", released="Released", tracks_w="Tracks", credits="Credits",
        decides="What the equation decides", composed="What was composed", equation="The equation", score_h="Score", read_full="Read the full score", prev="Previous", next="Next", track_of="track",
        on_apple="Apple Music", all_stores="All stores", scores_lede="The notes of {n} tracks, in standard notation. Press play and the page follows the sound.",
        score_note_later="These notes were read back from the track's code as it ran: the notes it asked its instruments for or handed to a voice it computes itself, and single sounds whose pitch was measured before the mix. Each part was then checked against its own audio, and only the parts that passed are written. Stereo copies and octave layers share one staff, timing is rounded to values you can read, and whole-mix effects (stutters, stops, reversed bars), pitch bends and filter moves are not written.",
        not_written="Not written here",
        score_note="This is the notation of what the code plays. Stereo copies and octave layers share one staff, empty staves are hidden, and timing is rounded to values you can read. Pitch bends, filter moves and the rest of what the equation does to the sound can't be written here. That part you have to hear.",
        follow="Follow the sound", dl_pdf="PDF", dl_xml="MusicXML", dl_mid="MIDI", silent="Rest", bars="bars", parts="parts", notes="notes", terms="Terms", privacy="Privacy", follow_h="Follow", site_h="Site",
        albums_lede="Three so far, all out.", also_out="Also out", all_albums="All albums", every_album="All",
        about_title="About", not_found="This equation has no solution.", not_found_p="The page you asked for isn't here.", home="Back to the start",
        now_loading="Loading", desc_home="x=arcsin y makes music from equations. Tap an equation to hear it, read every score, and see what the math decides.", desc_lib="All tracks by x=arcsin y: equations you can play, search and read.",
        desc_albums="Albums by x=arcsin y.", desc_scores="Sheet music for x=arcsin y tracks, in standard notation, moving with the sound.", desc_about="How x=arcsin y turns equations into music, and who is behind it.",
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
    data = json.dumps([[r["n"], r["slug"], r["title"], r["hook"], r["duration"], ALBUM[r["album"]]["index"], int(bool(r.get("bars")))] for r in TRACKS], ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    albums = json.dumps([[a["title"], a["image"]] for a in ALBUMS], ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
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
<script id="albums" type="application/json">{albums}</script>
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
    plots = "".join(f'<li><a href="{("/tracks/" + r["slug"] + "/")}" aria-label="{esc(r["title"])}"><img src="/figures/{r["slug"]}.svg" alt="" loading="lazy" width="200" height="200"><span class="cap eq">{esc(r["title"])}</span></a></li>' for r in PLOTTED)
    how = "".join(f"<li><h3>{esc(a)}</h3><p>{esc(b)}</p></li>" for a, b in t["how"])
    sinc = next(r for r in TRACKS if r["slug"] == "sinc")
    tag = t["tagline"]
    lead = 'Every equation<span class="br"> has a sound.</span>'
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
<div><p class="label">{t['first_album']}</p><h2 class="eq"><a href="/albums/f-t/">f(t)</a></h2><p class="lede">{lede(FIRST)}</p>
{listen(FIRST)}
{store_links(FIRST)}</div>
</div>
</section>
<section class="section">
<div class="section-head"><h2>{t['also_out']}</h2><a class="link" href="/albums/">{t['all_albums']}</a></div>
<div class="albums albums-home">{"".join(album_card(a) for a in reversed(LATER))}</div>
</section>
<section class="section">
<div class="section-head"><h2>{t['plots'].format(n=len(PLOTTED))}</h2><a class="link" href="/library/">{t['plots_more']}</a></div>
<ul class="plots">{plots}</ul>
</section>
<section class="section">
<div class="section-head"><h2>{t['excerpt_t']}</h2><a class="link" href="/scores/">{t['all_scores']}</a></div>
<a class="excerpt" href="/scores/sinc/" aria-label="{esc(sinc['title'])}"><img src="/scores/sinc/l007.svg" alt="" loading="lazy"></a>
<p class="mute" style="margin-top:16px;max-width:34em">{t['excerpt_p'].format(n=len(SCORED))}</p>
</section>
<section class="section">
<div class="section-head"><h2>{t['how_t']}</h2><a class="link" href="/about/">{t['more_about']}</a></div>
<ul class="how">{how}</ul>
</section>"""
    ld = {"@context": "https://schema.org", "@type": "MusicGroup", "name": "x=arcsin y", "url": ORIGIN + "/", "genre": ["Electronic", "Dance"], "slogan": "Every equation has a sound.",
          "sameAs": [h for _, h in SOCIAL] + [STORES["album"]["apple"], STORES["album"]["spotify"], GITHUB], "album": [{"@type": "MusicAlbum", "name": "f(t)", "url": ORIGIN + "/albums/f-t/"}] + [{"@type": "MusicAlbum", "name": a["title"], "url": f"{ORIGIN}/albums/{a['slug']}/"} for a in LATER]}
    return shell("/", "x=arcsin y — " + tag, t["desc_home"], body, "home", ld)


def row(r):
    c = COPY[r["slug"]]
    style = c["style"]
    q = f"{r['title']} {c['style']} {re.sub('<[^>]+>', '', c['exact'])} {r.get('reading') or ''} {r['slug']} {ALBUM[r['album']]['title']}".lower()
    return f"""<li class="row" data-slug="{r['slug']}" data-n="{TRACKS.index(r) + 1}" data-album="{r['album']}" data-title="{esc(r['title'])}" data-bpm="{r['bpm']}" data-duration="{r['duration']}" data-q="{esc(q)}">
{thumb(r)}
<div class="row-main"><a class="row-title eq" href="{('/tracks/' + r['slug'] + '/')}"><span class="row-n num">{r['n']}</span>{esc(r['title'])}</a></div>
<span class="c-style mute">{esc(style)}</span><span class="c-spark">{spark_svg(r['spark'])}</span>
<span class="c-bpm mute num">{r['bpm']}</span><span class="c-key mute">{esc(short_key(r['key']))}</span><span class="mute num">{clock(r['duration'])}</span></li>"""


def library():
    t = T
    rows = "".join(row(r) for r in TRACKS)
    body = f"""<div class="page-head"><h1>{t['lib']}</h1><p>{t['lib_lede']}</p></div>
<div class="tools"><input class="search" type="search" placeholder="{esc(t['search'])}" aria-label="{esc(t['search'])}">
<div class="pick"><button class="on" data-album="">{t['every_album']}</button>{"".join(f'<button class="eq" data-album="{a["slug"]}">{esc(a["title"])}</button>' for a in ALBUMS)}</div>
<div class="sort"><button class="on" data-sort="n">{t['sort_album']}</button><button data-sort="title">{t['sort_title']}</button><button data-sort="bpm">{t['sort_slow']}</button><button data-sort="bpmd">{t['sort_fast']}</button><button data-sort="duration">{t['sort_short']}</button></div>
<div class="views"><button class="on" data-view="list">{t['view_list']}</button><button data-view="grid">{t['view_grid']}</button></div></div>
<ul class="rows">{rows}</ul><p class="empty" hidden>{t['nothing']}</p><div style="height:var(--section)"></div>"""
    return shell("/library/", f"{t['lib']} — x=arcsin y", t["desc_lib"], body, "home", nav="lib")


def lede(a):
    return T["album_lede"].format(m=a["minutes"])


def store_links(a):
    names = [("spotify", "Spotify"), ("apple", T["on_apple"]), ("amazon", "Amazon Music"), ("all", T["all_stores"])]
    return '<p class="stores">' + "".join(f'<a class="link" href="{a["stores"][k]}" rel="noopener">{label}</a>' for k, label in names if a["stores"].get(k)) + "</p>"


def listen(a):
    return f'<p class="stores"><button class="button" data-play="{a["tracks"][0]["slug"]}">{ICON_PLAY}{ICON_PAUSE}{T["listen"]}</button></p>'


def title_class(a):
    """The album title is set very large: a longer one gets a smaller step so it stays on one line."""
    n = len(a["title"])
    return "album-split" + (" album-long" if n > 6 else "") + (" album-xlong" if n > 12 else "")


def album_card(a, stores=True):
    path = f"/albums/{a['slug']}/"
    return f"""<div class="{title_class(a)}"><a href="{path}"><img src="/assets/img/{a['image']}-1200.jpg" alt="{esc(a['title'])}" width="1200" height="1200" loading="lazy"></a>
<div><p class="label">Album {a['number']} · {a['release_date']}</p><h2 class="eq"><a href="{path}">{esc(a['title'])}</a></h2><p class="lede">{lede(a)}</p>
{listen(a)}{store_links(a) if stores else ''}</div></div>"""


def albums():
    t = T
    body = f"""<div class="page-head"><h1>{t['albums']}</h1><p>{t['albums_lede']}</p></div>
<div class="albums">{"".join(album_card(a, a is not FIRST) for a in ALBUMS)}</div>"""
    return shell("/albums/", f"{t['albums']} — x=arcsin y", t["desc_albums"], body, "album-f-t", nav="albums")


def album(a):
    t = T
    rows = "".join(row(r) for r in a["tracks"])
    meta = [(t["released"], a["release_date"]), (t["tracks_w"], str(len(a["tracks"]))), (t["length"], a["total"]), (t["label"], "y=sin(x)"), (t["genre"], "Electronic, Dance"), (t["credits"], "prod. Naru Kijima / AI")]
    dl = "".join(f"<dt>{esc(x)}</dt><dd>{esc(y)}</dd>" for x, y in meta)
    path = f"/albums/{a['slug']}/"
    image = f"/assets/img/{a['image']}-1200.jpg"
    intro = "" if a is FIRST else f'<p class="lede">{lede(a)}</p>'
    body = f"""<div class="section" style="padding-top:clamp(32px,6vw,80px)"><div class="{title_class(a)}"><img src="{image}" alt="{esc(a['title'])}" width="1200" height="1200">
<div><p class="label">Album {a['number']} · x=arcsin y</p><h1 class="eq">{esc(a['title'])}</h1>{intro}
{listen(a)}
{store_links(a)}</div></div></div>
<div class="album-meta"><p>{esc(a['about'])}</p><dl class="meta">{dl}</dl></div>
<div style="height:calc(var(--u)*6)"></div>
<ul class="rows">{rows}</ul><div style="height:var(--section)"></div>"""
    ld = {"@context": "https://schema.org", "@type": "MusicAlbum", "name": a["title"], "url": ORIGIN + path, "image": ORIGIN + image, "datePublished": a["release_date"], "numTracks": len(a["tracks"]),
          "byArtist": {"@type": "MusicGroup", "name": "x=arcsin y"}, "track": [{"@type": "MusicRecording", "name": r["title"], "url": f"{ORIGIN}/tracks/{r['slug']}/", "position": r["n"]} for r in a["tracks"]]}
    return shell(path, f"{a['title']} — x=arcsin y", f"{a['title']}, the {a['ordinal']} album by x=arcsin y. {lede(a)}", body, "album-" + a["slug"], ld, nav="albums")


def track(r):
    t = T
    c = COPY[r["slug"]]
    a = ALBUM[r["album"]]
    count = len(a["tracks"])
    album_path = f"/albums/{a['slug']}/"
    score_path = f"/scores/{r['slug']}/"
    prev_r, next_r = a["tracks"][r["n"] - 2] if r["n"] > 1 else None, a["tracks"][r["n"]] if r["n"] < count else None
    fig = (BUILD / "figures" / f"{r['slug']}.svg").read_text()
    note = f'<p class="figure-note">{esc(FIGURE_NOTE[a["slug"]])}</p>' if a["slug"] in FIGURE_NOTE and FIGURE_KIND.get(r["slug"]) != "formula" else ""
    meta = [(t["genre"], c["style"]), (t["tempo"], f"{r['bpm']} BPM"), (t["key"], short_key(r["key"])), (t["meter"], short_meter(r["meter"])), (t["length"], clock(r["duration"])), (t["album"], f"{a['title']} · {r['n']} / {count}")]
    dl = "".join(f"<dt>{esc(x)}</dt><dd>{esc(y)}</dd>" for x, y in meta)
    pager = []
    if prev_r:
        pager.append(f'<a class="eq" href="{("/tracks/" + prev_r["slug"] + "/")}"><span>{t["prev"]}</span>{esc(prev_r["title"])}</a>')
    else:
        pager.append("<span></span>")
    if next_r:
        pager.append(f'<a class="eq" href="{("/tracks/" + next_r["slug"] + "/")}"><span>{t["next"]}</span>{esc(next_r["title"])}</a>')
    score_link = score_section = ""
    if r.get("bars"):
        first_line = next((f"l{k+1:03d}.svg" for k, l in enumerate(json.loads((BUILD / "data" / f"{r['slug']}.json").read_text())["lines"]) if l["f"]), "l001.svg")
        score_link = f'<a class="link" href="{score_path}">{t["read_score"]}</a>'
        score_section = f"""<section class="section"><div class="section-head"><h2>{t['score_h']}</h2><a class="link" href="{score_path}">{t['read_full']}</a></div>
<a class="peek" href="{score_path}" aria-label="{esc(t['read_full'])}"><img src="/scores/{r['slug']}/{first_line}" alt="" loading="lazy"></a></section>"""
    body = f"""<article>
<header class="track-head"><p class="crumb"><a class="link eq" href="{album_path}">{esc(a['title'])}</a><span class="num">{r['n']} / {count}</span><span>{esc(c['style'])}</span></p>
<h1 class="track-title eq">{esc(r['title'])}</h1><p class="track-what">{esc(c['what'])}</p>
<p class="track-actions"><button class="button" data-play="{r['slug']}">{ICON_PLAY}{ICON_PAUSE}{t['play']}</button>{score_link}<a class="link" href="{a['track_links'].get(str(r['n'])) or a['stores']['apple']}" rel="noopener">{t['on_apple']}</a></p></header>
<canvas class="track-scope" data-slug="{r['slug']}" aria-hidden="true"></canvas>
<div class="track-body"><div>
<section class="fact"><h2>{t['equation']}</h2><p class="formula eq">{c['exact']}</p></section>
<section class="fact"><h2>{t['decides']}</h2><p>{esc(c['decides'])}</p></section>
<section class="fact"><h2>{t['composed']}</h2><p class="small">{esc(c['composed'])}</p></section>
</div><div>
<div class="figure">{fig}</div>{note}
<dl class="meta" style="margin-top:24px">{dl}</dl></div></div>
{score_section}
<nav class="pager">{''.join(pager)}</nav></article>"""
    ld = {"@context": "https://schema.org", "@type": "MusicRecording", "name": r["title"], "url": f"{ORIGIN}/tracks/{r['slug']}/", "duration": f"PT{int(r['duration'] // 60)}M{int(r['duration'] % 60)}S", "position": r["n"],
          "byArtist": {"@type": "MusicGroup", "name": "x=arcsin y"}, "inAlbum": {"@type": "MusicAlbum", "name": a["title"], "url": ORIGIN + album_path}, "audio": {"@type": "AudioObject", "contentUrl": f"{ORIGIN}/audio/{r['slug']}.mp3", "encodingFormat": "audio/mpeg"}}
    return shell(f"/tracks/{r['slug']}/", f"{r['title']} — x=arcsin y", c["what"], body, r["slug"], ld, nav="lib")


def scores_index():
    t = T
    items = []
    for r in SCORED:
        d = json.loads((BUILD / "data" / f"{r['slug']}.json").read_text())
        first = next((l["f"] for l in d["lines"] if l["f"]), None)
        items.append(f"""<li class="score-item"><div><a class="row-title eq" href="{('/scores/' + r['slug'] + '/')}"><span class="row-n num">{r['n']}</span>{esc(r['title'])}</a>
<span class="list-eq eq">{COPY[r['slug']]['exact']}</span><span class="stat">{esc(ALBUM[r['album']]['title'])} · {r['bars']} {t['bars']} · {len(r['parts'])} {t['parts']} · {r['notes']:,} {t['notes']}</span></div>
<a class="score-thumb" href="{('/scores/' + r['slug'] + '/')}" aria-label="{esc(r['title'])}"><img src="/scores/{r['slug']}/{first}" alt="" loading="lazy"></a></li>""")
    body = f"""<div class="page-head"><h1>{t['scores']}</h1><p>{t['scores_lede'].format(n=len(SCORED))}</p></div><ul class="score-list">{''.join(items)}</ul><div style="height:var(--section)"></div>"""
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
    note = t["score_note"]
    if r["album"] != "f-t":
        note = t["score_note_later"] + (f" {t['not_written']}: {', '.join(r['unwritten'])}." if r.get("unwritten") else "")
    body = f"""<div class="track-head"><p class="crumb"><a class="link" href="/scores/">{t['scores']}</a><a class="link" href="{('/tracks/' + r['slug'] + '/')}">{t['open_track']}</a><span class="num">{r['bars']} {t['bars']} · {len(r['parts'])} {t['parts']} · {r['bpm']} BPM · {esc(short_key(r['key']))}</span></p>
<h1 class="track-title score-title eq">{esc(r['title'])}</h1>
<p class="track-actions"><button class="button" data-play="{r['slug']}">{ICON_PLAY}{ICON_PAUSE}{t['play_score']}</button><label class="follow"><input type="checkbox" checked>{t['follow']}</label></p></div>
<section class="score-eq"><h2>{t['equation']}</h2><p class="formula eq">{COPY[r['slug']]['exact']}</p><h2>{t['decides']}</h2><p class="decides">{esc(COPY[r['slug']]['decides'])}</p></section>
<p class="score-note">{esc(note)}</p>
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
    for a in ALBUMS:
        for size in (1200, 600):
            Image.open(source(a["cover"])).convert("RGB").resize((size, size), Image.LANCZOS).save(DIST / f"assets/img/{a['image']}-{size}.jpg", quality=88, optimize=True)
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
    for a in ALBUMS:
        write(f"/albums/{a['slug']}/", album(a))
    write("/scores/", scores_index())
    for name in ("about", "terms", "privacy"):
        write(f"/{name}/", prose_page(name))
    for r in TRACKS:
        write(f"/tracks/{r['slug']}/", track(r))
    for r in SCORED:
        write(f"/scores/{r['slug']}/", score_page(r))
    (DIST / "404.html").write_text(not_found(), encoding="utf-8")
    for r in TRACKS:
        og_image(r["slug"], r["title"], r["spark"], "x=arcsin y · " + ALBUM[r["album"]]["title"])
    og_image("home", "x=arcsin y", TRACKS[33]["spark"], "Every equation has a sound.")
    for a in ALBUMS:
        og_image("album-" + a["slug"], a["title"], None, "x=arcsin y · 35 tracks")
    og_image("scores", "x=arcsin y", None, f"{len(SCORED)} scores are public.")
    paths = ["/", "/library/", "/albums/", *(f"/albums/{a['slug']}/" for a in ALBUMS), "/scores/", "/about/", "/terms/", "/privacy/"] + [f"/tracks/{r['slug']}/" for r in TRACKS] + [f"/scores/{r['slug']}/" for r in SCORED]
    urls = "".join(f"<url><loc>{ORIGIN}{p}</loc></url>" for p in paths)
    (DIST / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {ORIGIN}/sitemap.xml\n")
    n = sum(1 for _ in DIST.rglob("*") if _.is_file())
    size = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"{n} files, {size / 1e6:.0f} MB, largest {max((p.stat().st_size for p in DIST.rglob('*') if p.is_file())) / 1e6:.1f} MB")


VERSION = "dev"

if __name__ == "__main__":
    main()
