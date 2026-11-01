#!/usr/bin/env python3
"""Refuse anything that must not be public, in every file of every commit.

This repository holds the site's code and words. The sound, the scores as files, the code that can regenerate the sound and
private notes live elsewhere. Paths work as an allowlist, so a file nobody thought about fails until someone decides.
A local check run by the pre-push hook adds what can't be named here, because naming it would publish it.

usage: check_public.py [--repo PATH]
"""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys

ALLOWED = re.compile(r"""^(
    README\.md | LICENSE | \.gitignore | worker\.js | wrangler\.jsonc
  | src/(app\.js | site\.css | _headers | fonts/inter\.woff2 | fonts/OFL\.txt)
  | content/(pages | tracks)\.json
  | data/(stores | tracks)\.json
  | tools/(build | deploy | extract | figures | paths | pdf | score_xml | stores)\.py
  | scripts/(check_public | test_check_public)\.py
  | \.githooks/pre-push
  | \.github/workflows/check\.yml
)$""", re.X)
BINARY = {"src/fonts/inter.woff2": "3100e775e8616cd2611beecfa23a4263d7037586789b43f035236a2e6fbd4c62"}
MAX_BYTES = 200_000
FORBIDDEN_NAMES = [
    (r"\.(wav|wave|mp3|flac|aiff?|ogg|opus|m4a|aac|mp4|mov|caf)$", "audio or video"),
    (r"\.(midi?|musicxml|mxl|svg|pdf)$", "generated score"),
    (r"\.(png|jpe?g|gif|webp)$", "generated image"),
    (r"(^|/)(\w*_score|score|base)\.py$", "track code"),
    (r"(^|/)(track|formula)\.", "track record"),
    (r"(^|/)engine\d*(/|\.)", "engine"),
    (r"album[-_]?\d", "album record"),
    (r"(^|/)[a-z]\d{2,3}-[a-z]", "unreleased track"),
]
FORBIDDEN_TEXT = [
    (r"/Users/[A-Za-z]|/home/[a-z]|/Volumes/[A-Za-z]|[A-Z]:\\Users|~/[A-Za-z]|\$HOME/[A-Za-z]", "local path"),
    (r'"account_id"\s*:', "account setting"),
    (r"(?i)album[-_]\d", "album record"),
    (r"(?i)(?<![\w#.-])[a-z]\d{2,3}[-_][a-z]", "unreleased track"),
    (r'"id"\s*:\s*"[a-z]\d', "unreleased track"),
    (r'^\s*def cover_geometry\(|^\s*(from|import)\s+engine\b', "track code"),
    (r"[A-Za-z0-9+/]{4096,}|(?:^[A-Za-z0-9+/=]{60,}\n){20,}", "large encoded blob"),
    (r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}", "GitHub token"),
    (r"sk-[A-Za-z0-9_-]{20,}", "API key"),
    (r"AKIA[0-9A-Z]{16}", "AWS key"),
    (r"xox[abprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"AIza[0-9A-Za-z_-]{30,}", "Google key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
    (r"""(?i)(api[_-]?key|api[_-]?token|secret|password)["']?\s*[:=]\s*["'][^"'\s]{12,}""", "credential"),
]
FORBIDDEN_TEXT = [(re.compile(p, re.M), why) for p, why in FORBIDDEN_TEXT]
FORBIDDEN_NAMES = [(re.compile(p, re.I), why) for p, why in FORBIDDEN_NAMES]
NOT_CODE = [(re.compile(p), why) for p, why in [(r"<score-partwise|<score-timewise|<mei[ >]", "score file content")]]  # the converter's own code may say these
IN_JSON = [(re.compile(p), why) for p, why in [(r'"tempo_map"\s*:|"inst"\s*:|"events"\s*:', "event data"), (r"<svg", "score or figure")]]
MAGIC = [(b"RIFF", "audio"), (b"ID3", "audio"), (b"fLaC", "audio"), (b"OggS", "audio"), (b"FORM", "audio"), (b"MThd", "MIDI"), (b"%PDF", "PDF"), (b"PK\x03\x04", "archive"), (b"\x89PNG", "image"), (b"\xff\xd8\xff", "image")]
AUTHORS = re.compile(r"(^\d+\+[\w-]+@users\.noreply\.github\.com$)|(^noreply@github\.com$)")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


def text_problems(text):
    for rule, why in FORBIDDEN_TEXT:
        hit = rule.search(text)
        if hit:
            yield why, text.count("\n", 0, hit.start()) + 1


def scan_blob(path, data):
    if len(data) > MAX_BYTES:
        yield f"{len(data)} bytes, larger than the limit"
    for magic, what in MAGIC:
        if data.startswith(magic):
            yield f"{what} data"
    if data[4:8] == b"ftyp" or (len(data) > 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0 and path not in BINARY):
        yield "audio or video data"
    if path in BINARY:
        if hashlib.sha256(data).hexdigest() != BINARY[path]:
            yield "binary file changed"
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        yield "binary file outside the list"
        return
    for why, line in text_problems(text):
        yield f"{why} (line {line})"
    if not path.endswith(".py"):
        for rule, why in NOT_CODE:
            if rule.search(text):
                yield why
    if path.endswith(".json"):
        for rule, why in IN_JSON:
            if rule.search(text):
                yield why


def scan(repo):
    problems = []
    commits = git(repo, "rev-list", "--all").decode().split()
    if not commits:
        return ["no commits to check"]
    for ref in git(repo, "for-each-ref", "--format=%(refname)").decode().split():
        for rule, why in FORBIDDEN_NAMES:
            if rule.search(ref):
                problems.append(f"{ref}: {why}")
    for why, line in text_problems(git(repo, "for-each-ref", "--format=%(contents)", "refs/tags").decode()):
        problems.append(f"tag message: {why} (line {line})")
    for commit in commits:
        author, committer, body = git(repo, "show", "-s", "--format=%ae%x00%ce%x00%B", commit).decode().split("\0", 2)
        for mail in (author, committer):
            if not AUTHORS.match(mail):
                problems.append(f"commit {commit[:10]}: address outside the noreply list")
        for why, line in text_problems(body):
            problems.append(f"commit {commit[:10]} message: {why} (line {line})")
    seen = set()
    for commit in commits:
        for row in git(repo, "ls-tree", "-r", "-z", commit).decode().split("\0"):
            if not row:
                continue
            head, path = row.split("\t", 1)
            mode, _, sha = head.split()
            label = f"{path} (commit {commit[:10]})"
            if (path, sha, mode) in seen:
                continue
            seen.add((path, sha, mode))
            if mode == "120000":
                problems.append(f"{label}: symbolic link")
            if not ALLOWED.match(path):
                problems.append(f"{label}: path outside the allowed list")
            for rule, why in FORBIDDEN_NAMES:
                if rule.search(path):
                    problems.append(f"{label}: {why}")
            problems += [f"{label}: {why}" for why in scan_blob(path, git(repo, "cat-file", "blob", sha))]
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=Path(__file__).resolve().parents[1])
    a = ap.parse_args()
    problems = scan(a.repo)
    for p in problems:
        print(p)
    print(f"{len(problems)} problems")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
