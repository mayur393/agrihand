#!/usr/bin/env python3
"""RM-042 Step 0 — per-unit action tally (dev-only profiler, NOT shipped).

Measures the waste split before choosing a movement lever: how many turns each
worker spends moving (walking) vs acting (water/harvest/plant/feed/etc.) vs
idle (PASS). The levers in the RM-042 plan fix different waste kinds, so this
number decides which lever is actually worth building.

Reads the action each agent RETURNS per step (not submitted orders), so it
measures the committed policy's behavior, not engine post-processing.

Usage:
    .venv/bin/python analysis/turn_tally.py --candidate main.py --opponent starter --episodes 5
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kaggle_environments import make  # dev-only dep, not shipped

MOVE_DIRS = {"NORTH", "SOUTH", "EAST", "WEST"}
ACT_OPS = {
    "WATER", "HARVEST", "DIG", "PLANT", "BUILD_COOP", "PLACE",
    "PICKUP", "FEED", "CARE", "COLLECT_FERTILIZER", "DROP",
}


def classify_unit(action) -> str:
    """Classify a unit action list into move / act / pass / empty."""
    if not isinstance(action, list) or not action:
        return "empty"
    op = action[0]
    if op == "PASS":
        return "pass"
    if op in MOVE_DIRS:
        return "move"
    if op in ACT_OPS:
        return "act"
    return "unknown"


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
    if not hasattr(mod, "agent"):
        raise SystemExit(f"{path}: no agent(obs) function")
    return mod.agent


def tally_episode(env, cand_idx: int):
    """Tally farmer + hands for the candidate's seat index (0 or 1).

    Returns (farmer_counter, hands_counter, farmer_steps, hand_steps) so the
    caller can report per-unit averages (hands are multiple workers, each with
    its own action every step — summing them against a farmer-step denominator
    would inflate the hand percentage).
    """
    steps = env.steps
    farmer = Counter()
    hands = Counter()
    farmer_steps = max(0, len(steps) - 1)  # skip steps[0] opening pass
    hand_steps = 0
    for t in range(1, len(steps)):
        a = steps[t][cand_idx].get("action") or {}
        f = a.get("farmer") or []
        farmer[classify_unit(f)] += 1
        hs = a.get("hands") or []
        hand_steps += len(hs)
        for h in hs:
            hands[classify_unit(h)] += 1
    return farmer, hands, farmer_steps, hand_steps


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

    tot_farmer = Counter()
    tot_hands = Counter()
    tot_farmer_steps = 0
    tot_hand_steps = 0
    for g in range(args.episodes):
        for seat in (0, 1):
            agents = [candidate, opponent] if seat == 0 else [opponent, candidate]
            env = make("kaggriculture",
                       configuration={"episodeSteps": args.episode_steps,
                                      "seed": args.seed + g}, debug=True)
            env.run(agents)
            cand_idx = 0 if seat == 0 else 1
            farmer, hands, farmer_steps, hand_steps = tally_episode(env, cand_idx)
            tot_farmer.update(farmer)
            tot_hands.update(hands)
            tot_farmer_steps += farmer_steps
            tot_hand_steps += hand_steps

    def pct(c, k, denom):
        return c.get(k, 0) / denom * 100 if denom else 0.0

    print(f"candidate: {args.candidate} | opponent: {args.opponent} | "
          f"episodes: {args.episodes}")
    print(f"farmer-steps: {tot_farmer_steps} | hand-steps: {tot_hand_steps}")
    print("\n--- farmer (per farmer-step) ---")
    print(f"  act : {tot_farmer.get('act', 0):6d} ({pct(tot_farmer, 'act', tot_farmer_steps):5.1f}%)")
    print(f"  move: {tot_farmer.get('move', 0):6d} ({pct(tot_farmer, 'move', tot_farmer_steps):5.1f}%)")
    print(f"  pass: {tot_farmer.get('pass', 0):6d} ({pct(tot_farmer, 'pass', tot_farmer_steps):5.1f}%)")
    print("\n--- hands (per hand-step) ---")
    print(f"  act : {tot_hands.get('act', 0):6d} ({pct(tot_hands, 'act', tot_hand_steps):5.1f}%)")
    print(f"  move: {tot_hands.get('move', 0):6d} ({pct(tot_hands, 'move', tot_hand_steps):5.1f}%)")
    print(f"  pass: {tot_hands.get('pass', 0):6d} ({pct(tot_hands, 'pass', tot_hand_steps):5.1f}%)")
    total_act = tot_farmer.get('act', 0) + tot_hands.get('act', 0)
    total_move = tot_farmer.get('move', 0) + tot_hands.get('move', 0)
    total_steps = tot_farmer_steps + tot_hand_steps
    print("\n--- aggregate (all units) ---")
    print(f"  productive act share: {total_act / total_steps:.3f}" if total_steps else "  n/a")
    print(f"  wasted move share: {total_move / total_steps:.3f}" if total_steps else "  n/a")


if __name__ == "__main__":
    main()
