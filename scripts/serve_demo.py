#!/usr/bin/env python3
"""Serve a live kaggriculture match with subtitle-style captions.

Runs one episode (stdlib-only + kaggle_environments), annotates every step's
actions into plain-language captions (scripts/annotate_replay.py), and serves
the bundled visualizer full-screen with a thin, semi-transparent subtitle bar
at the bottom showing the current step's actions + market prices for both
farms — like video subtitles. Read-only overlay; the game itself is untouched.

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

# Subtitle overlay: full-screen game + a thin caption bar at the bottom.
# pointer-events:none so it never blocks clicks on the board.
OVERLAY = r"""
<style>
  #kaggle-subtitle {
    position: fixed; left: 50%; transform: translateX(-50%); bottom: 10px;
    max-width: 94%; box-sizing: border-box; z-index: 99999;
    background: rgba(0, 0, 0, 0.78); color: #f2f4f8;
    border-radius: 8px; padding: 8px 14px;
    font: 12.5px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
    text-align: left; pointer-events: none;
  }
  #kaggle-subtitle .head { color: #ffd479; font-weight: 600; margin-bottom: 2px; }
  #kaggle-subtitle .p0 { color: #6fb7ff; }
  #kaggle-subtitle .p1 { color: #ff8f8f; }
  #kaggle-subtitle .money { color: #ffd479; }
  #kaggle-subtitle .act { color: #e6e9ef; }
</style>
<div id="kaggle-subtitle"><div class="head">Loading…</div></div>
<script>
(function () {
  function boot() {
    var c = document.getElementById('kaggle-subtitle');
    if (!c) return;
    var ann = window.__kaggle_annotations__ || null;

    // The bundle updates .turn-total with the current STEP (day*turns+hour).
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
      if (!ann) { c.innerHTML = '<div class="head">No annotations found.</div>'; return; }
      var d = ann[currentStep()];
      if (!d) return;
      var html = '<div class="head">Day ' + d.day + ' · Hour ' + d.hour + ' · Step ' + d.step + '</div>';
      var names = ['Player 1', 'Player 2'];
      d.players.forEach(function (p, i) {
        var cls = i === 0 ? 'p0' : 'p1';
        var acts = p.caption.length ? p.caption.join(' · ') : 'no action';
        html += '<div class="' + cls + '">' + (i === 0 ? '▶ ' : '◀ ') + p.name +
                ' <span class="money">$' + Math.round(p.money) + '</span> — <span class="act">' + acts + '</span></div>';
      });
      // compact price line
      var prices = '';
      Object.keys(d.prices || {}).forEach(function (k) {
        prices += k.charAt(0) + k.slice(1).toLowerCase() + ' $' + d.prices[k] + '  ';
      });
      html += '<div class="act">' + prices + '| shops: ' +
              ((d.shops || []).length ? d.shops.join(', ') : 'none') + '</div>';
      c.innerHTML = html;
    }

    render();
    var last = -1;
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
