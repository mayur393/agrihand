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
OVERLAY = r"""
<style>
  html, body { margin: 0; height: 100%; }
  #kaggle-root { display: flex; height: 100vh; }
  /* shrink the visualizer's game column */
  #kaggle-game { flex: 0 0 55%; min-width: 380px; overflow: auto; }
  /* caption panel */
  #kaggle-captions {
    flex: 1; overflow-y: auto; padding: 16px 18px;
    font: 13px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
    background: #0f1115; color: #d7dae0; border-left: 1px solid #2a2e37;
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
<div id="kaggle-root">
  <div id="kaggle-game"></div>
  <div id="kaggle-captions"></div>
</div>
<script>
(function () {
  // move the game into the shrunk column
  function moveGame() {
    var el = document.querySelector('#root, #app, .game, main, [class*="game"]');
    if (!el) return;
    document.getElementById('kaggle-game').appendChild(el);
  }
  var c = document.getElementById('kaggle-captions');
  var ann = null;
  function setStep(step) {
    if (!ann || !ann[step]) return;
    var d = ann[step];
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
    Object.keys(d.prices).forEach(function (k) {
      html += '<span>' + k.charAt(0) + k.slice(1).toLowerCase() + ': $' + d.prices[k] + '</span>';
    });
    if (d.shops.length) {
      html += '<div class="shops">Open shops: ' + d.shops.join(', ') + '</div>';
    } else {
      html += '<div class="shops">No town shops open yet</div>';
    }
    html += '</div>';
    c.innerHTML = html;
  }
  // poll for the app + read annotations from window.__kaggle_annotations__
  var tries = 0;
  (function poll() {
    ann = window.__kaggle_annotations__ || null;
    var el = document.querySelector('#root, #app, .game, main, [class*="game"]');
    if (ann && el) {
      // hook into the visualizer's currentStep if it exposes it
      var w = el.__kaggle && el.__kaggle.step !== undefined ? el.__kaggle.step : 0;
      setStep(0);
      // try to observe a step counter: the bundle sets window.kaggle.step via message
      window.addEventListener('message', function (e) {
        if (e.data && typeof e.data.step === 'number') setStep(e.data.step);
      });
      // fallback: poll a known step element
      setInterval(function () {
        var s = document.querySelector('[class*="step"]');
        if (s) {
          var v = parseInt(s.textContent, 10);
          if (!isNaN(v)) setStep(v);
        }
      }, 300);
    } else if (tries++ < 100) { setTimeout(poll, 100); }
  })();
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
