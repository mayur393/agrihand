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
ANNOTATOR = ROOT / "demo" / "annotate_replay.py"

# Subtitle overlay with playback controls. The bundled visualizer does NOT
# self-play in a standalone page: it renders and waits for a parent to send
# postMessage({step:N}). So this overlay IS the playback controller:
#   - a timer advances `step` (speed-selectable), posting {step} to the board,
#   - play/pause toggles the timer,
#   - a range slider scrubs the step,
#   - captions render from the same `step` in lockstep.
# The bar is non-interactive (pointer-events:none) except the controls row.
OVERLAY = r"""
<style>
  #kaggle-subtitle {
    position: fixed; left: 50%; transform: translateX(-50%); bottom: 10px;
    width: min(94%, 1100px); box-sizing: border-box; z-index: 99999;
    background: rgba(10, 12, 16, 0.88); color: #f2f4f8;
    border-radius: 10px; padding: 8px 14px 10px;
    font: 12.5px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
    text-align: left; pointer-events: none;
  }
  #kaggle-subtitle .head { color: #ffd479; font-weight: 600; margin-bottom: 2px; }
  #kaggle-subtitle .p0 { color: #6fb7ff; }
  #kaggle-subtitle .p1 { color: #ff8f8f; }
  #kaggle-subtitle .money { color: #ffd479; }
  #kaggle-subtitle .act { color: #e6e9ef; }
  #kaggle-subtitle .ctrls {
    display: flex; align-items: center; gap: 10px; margin-top: 6px;
    padding-top: 6px; border-top: 1px solid #2a2e37; pointer-events: auto;
  }
  #kaggle-subtitle .ctrls button {
    background: #263041; color: #eef1f6; border: 1px solid #3a4458; border-radius: 6px; padding: 3px 12px;
    font-size: 12px; cursor: pointer;
  }
  #kaggle-subtitle .ctrls button:hover { background: #33415c; }
  #kaggle-subtitle .ctrls input[type=range] { flex: 1; }
  #kaggle-subtitle .ctrls label { font-size: 11px; color: #9aa3b2; }
  #kaggle-subtitle .ctrls select {
    background: #263041; color: #eef1f6; border: 1px solid #3a4458;
    border-radius: 6px; font-size: 12px; padding: 2px 4px;
  }
</style>
<div id="kaggle-subtitle">
  <div class="head" id="ks-head">Loading…</div>
  <div id="ks-body"></div>
  <div class="ctrls">
    <button id="ks-play">⏸</button>
    <label>speed</label>
    <select id="ks-speed">
      <option value="4">0.25×</option>
      <option value="2">0.5×</option>
      <option value="1">1×</option>
      <option value="0.5">2×</option>
      <option value="0.25">4×</option>
    </select>
    <input type="range" id="ks-slider" min="0" max="100" value="0">
  </div>
</div>
<script>
(function () {
  function boot() {
    var root = document.getElementById('kaggle-subtitle');
    if (!root) return;
    var head = document.getElementById('ks-head');
    var body = document.getElementById('ks-body');
    var playBtn = document.getElementById('ks-play');
    var speedSel = document.getElementById('ks-speed');
    var slider = document.getElementById('ks-slider');
    var ann = window.__kaggle_annotations__ || null;
    var total = (ann ? ann.length : 1) - 1;
    var step = 0, playing = true;
    var BASE_MS = 400; // 1× = 400ms per step
    slider.max = total;

    function render() {
      var d = ann && ann[step];
      if (!d) { head.textContent = 'Loading…'; return; }
      head.textContent = 'Day ' + d.day + ' · Hour ' + d.hour + ' · Step ' + d.step + ' / ' + total;
      var html = '';
      d.players.forEach(function (p, i) {
        var cls = i === 0 ? 'p0' : 'p1';
        var acts = p.caption.length ? p.caption.join(' · ') : 'no action';
        html += '<div class="' + cls + '">' + (i === 0 ? '▶ ' : '◀ ') + p.name +
                ' <span class="money">$' + Math.round(p.money) + '</span> — <span class="act">' + acts + '</span></div>';
      });
      var prices = '';
      Object.keys(d.prices || {}).forEach(function (k) {
        prices += k.charAt(0) + k.slice(1).toLowerCase() + ' $' + d.prices[k] + '  ';
      });
      html += '<div class="act">' + prices + '| shops: ' +
              ((d.shops || []).length ? d.shops.join(', ') : 'none') + '</div>';
      body.innerHTML = html;
      slider.value = step;
    }

    function post() { window.postMessage({ step: step }, '*'); render(); }

    function intervalMs() {
      // speed select value is a multiplier (0.25 = slowest/4x time, 4 = fastest)
      return BASE_MS * parseFloat(speedSel.value);
    }

    var timer = null;
    function tick() {
      if (playing) {
        step = step >= total ? 0 : step + 1;
        post();
      }
      timer = setTimeout(tick, intervalMs());
    }
    function start() {
      if (timer) clearTimeout(timer);
      timer = setTimeout(tick, intervalMs());
    }
    function stop() {
      if (timer) { clearTimeout(timer); timer = null; }
    }

    playBtn.addEventListener('click', function () {
      playing = !playing;
      playBtn.textContent = playing ? '⏸' : '▶';
      if (playing) start(); else stop();
    });
    speedSel.addEventListener('change', function () {
      if (playing) start(); // reschedule with the new speed
    });
    slider.addEventListener('input', function () {
      step = parseInt(slider.value, 10);
      post();
    });

    render();
    start();
    // kick the board to step 0 with data
    window.postMessage({ step: 0 }, '*');
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
    ap.add_argument("--agent", default="demo/demo_hustler.py")
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

