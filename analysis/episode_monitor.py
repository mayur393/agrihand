#!/usr/bin/env python3
"""Poll a kaggriculture submission's episodes and save NEW rated-episode replays.

DEV-ONLY. Not part of the submission. Idempotent: keeps a JSON manifest of
already-seen episode ids, downloads only new ones, and skips validation
(self-play) episodes (they are not rated and carry no opponent signal).

Usage:
    .venv/bin/python analysis/episode_monitor.py --submission 55695932 --out /home/mayur/Projects/agrihand/data/raw/replays

Runs once per invocation. Pair it with a cron/loop for continuous monitoring.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DEFAULT = ROOT / "data" / "raw" / "replays"
MANIFEST_DEFAULT = OUT_DEFAULT / ".manifest.json"


def run_kaggle(*args):
    """Invoke the kaggle CLI via the venv python (console-script shebang is stale)."""
    py = ROOT / ".venv" / "bin" / "python"
    return subprocess.run(
        [str(py), "-m", "kaggle", "competitions", *args],
        capture_output=True, text=True,
    )


def parse_episodes_csv(text: str):
    """Parse the CLI's --csv output into a list of dicts."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    header = [c.strip() for c in lines[0].split(",")]
    rows = []
    for ln in lines[1:]:
        vals = [c.strip() for c in ln.split(",")]
        rows.append(dict(zip(header, vals)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission", required=True, help="submission id to watch")
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--dry-run", action="store_true", help="don't download, just report")
    args = ap.parse_args()

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = MANIFEST_DEFAULT if args.out == OUT_DEFAULT else out / ".manifest.json"

    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())

    r = run_kaggle("episodes", str(args.submission), "--csv")
    if r.returncode != 0:
        print(f"[monitor] episodes call failed:\n{r.stderr.strip()}")
        return 1
    eps = parse_episodes_csv(r.stdout)
    print(f"[monitor] submission {args.submission}: {len(eps)} episode(s)")

    rated = [e for e in eps if "PUBLIC" in (e.get("type") or "")]
    print(f"[monitor] rated (public) episodes: {len(rated)}")

    new_ids = [e["id"] for e in rated if e["id"] not in manifest]
    if not new_ids:
        print("[monitor] no new rated episodes")
        return 0

    for eid in new_ids:
        if args.dry_run:
            print(f"[monitor] would download replay for episode {eid}")
            continue
        print(f"[monitor] downloading replay for episode {eid} ...")
        r = run_kaggle("replay", str(eid), "-p", str(out))
        if r.returncode != 0:
            print(f"[monitor]   replay download failed: {r.stderr.strip()[:200]}")
            continue
        # find the file it wrote (name is episode-<id>-replay.json)
        target = out / f"episode-{eid}-replay.json"
        if target.exists():
            manifest[eid] = {
                "type": "EPISODE_TYPE_PUBLIC",
                "path": str(target),
            }
        else:
            print(f"[monitor]   downloaded file not found at {target}")

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"[monitor] manifest now tracks {len(manifest)} rated episode(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
