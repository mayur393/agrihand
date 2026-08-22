#!/usr/bin/env python3
"""Absolute-income benchmark (dev-only, NOT shipped).

Self-play A/B saturates (every variant beats our own baseline 80/0), so win rate
can no longer tell us if we're improving in ABSOLUTE terms. This measures the
committed agent's own final bank against opponents, to compare against the
leaderboard's ~$92k winner mean (RM-040 data). A low absolute income is the real
gap, not our self-play record.

Usage:
    .venv/bin/python analysis/abs_income.py --candidate main.py --opponent starter --episodes 10
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

    banks = []
    for g in range(args.episodes):
        for seat in (0, 1):
            agents = [cand, opp] if seat == 0 else [opp, cand]
            env = make("kaggriculture",
                       configuration={"episodeSteps": args.episode_steps,
                                      "seed": args.seed + g}, debug=True)
            env.run(agents)
            final = env.steps[-1]
            c_idx = 0 if seat == 0 else 1
            banks.append(final[c_idx].observation["farms"][c_idx]["money"])

    mean = sum(banks) / len(banks)
    sorted_b = sorted(banks)
    med = sorted_b[len(sorted_b) // 2]
    print(f"candidate: {args.candidate} | opponent: {args.opponent}")
    print(f"episodes: {len(banks)} | seed: {args.seed}")
    print(f"candidate final bank — mean {mean:,.0f} | median {med:,.0f} "
          f"| min {sorted_b[0]:,.0f} | max {sorted_b[-1]:,.0f}")


if __name__ == "__main__":
    main()
