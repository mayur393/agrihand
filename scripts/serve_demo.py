#!/usr/bin/env python3
"""Serve a live kaggriculture match to the browser using the bundled visualizer.

Runs one episode (stdlib-only + kaggle_environments) between the agents given on
the CLI, then serves the kaggle-environments visualizer HTML with the replay
embedded as `window.kaggle.environment`.

Usage:
    .venv/bin/python scripts/serve_demo.py [--steps 720] [--port 8000] [--agent main.py] [--opponent random]

Defaults: pass vs random for a quick visual check. Point --agent at main.py once v1 exists.
"""
from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from kaggle_environments import make

VISUALIZER = (
    Path(__file__).resolve().parent.parent
    / ".venv/lib/python3.12/site-packages/kaggle_environments/envs/kaggriculture/visualizer/default/dist/index.html"
)


def run_episode(agent: str, opponent: str, steps: int) -> dict:
    env = make("kaggriculture", debug=True, configuration={"episodeSteps": steps})
    env.run([agent, opponent])
    replay = env.toJSON()
    # inject friendly agent names into info so the header shows them
    replay.setdefault("info", {})
    replay["info"]["Agents"] = [{"index": 0, "name": agent}, {"index": 1, "name": opponent}]
    return replay


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--steps", type=int, default=720)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--agent", default="pass")
    ap.add_argument("--opponent", default="random")
    args = ap.parse_args()

    if not VISUALIZER.exists():
        raise SystemExit(f"visualizer not found at {VISUALIZER} — reinstall kaggle-environments")

    replay = run_episode(args.agent, args.opponent, args.steps)
    page = VISUALIZER.read_text(encoding="utf-8")
    payload = json.dumps({"environment": replay})
    # inject window.kaggle before the app boots; if the bundle already defines it, we prepend ours first
    script = f"<script>window.kaggle={payload};</script>"
    page = page.replace("<head>", f"<head>{script}", 1) if "<head>" in page else script + page

    out = Path("/tmp/kaggriculture_demo.html")
    out.write_text(page, encoding="utf-8")
    print(f"Replay: {len(replay['steps'])} steps | saved {out}")

    handler = lambda *a, **kw: SimpleHTTPRequestHandler(*a, directory=str(out.parent), **kw)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    url = f"http://127.0.0.1:{args.port}/{out.name}"
    print(f"Serving at {url}")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
