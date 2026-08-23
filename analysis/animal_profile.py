#!/usr/bin/env python3
"""Profile peak animal count + composition for the current agent (dev-only).

Confirms whether multi-animal scaling actually deploys cow/sheep, or whether
the herd stays stuck at one goose due to structure/placement constraints.

Usage:
    .venv/bin/python analysis/animal_profile.py --candidate main.py --opponent starter --episodes 5
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
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
    ap.add_argument("--episodes", type=int, default=5)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    cand = resolve_agent(args.candidate)
    opp = resolve_agent(args.opponent)

    peaks = Counter()
    final_money = []
    for g in range(args.episodes):
        for seat in (0, 1):
            agents = [cand, opp] if seat == 0 else [opp, cand]
            env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": args.seed + g}, debug=True)
            env.run(agents)
            cand_idx = 0 if seat == 0 else 1
            peak = Counter()
            for step in env.steps:
                farm = step[0]["observation"]["farms"][cand_idx]
                c = Counter()
                for row in farm.get("tiles", []):
                    for cell in row:
                        if isinstance(cell, dict) and "animal" in cell:
                            c[cell["animal"]] += 1
                for k, v in c.items():
                    peak[k] = max(peak[k], v)
            peaks[tuple(sorted(peak.items()))] += 1
            final_money.append(env.steps[-1][cand_idx]["observation"]["farms"][cand_idx]["money"])

    print(f"candidate: {args.candidate} | opponent: {args.opponent} | episodes: {args.episodes}")
    print(f"final money mean: {sum(final_money)/len(final_money):,.0f}")
    print(f"peak animal compositions (composition: count of episodes):")
    for comp, n in peaks.most_common():
        print(f"  {dict(comp)}: {n} episodes")


if __name__ == "__main__":
    main()
