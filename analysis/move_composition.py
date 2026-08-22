#!/usr/bin/env python3
"""RM-042 — movement composition profiler (dev-only, NOT shipped).

Splits MOVE turns by whether the unit is carrying items at the time it moves:
  - move-empty: walking toward a task (fixable by zones/persistence)
  - move-loaded: walking while carrying (mostly shed logistics; fixable by a
    runner role or better shed cycling)

Also reports how often a moving unit is adjacent to the shed (arriving/leaving
logistics) so the shed-shuttle share is explicit rather than guessed.

Usage:
    .venv/bin/python analysis/move_composition.py --candidate main.py --opponent starter --episodes 5
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kaggle_environments import make

MOVE_DIRS = {"NORTH", "SOUTH", "EAST", "WEST"}


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


def _is_shed_adjacent(pos, board_size):
    half = board_size // 2
    return tuple(pos) in {(half - 1, half - 1), (half, half - 1),
                          (half - 1, half), (half, half)}


def profile_episode(env, cand_idx):
    steps = env.steps
    empty = Counter()
    loaded = Counter()
    shed_adj = Counter()
    farmer_steps = 0
    hand_steps = 0
    for t in range(1, len(steps)):
        step = steps[t][cand_idx]
        obs = step["observation"]
        private = obs["private"]
        invs = private.get("inventories", [])
        board = len(obs["farms"][cand_idx]["tiles"])
        a = step.get("action") or {}

        units = [a.get("farmer") or []]
        positions = [tuple(obs["farms"][cand_idx]["farmer"])]
        for hp in obs["farms"][cand_idx]["hands"]:
            units.append(a.get("hands", [])[len(positions) - 1]
                         if len(positions) - 1 < len(a.get("hands", [])) else [])
            positions.append(tuple(hp))

        for i, u in enumerate(units):
            is_farmer = i == 0
            if not u or u[0] not in MOVE_DIRS:
                if is_farmer:
                    farmer_steps += 1
                else:
                    hand_steps += 1
                continue
            carry = sum((invs[i] if i < len(invs) else {}).values())
            if carry > 0:
                loaded["move"] += 1
            else:
                empty["move"] += 1
            if _is_shed_adjacent(positions[i], board):
                shed_adj["move"] += 1
            if is_farmer:
                farmer_steps += 1
            else:
                hand_steps += 1
    return empty, loaded, shed_adj, farmer_steps, hand_steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default="main.py")
    ap.add_argument("--opponent", default="starter")
    ap.add_argument("--episodes", type=int, default=5)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--episode-steps", type=int, default=720)
    args = ap.parse_args()

    candidate = resolve_agent(args.candidate)
    opponent = resolve_agent(args.opponent)

    empty = Counter()
    loaded = Counter()
    shed_adj = Counter()
    farmer_steps = 0
    hand_steps = 0
    for g in range(args.episodes):
        for seat in (0, 1):
            agents = [candidate, opponent] if seat == 0 else [opponent, candidate]
            env = make("kaggriculture",
                       configuration={"episodeSteps": args.episode_steps,
                                      "seed": args.seed + g}, debug=True)
            env.run(agents)
            cand_idx = 0 if seat == 0 else 1
            e, l, s, fs, hs = profile_episode(env, cand_idx)
            empty.update(e)
            loaded.update(l)
            shed_adj.update(s)
            farmer_steps += fs
            hand_steps += hs

    total_moves = empty["move"] + loaded["move"]
    total_steps = farmer_steps + hand_steps
    print(f"candidate: {args.candidate} | opponent: {args.opponent} | episodes: {args.episodes}")
    print(f"total moves: {total_moves} | unit-steps: {total_steps}")
    if total_moves:
        print(f"  move-empty  (to a task):   {empty['move']:6d} ({empty['move']/total_moves*100:5.1f}% of moves)")
        print(f"  move-loaded (logistics):    {loaded['move']:6d} ({loaded['move']/total_moves*100:5.1f}% of moves)")
        print(f"  move while shed-adjacent:   {shed_adj['move']:6d} ({shed_adj['move']/total_moves*100:5.1f}% of moves)")


if __name__ == "__main__":
    main()
