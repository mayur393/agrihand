#!/usr/bin/env python3
"""Cash-trajectory probe (dev-only, NOT shipped).

Measures the committed agent's money at each day boundary, to decide when land
expansion becomes affordable under the CURRENT economy (4 hands + closest-first
+ premium mix). The old Q4 gate was derived for a much poorer baseline.

Usage:
    .venv/bin/python analysis/cash_trajectory.py --candidate main.py --opponent starter --episodes 10
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kaggle_environments import make


def resolve_agent(name):
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
    ap.add_argument("--candidate", default="main.py")
    ap.add_argument("--opponent", default="starter")
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--episode-steps", type=int, default=720)
    args = ap.parse_args()

    cand = resolve_agent(args.candidate)
    opp = resolve_agent(args.opponent)

    day_money = {d: [] for d in range(31)}
    for g in range(args.episodes):
        for seat in (0, 1):
            agents = [cand, opp] if seat == 0 else [opp, cand]
            env = make("kaggriculture",
                       configuration={"episodeSteps": args.episode_steps,
                                      "seed": args.seed + g}, debug=True)
            env.run(agents)
            c_idx = 0 if seat == 0 else 1
            for step in env.steps:
                day = step[0]["observation"]["day"]
                money = step[0]["observation"]["farms"][c_idx]["money"]
                day_money[day].append(money)

    print(f"candidate: {args.candidate} | opponent: {args.opponent} | "
          f"{len(day_money[0])} seat-episodes")
    print("day | mean money | median")
    for d in range(0, 31, 3):
        vals = sorted(day_money[d])
        if not vals:
            continue
        mean = sum(vals) / len(vals)
        med = vals[len(vals) // 2]
        print(f"{d:3d} | {mean:11,.0f} | {med:7,.0f}")


if __name__ == "__main__":
    main()
