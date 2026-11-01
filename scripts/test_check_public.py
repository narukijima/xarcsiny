#!/usr/bin/env python3
"""Prove the check fails: build a clean throwaway repository, add one forbidden thing at a time, expect a refusal.
Each case is removed from the tree again before the check runs, because a leak in the history counts the same as one in the tree."""
from pathlib import Path
import subprocess
import sys
import tempfile

CHECK = Path(__file__).resolve().parent / "check_public.py"
ME = ("-c", "user.name=test", "-c", "user.email=1+test@users.noreply.github.com")
CASES = [
    ("x.wav", b"anything"), ("x.mp3", b"anything"), ("src/stem.flac", b"anything"), ("x.mid", b"anything"), ("x.musicxml", b"anything"), ("scores/l001.svg", b"<svg></svg>"), ("scores/x.pdf", b"anything"),
    ("tools/score.py", b"x = 1\n"), ("tracks/a/track.json", b"{}\n"), ("tracks/a/formula.md", b"x\n"), ("engine/core.py", b"x = 1\n"), ("engine" + "2/core.py", b"x = 1\n"),
    ("NOTES.md", b"x\n"), ("records/a.json", b"{}\n"), ("docs/album" + "-9.json", b"{}\n"), ("tools/c" + "999-zzz.py", b"x = 1\n"), ("tools/synth.py", b"x = 1\n"), ("src/fonts/inter.woff2", b"wOF2 not the font"),
    ("tools/stores.py", b"RIFF\x00\x00\x00\x00WAVE"), ("data/tracks.json", b'{"tempo_map": []}\n'), ("data/stores.json", b"<score-partwise version='4.0'>\n"), ("tools/stores.py", b"def cover_geometry():\n    pass\n"), ("data/stores.json", b'{"beat": "1", "inst": "x"}\n'), ("content/pages.json", b'{"a": "<svg></svg>"}\n'), ("data/stores.json", (b"A" * 76 + b"\n") * 30),
    ("tools/stores.py", b"p = '/Users" + b"/someone/x'\n"), ("tools/stores.py", b"p = '~" + b"/studio'\n"), ("tools/stores.py", b"p = '$HO" + b"ME/x'\n"), ("tools/stores.py", b"p = '/Vol" + b"umes/x'\n"), ("content/tracks.json", b'{"t": "C' + b'999_Zzz"}\n'), ("tools/stores.py", b"t = 'gh" + b"p_" + b"a" * 36 + b"'\n"), ("tools/stores.py", b"-----BEGIN " + b"PRIVATE KEY-----\n"),
    ("content/tracks.json", b'{"t": "the album' + b'-9 list"}\n'), ("content/tracks.json", b'{"t": "c' + b'999-zzz"}\n'), ("data/stores.json", b"A" * 5000 + b"\n"), ("notes.txt", b"plain\n"),
]


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *ME, *args], check=True, capture_output=True)


def fresh(tmp):
    repo = Path(tempfile.mkdtemp(dir=tmp))
    git(repo, "init", "-q", "-b", "main")
    (repo / "worker.js").write_text("export default {};\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "clean")
    return repo


def refused(repo):
    return subprocess.run([sys.executable, str(CHECK), "--repo", str(repo)], capture_output=True).returncode != 0


def main():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        if refused(fresh(tmp)):
            failures.append("a clean repository was refused")
        for path, data in CASES:
            repo = fresh(tmp)
            target = repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "add")
            git(repo, "rm", "-q", "-r", path)
            git(repo, "commit", "-q", "-m", "remove")
            if not refused(repo):
                failures.append(f"not refused: {path} {data[:30]!r}")
        repo = fresh(tmp)
        (repo / "worker.js").write_text("export default { };\n")
        git(repo, "add", "-A")
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=someone@example.com", "commit", "-q", "-m", "add"], check=True)
        if not refused(repo):
            failures.append("a real address was not refused")
    for f in failures:
        print(f)
    print(f"{len(CASES) + 2} cases, {len(failures)} failures")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
