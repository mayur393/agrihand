#!/usr/bin/env python3
"""Per-unit production attribution (dev-only, NOT shipped).

Counts, per unit slot (0=farmer, 1..n=hands), how many productive ACT actions
each performs vs moves, and how often each carries a load. This tells us whether
a "runner" role (one hand owning shed logistics) would unload the other units,
or whether shed trips are already spread evenly.

Usage:
    .venv/bin/python analysis/unit_attribution.py --candidate main.py --opponent starter --episodes 5
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kaggle_environments import make

MOVE_DIRS = {"NORTH", "SOUTH", "EAST", "WEST"}
ACT_OPS = {"WATER", "HARVEST", "DIG", "PLANT", "BUILD_COOP", "PLACE",
           "PICKUP", "FEED", "CARE", "COLLECT_FERTILIZER", "DROP", "FERTILIZE"}


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


def profile(env, cand_idx):
    steps = env.steps
    per = defaultdict(lambda: Counter())
    loaded_moves = defaultdict(int)
    act_detail = defaultdict(Counter)
    for t in range(1, len(steps)):
        step = steps[t][cand_idx]
        obs = step["observation"]
        private = obs["private"]
        invs = private.get("inventories", [])
        a = step.get("action") or {}
        units = [a.get("farmer") or []] + list(a.get("hands") or [])
        positions = [tuple(obs["farms"][cand_idx]["farmer"])] + \
                    [tuple(h) for h in obs["farms"][cand_idx]["hands"]]
        for i, u in enumerate(units):
            if not u:
                continue
            op = u[0]
            slot = f"farmer" if i == 0 else f"hand{i}"
            if op in MOVE_DIRS:
                per[slot]["move"] += 1
                carry = sum((invs[i] if i < len(invs) else {}).values())
                if carry > 0:
                    loaded_moves[slot] += 1
            elif op in ACT_OPS:
                per[slot]["act"] += 1
                act_detail[slot][op] += 1
            elif op == "PASS":
                per[slot]["pass"] += 1
    return per, loaded_moves, act_detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default="main.py")
    ap.add_argument("--opponent", default="starter")
    ap.add_argument("--episodes", type=int, default=5)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--episode-steps", type=int, default=720)
    args = ap.parse_args()

    cand = resolve_agent(args.candidate)
    opp = resolve_agent(args.opponent)

    per = defaultdict(lambda: Counter())
    loaded_moves = defaultdict(int)
    act_detail = defaultdict(Counter)
    for g in range(args.episodes):
        for seat in (0, 1):
            agents = [cand, opp] if seat == 0 else [opp, cand]
            env = make("kaggriculture",
                       configuration={"episodeSteps": args.episode_steps,
                                      "seed": args.seed + g}, debug=True)
            env.run(agents)
            cand_idx = 0 if seat == 0 else 1
            p, lm, ad = profile(env, cand_idx)
            for k, v in p.items():
                per[k].update(v)
            for k, v in lm.items():
                loaded_moves[k] += v
            for k, v in ad.items():
                act_detail[k].update(v)

    print(f"candidate: {args.candidate} | opponent: {args.opponent} | episodes: {args.episodes}")
    print(f"\n{'slot':8s} {'act':>6s} {'move':>6s} {'loaded-moves':>12s} {'pass':>5s}")
    for slot in sorted(per, key=lambda s: (s == "farmer", s)):
        c = per[slot]
        print(f"{slot:8s} {c.get('act',0):6d} {c.get('move',0):6d} "
              f"{loaded_moves[slot]:12d} {c.get('pass',0):5d}")
    print("\n=== act detail by slot (top ops) ===")
    for slot in sorted(act_detail, key=lambda s: (s == "farmer", s)):
        top = act_detail[slot].most_common(6)
        print(f"  {slot}: {top}")


if __name__ == "__main__":
    main()
