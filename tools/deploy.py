#!/usr/bin/env python3
"""Deploy the built site. The assets folder, the account and a last private check come from the sources file (tools/paths.py).

usage: deploy.py [wrangler arguments, such as --dry-run]
"""
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import SITE, setting, source  # noqa: E402


def main():
    subprocess.run([str(source("check")), "--dist", str(source("dist"))], check=True)
    env = dict(os.environ, CLOUDFLARE_ACCOUNT_ID=setting("account_id"))
    cmd = [str(source("wrangler")), "deploy", "--assets", str(source("dist")), *sys.argv[1:]]
    raise SystemExit(subprocess.run(cmd, cwd=SITE, env=env).returncode)


if __name__ == "__main__":
    main()
