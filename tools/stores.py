#!/usr/bin/env python3
"""Store links for the album and each track, read from Apple's public lookup. Written to site/data/stores.json."""
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


def main():
    with urllib.request.urlopen(f"https://itunes.apple.com/lookup?id={ALBUM_ID}&entity=song&country=us", timeout=30) as r:
        rows = json.load(r)["results"]
    album = next(x for x in rows if x.get("wrapperType") == "collection")
    songs = [x for x in rows if x.get("wrapperType") == "track"]
    if len(songs) != 35:
        raise SystemExit(f"expected 35 tracks, got {len(songs)}")
    tracks = {str(x["trackNumber"]): clean(x["trackViewUrl"]) for x in songs}
    OUT.write_text(json.dumps({"album": {"apple": clean(album["collectionViewUrl"]), "spotify": SPOTIFY, "amazon": AMAZON, "all": ALL_STORES}, "tracks": tracks}, indent=1))
    index = json.loads((OUT.parent / "tracks.json").read_text())
    bad = [(t["n"], t["title"], s["trackName"]) for t in index for s in songs if s["trackNumber"] == t["n"] and s["trackName"].lower() != t["title"].lower()]
    print("title differences between this site and Apple:", bad)


if __name__ == "__main__":
    main()
