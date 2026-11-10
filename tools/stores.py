#!/usr/bin/env python3
"""Store links for each album and each track, read from Apple's public lookup. Written to data/stores.json.
The later albums' own links live in content/album-*.json; their track links are looked up from the Apple link there."""
import json
from pathlib import Path
import re
import urllib.request

ALBUM_ID = 6824995962
SPOTIFY = "https://open.spotify.com/album/5CwbvuPIhtz6OtAc7gWGt1"  # from the DistroKid HyperFollow page
AMAZON = "https://www.amazon.com/dp/B0HNPMBM8Q"
ALL_STORES = "https://distrokid.com/hyperfollow/xarcsiny/ft"
OUT = Path(__file__).resolve().parents[1] / "data" / "stores.json"


def clean(url):
    return re.sub(r"[?&]uo=\d+", "", url)


def lookup(album_id):
    with urllib.request.urlopen(f"https://itunes.apple.com/lookup?id={album_id}&entity=song&country=us", timeout=30) as r:
        rows = json.load(r)["results"]
    album = next(x for x in rows if x.get("wrapperType") == "collection")
    songs = [x for x in rows if x.get("wrapperType") == "track"]
    if len(songs) != 35:
        raise SystemExit(f"{album_id}: expected 35 tracks, got {len(songs)}")
    return album, songs


def main():
    index = json.loads((OUT.parent / "tracks.json").read_text())
    album, songs = lookup(ALBUM_ID)
    out = {"album": {"apple": clean(album["collectionViewUrl"]), "spotify": SPOTIFY, "amazon": AMAZON, "all": ALL_STORES},
           "tracks": {str(x["trackNumber"]): clean(x["trackViewUrl"]) for x in songs}, "albums": {}}
    names = {("f-t", x["trackNumber"]): x["trackName"] for x in songs}
    for f in sorted((OUT.parents[1] / "content").glob("album-*.json")):
        a = json.loads(f.read_text())
        _, songs = lookup(int(a["stores"]["apple"].rstrip("/").rsplit("/", 1)[1]))
        out["albums"][a["slug"]] = {"tracks": {str(x["trackNumber"]): clean(x["trackViewUrl"]) for x in songs}}
        names.update({(a["slug"], x["trackNumber"]): x["trackName"] for x in songs})
    OUT.write_text(json.dumps(out, indent=1))
    bad = [(t.get("album", "f-t"), t["n"], t["title"], names[t.get("album", "f-t"), t["n"]]) for t in index if names[t.get("album", "f-t"), t["n"]].lower() != t["title"].lower()]
    print("title differences between this site and Apple:", bad)


if __name__ == "__main__":
    main()
