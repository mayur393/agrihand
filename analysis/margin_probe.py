#!/usr/bin/env python3
"""RM-042 — margin profiler for the labor ceiling (dev-only, NOT shipped).

Win rate is saturated above 3 hands; the discriminator is actual final-bank
margin. Plays two candidate/opponent pairs and reports mean paired margin
(candidate - opponent) over full 720-turn episodes, slot-swapped per seed.

Usage:
    .venv/bin/python analysis/margin_probe.py --candidate agents/rm042_hands4.py --opponent agents/rm042_hands3.py --episodes 20
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kaggle_environments import make


def resolve_agent(name: str):
    if name in ("pass", "random", "starter"):
        return name
    path = Path(name)
    if not path.is_absolute():
        path = ROOT / path
    import importlib.util
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.agent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--opponent", required=True)
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--episode-steps", type=int, default=720)
    args = ap.parse_args()

    cand = resolve_agent(args.candidate)
    opp = resolve_agent(args.opponent)

    margins = []
    for g in range(args.episodes):
        ep_seed = args.seed + g
        for seat in (0, 1):
            agents = [cand, opp] if seat == 0 else [opp, cand]
            env = make("kaggriculture",
                       configuration={"episodeSteps": args.episode_steps,
                                      "seed": ep_seed}, debug=True)
            env.run(agents)
            final = env.steps[-1]
            c_idx = 0 if seat == 0 else 1
            o_idx = 1 - c_idx
            c_money = final[c_idx].observation["farms"][c_idx]["money"]
            o_money = final[o_idx].observation["farms"][o_idx]["money"]
            margins.append(c_money - o_money)

    mean = sum(margins) / len(margins)
    sorted_m = sorted(margins)
    med = sorted_m[len(sorted_m) // 2]
    print(f"candidate: {args.candidate} | opponent: {args.opponent}")
    print(f"paired episodes: {len(margins)} | seed: {args.seed}")
    print(f"mean margin: {mean:,.0f} | median margin: {med:,.0f}")
    print(f"min: {sorted_m[0]:,.0f} | max: {sorted_m[-1]:,.0f}")
    print(f"negative-margin count: {sum(1 for m in margins if m < 0)}/{len(margins)}")


if __name__ == "__main__":
    main()
