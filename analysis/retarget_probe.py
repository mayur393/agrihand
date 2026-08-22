#!/usr/bin/env python3
"""RM-042 — cross-turn re-targeting probe (dev-only, NOT shipped).

Counts "direction reversals": a unit moves in one direction, then the exact
opposite direction on the next turn (EAST then WEST, or NORTH then SOUTH).
A reversal is the signature of re-targeting — the unit was walking toward one
tile, the assignment changed under it, and it turned around. Lots of reversals
= lever #2 (persistent intent) has teeth; few = the remaining movement is the
geometric floor of walking between distinct tasks.

Usage:
    .venv/bin/python analysis/retarget_probe.py --candidate main.py --opponent starter --episodes 5
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kaggle_environments import make

OPPOSITE = {"NORTH": "SOUTH", "SOUTH": "NORTH", "EAST": "WEST", "WEST": "EAST"}
MOVE_DIRS = set(OPPOSITE)


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


def probe_episode(env, cand_idx):
    steps = env.steps
    prev_dir = {}      # unit slot (0=farmer, 1+=hand) -> last move dir
    prev_pos = {}
    reversals = 0
    moves = 0
    for t in range(1, len(steps)):
        obs = steps[t][cand_idx]["observation"]
        a = steps[t][cand_idx].get("action") or {}
        units = [a.get("farmer") or []] + list(a.get("hands") or [])
        positions = [tuple(obs["farms"][cand_idx]["farmer"])] + \
                    [tuple(h) for h in obs["farms"][cand_idx]["hands"]]
        for i, u in enumerate(units):
            if not u or u[0] not in MOVE_DIRS:
                prev_dir.pop(i, None)
                continue
            moves += 1
            d = u[0]
            if i in prev_dir and prev_dir[i] == OPPOSITE[d]:
                reversals += 1
            prev_dir[i] = d
    return reversals, moves


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

    reversals = 0
    moves = 0
    for g in range(args.episodes):
        for seat in (0, 1):
            agents = [candidate, opponent] if seat == 0 else [opponent, candidate]
            env = make("kaggriculture",
                       configuration={"episodeSteps": args.episode_steps,
                                      "seed": args.seed + g}, debug=True)
            env.run(agents)
            cand_idx = 0 if seat == 0 else 1
            r, m = probe_episode(env, cand_idx)
            reversals += r
            moves += m

    print(f"candidate: {args.candidate} | opponent: {args.opponent} | episodes: {args.episodes}")
    print(f"moves: {moves} | reversals: {reversals}")
    if moves:
        print(f"reversal rate: {reversals/moves*100:.2f}% of moves are immediate turn-arounds")


if __name__ == "__main__":
    main()
