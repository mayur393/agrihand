#!/usr/bin/env python3
"""Serve a live kaggriculture match with per-step captions.

Runs one episode (stdlib-only + kaggle_environments), annotates every step's
actions into plain-language captions (scripts/annotate_replay.py), and serves
the bundled visualizer with:
  - the game board shrunk to ~55% width,
  - a right-side caption panel showing each player's actions + market prices
    for the current step, synced to the visualizer's playback.

Usage:
    .venv/bin/python scripts/serve_demo.py [--steps 720] [--port 8000]
        [--agent agents/demo_hustler.py] [--opponent starter]

Defaults: demo_hustler vs starter for a full 720-turn season. Point --agent at
main.py once v1 exists.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from kaggle_environments import make

ROOT = Path(__file__).resolve().parent.parent
VISUALIZER = (
    ROOT
    / ".venv/lib/python3.12/site-packages/kaggle_environments/envs/kaggriculture/visualizer/default/dist/index.html"
)
ANNOTATOR = ROOT / "scripts" / "annotate_replay.py"

# Overlay: shrink the game, add a caption panel. Injected into <head>.
# The visualizer mounts to #app (width:100%, height:100%, overflow:hidden),
# so we shrink #app directly and pin a caption panel to the right.
OVERLAY = r"""
<style>
  /* shrink the game to ~55% of viewport width */
  #app { width: 55% !important; }
  /* caption panel pinned right */
  #kaggle-captions {
    position: fixed; top: 0; right: 0; bottom: 0; width: 45%;
    overflow-y: auto; padding: 16px 18px; box-sizing: border-box;
    font: 13px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
    background: #0f1115; color: #d7dae0; border-left: 1px solid #2a2e37;
    z-index: 99999;
  }
  #kaggle-captions h1 { font-size: 15px; margin: 0 0 4px; color: #fff; }
  #kaggle-captions .sub { color: #8b90a0; font-size: 12px; margin-bottom: 14px; }
  #kaggle-captions .player { margin: 10px 0 6px; font-weight: 700; color: #6fb7ff; }
  #kaggle-captions .money { color: #ffd479; font-weight: 600; }
  #kaggle-captions ul { margin: 2px 0 6px; padding-left: 18px; }
  #kaggle-captions li { margin: 2px 0; }
  #kaggle-captions .prices { border-top: 1px solid #2a2e37; margin-top: 12px; padding-top: 8px; }
  #kaggle-captions .prices span { display: inline-block; margin: 2px 10px 2px 0; }
  #kaggle-captions .shops { color: #9ee6a1; }
  #kaggle-captions .empty { color: #6b7080; font-style: italic; }
</style>
<div id="kaggle-captions"><div class="empty">Loading captions…</div></div>
<script>
(function () {
  function boot() {
    var c = document.getElementById('kaggle-captions');
    if (!c) return;
    var ann = window.__kaggle_annotations__ || null;

    // The bundle updates .turn-total with the current STEP (day*turns+hour),
    // and .day-total with the day — prefer .turn-total for exact sync.
    function currentStep() {
      var el = document.querySelector('.market-header .turn-total, .turn-total');
      if (el) {
        var m = (el.textContent || '').match(/\d+/);
        if (m) return parseInt(m[0], 10);
      }
      var els = document.querySelectorAll('*');
      for (var i = 0; i < els.length; i++) {
        if (/turn-total|turn-value/.test(els[i].className || '') && els[i].textContent) {
          var mm = (els[i].textContent || '').match(/\d+/);
          if (mm) return parseInt(mm[0], 10);
        }
      }
      return 0;
    }

    function render() {
      if (!ann) { c.innerHTML = '<div class="empty">No annotations found.</div>'; return; }
      var step = currentStep();
      var d = ann[step];
      if (!d) return;
      var html = '<h1>Day ' + d.day + ' · Hour ' + d.hour + ' · Step ' + d.step + '</h1>';
      html += '<div class="sub">Actions this turn (per Kaggriculture rules)</div>';
      d.players.forEach(function (p, i) {
        html += '<div class="player">' + (i === 0 ? '▶ ' : '◀ ') + p.name +
                ' — <span class="money">$' + Math.round(p.money) + '</span></div>';
        if (!p.caption.length) { html += '<div class="empty">no action</div>'; return; }
        html += '<ul>';
        p.caption.forEach(function (x) { html += '<li>' + x + '</li>'; });
        html += '</ul>';
      });
      html += '<div class="prices"><div class="player" style="margin-top:0">Market prices</div>';
      Object.keys(d.prices || {}).forEach(function (k) {
        html += '<span>' + k.charAt(0) + k.slice(1).toLowerCase() + ': $' + d.prices[k] + '</span>';
      });
      html += '<div class="shops">Open shops: ' + ((d.shops || []).length ? d.shops.join(', ') : 'none yet') + '</div>';
      html += '</div>';
      c.innerHTML = html;
    }

    var last = -1;
    render();
    setInterval(function () {
      var s = currentStep();
      if (s !== last || !c.innerHTML) { last = s; render(); }
    }, 250);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
</script>
"""


def run_episode(agent: str, opponent: str, steps: int) -> dict:
    env = make("kaggriculture", debug=True, configuration={"episodeSteps": steps})
    env.run([agent, opponent])
    replay = env.toJSON()
    replay.setdefault("info", {})
    replay["info"]["Agents"] = [{"index": 0, "name": agent}, {"index": 1, "name": opponent}]
    return replay


def annotate(replay: dict) -> list:
    spec = importlib.util.spec_from_file_location("annotate", ANNOTATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return [mod.annotate_step(st, i, [a.get("name", f"Player {i+1}") for i, a in enumerate(replay.get("info", {}).get("Agents", []))])
            for i, st in enumerate(replay.get("steps", []))]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--steps", type=int, default=720)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--agent", default="agents/demo_hustler.py")
    ap.add_argument("--opponent", default="starter")
    args = ap.parse_args()

    if not VISUALIZER.exists():
        raise SystemExit(f"visualizer not found at {VISUALIZER} — reinstall kaggle-environments")

    replay = run_episode(args.agent, args.opponent, args.steps)
    annotations = annotate(replay)

    page = VISUALIZER.read_text(encoding="utf-8")
    payload = json.dumps({"environment": replay})
    ann_payload = json.dumps(annotations)
    script = (
        f"<script>window.kaggle={payload};window.__kaggle_annotations__={ann_payload};</script>"
        + OVERLAY
    )
    page = page.replace("<head>", f"<head>{script}", 1) if "<head>" in page else script + page

    out = Path("/tmp/kaggriculture_demo.html")
    out.write_text(page, encoding="utf-8")
    print(f"Replay: {len(replay['steps'])} steps, {len(annotations)} annotations | saved {out}")

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
