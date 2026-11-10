"""Where the private inputs live.

The music, the track records and everything generated from them stay out of this repository, so a build reads their
locations from a local JSON file: sources.local.json at the top of this repository, or the file named by XARCSINY_SOURCES.
Values may start with ~. Keys: sheet, masters, records, events (with {track_id}), engine, cover, cover_delta, cover_third, build, dist, wrangler, account_id, check,
albums (the later albums: slug, sheet, titles, masters, slugs, notes).
"""
import json
import os
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]


def _config():
    path = Path(os.environ.get("XARCSINY_SOURCES", SITE / "sources.local.json"))
    if not path.exists():
        raise SystemExit(f"no sources file at {path.name}: see tools/paths.py")
    return json.loads(path.read_text())


def setting(key):
    return _config()[key]


def source(key):
    return Path(setting(key)).expanduser()
