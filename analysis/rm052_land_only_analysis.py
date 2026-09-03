#!/usr/bin/env python3
"""analysis/rm052_land_only_analysis.py — RM-052 NE-only land expansion analysis.

Reports per-episode metrics for both candidate and baseline on identical seeds:
  - Final bank (money at episode end)
  - First land-purchase day (first step where unlocked_quadrants > 1)
  - Tiles planted in NW vs NE quadrant
  - Peak hands count during the episode
  - Movement turns (farmer steps that are N/S/E/W, not PASS or actions)
  - Animal escapes (tiles that held animals then lost them)
  - Runtime failures (non-DONE status)

Also produces a paired W/L/T summary and bank statistics (mean, median, Q1, min, max).

Usage:
    .venv/bin/python analysis/rm052_land_only_analysis.py \\
        --candidate agents/rm052_land_only.py \\
        --baseline main.py \\
        --episodes 40 --seed 1 --episode-steps 720
"""
from __future__ import annotations

import argparse
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kaggle_environments import make


def resolve_agent(name: str):
    """Load an agent callable from a builtin name or a .py file path."""
    if name in ("pass", "random", "starter"):
        return name
    path = Path(name)
    if not path.is_absolute():
        path = ROOT / path
    import importlib.util
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "agent"):
        raise SystemExit(f"{path}: no agent(obs) function found")
    return mod.agent


def _quadrant(x: int, y: int, board_size: int = 10) -> str:
    """Return quadrant label: NW/NE/SW/SE."""
    half = board_size // 2
    if x < half and y < half:
        return "NW"
    if x >= half and y < half:
        return "NE"
    if x < half and y >= half:
        return "SW"
    return "SE"


def _escape_events(steps, player_idx: int = 0) -> list[tuple[int, int, str]]:
    """Detect animal escapes across an episode's recorded steps."""
    events: list[tuple[int, int, str]] = []
    prev: dict[tuple[int, int], str] = {}
    for st in steps:
        farm = st[player_idx].observation["farms"][player_idx]
        cur: dict[tuple[int, int], str] = {}
        for y, row in enumerate(farm["tiles"]):
            for x, t in enumerate(row):
                if isinstance(t, dict) and "animal" in t:
                    cur[(x, y)] = t["animal"]
        for pos, animal in prev.items():
            if pos not in cur:
                events.append((pos[0], pos[1], animal))
        prev = cur
    return events


def _extract_episode_metrics(steps, player_idx: int = 0) -> dict:
    """Extract per-episode metrics from recorded steps."""
    board_size = 10
    first_land_day = None
    nw_planted = 0
    ne_planted = 0
    peak_hands = 0
    movement_turns = 0
    total_turns = 0
    final_bank = 0
    escapes = _escape_events(steps, player_idx)
    runtime_ok = True

    for st in steps:
        obs = st[player_idx].observation
        status = st[player_idx].status
        if status not in ("DONE", "ACTIVE"):
            runtime_ok = False

        farm = obs["farms"][player_idx]
        day = obs["day"]
        private = obs["private"]

        # Track land purchases
        n_unlocked = len(farm.get("unlocked_quadrants", []))
        if n_unlocked > 1 and first_land_day is None:
            first_land_day = day

        # Count hands
        n_hands = len(farm.get("hands", []))
        if n_hands > peak_hands:
            peak_hands = n_hands

        # Count planted tiles per quadrant
        for y, row in enumerate(farm["tiles"]):
            for x, t in enumerate(row):
                if isinstance(t, dict) and t.get("kind") == "PLANT":
                    q = _quadrant(x, y, board_size)
                    if q == "NW":
                        nw_planted += 1
                    elif q == "NE":
                        ne_planted += 1

        # Movement turns: check farmer action
        # We track the final step's farmer position and compare
        total_turns += 1
        final_bank = farm.get("money", 0)

    # Count movement turns by replaying farmer actions
    # (simpler: count steps where farmer's position changed)
    farmer_positions = []
    for st in steps:
        obs = st[player_idx].observation
        farm = obs["farms"][player_idx]
        fx, fy = farm["farmer"]
        farmer_positions.append((fx, fy))

    for i in range(1, len(farmer_positions)):
        if farmer_positions[i] != farmer_positions[i - 1]:
            movement_turns += 1

    # Final bank from last step
    if steps:
        final_obs = steps[-1][player_idx].observation
        final_bank = final_obs["farms"][player_idx].get("money", 0)

    return {
        "final_bank": final_bank,
        "first_land_day": first_land_day,
        "nw_planted": nw_planted,
        "ne_planted": ne_planted,
        "peak_hands": peak_hands,
        "movement_turns": movement_turns,
        "escapes": len(escapes),
        "runtime_ok": runtime_ok,
    }


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval (lower, upper) on win rate."""
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--candidate", default="agents/rm052_land_only.py")
    ap.add_argument("--baseline", default="main.py")
    ap.add_argument("--opponent", default="starter")
    ap.add_argument("--episodes", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--episode-steps", type=int, default=720)
    args = ap.parse_args()

    cand_agent = resolve_agent(args.candidate)
    base_agent = resolve_agent(args.baseline)
    opp = resolve_agent(args.opponent)

    cand_metrics = []
    base_metrics = []
    cand_wins = cand_losses = cand_ties = 0
    escape_episodes = 0
    failure_episodes = 0

    print(f"{'ep':>4} {'seed':>5} | {'cand_bank':>10} {'base_bank':>10} {'diff':>8} "
          f"{'land_day':>8} {'nw':>4} {'ne':>4} {'hds':>4} {'mv':>4} {'esc':>3} | W/L/T")
    print("-" * 100)

    for g in range(args.episodes):
        ep_seed = args.seed + g
        ep_w = ep_l = ep_t = 0
        ep_cand_m = None
        ep_base_m = None

        for seat in (0, 1):
            agents_c = [cand_agent, opp] if seat == 0 else [opp, cand_agent]
            agents_b = [base_agent, opp] if seat == 0 else [opp, base_agent]

            # Run candidate
            env_c = make("kaggriculture",
                         configuration={"episodeSteps": args.episode_steps, "seed": ep_seed},
                         debug=False)
            env_c.run(agents_c)
            c_idx = 0 if seat == 0 else 1
            cand_m = _extract_episode_metrics(env_c.steps, c_idx)

            # Run baseline
            env_b = make("kaggriculture",
                         configuration={"episodeSteps": args.episode_steps, "seed": ep_seed},
                         debug=False)
            env_b.run(agents_b)
            base_m = _extract_episode_metrics(env_b.steps, c_idx)

            if seat == 0:
                ep_cand_m = cand_m
                ep_base_m = base_m

            # Compare
            c_bank = env_c.steps[-1][c_idx].observation["farms"][c_idx]["money"]
            b_bank = env_b.steps[-1][c_idx].observation["farms"][c_idx]["money"]
            # For W/L, compare candidate's bank against its opponent in the same run
            c_opp_idx = 1 - c_idx
            c_opp_bank = env_c.steps[-1][c_opp_idx].observation["farms"][c_opp_idx]["money"]

            if c_bank > c_opp_bank:
                ep_w += 1
            elif c_bank < c_opp_bank:
                ep_l += 1
            else:
                ep_t += 1

            if cand_m["escapes"] > 0:
                escape_episodes += 1
            if not cand_m["runtime_ok"]:
                failure_episodes += 1

            cand_metrics.append(cand_m)
            base_metrics.append(base_m)

        cand_wins += ep_w
        cand_losses += ep_l
        cand_ties += ep_t

        land_day_str = str(ep_cand_m["first_land_day"]) if ep_cand_m else "?"
        diff = ep_cand_m["final_bank"] - ep_base_m["final_bank"] if ep_cand_m and ep_base_m else 0
        print(f"{g+1:4d} {ep_seed:5d} | "
              f"{ep_cand_m['final_bank']:10,} {ep_base_m['final_bank']:10,} {diff:>+8,} "
              f"{land_day_str:>8} {ep_cand_m['nw_planted']:4d} {ep_cand_m['ne_planted']:4d} "
              f"{ep_cand_m['peak_hands']:4d} {ep_cand_m['movement_turns']:4d} "
              f"{ep_cand_m['escapes']:3d} | {ep_w}/{ep_l}/{ep_t}")

    # Summary statistics
    n = len(cand_metrics)
    cand_banks = [m["final_bank"] for m in cand_metrics]
    base_banks = [m["final_bank"] for m in base_metrics]
    diffs = [c - b for c, b in zip(cand_banks, base_banks)]

    cand_banks_sorted = sorted(cand_banks)
    base_banks_sorted = sorted(base_banks)
    diffs_sorted = sorted(diffs)

    q1_idx = n // 4
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Episodes:        {n}")
    print(f"Seeds:           {args.seed}..{args.seed + n - 1}")
    print(f"Opponent:        {args.opponent}")
    print(f"Episode steps:   {args.episode_steps}")
    print()

    print("--- Candidate (rm052_land_only) ---")
    print(f"  Final bank — mean {statistics.mean(cand_banks):>10,.0f} | "
          f"median {cand_banks_sorted[n//2]:>10,} | "
          f"Q1 {cand_banks_sorted[q1_idx]:>10,} | "
          f"min {cand_banks_sorted[0]:>10,} | "
          f"max {cand_banks_sorted[-1]:>10,}")
    print(f"  Land purchased (NE): {sum(1 for m in cand_metrics if m['first_land_day'] is not None)}/{n} episodes")
    land_days = [m["first_land_day"] for m in cand_metrics if m["first_land_day"] is not None]
    if land_days:
        print(f"  First land day — mean {statistics.mean(land_days):.1f} | "
              f"min {min(land_days)} | max {max(land_days)}")
    print(f"  NE planted tiles — mean {statistics.mean([m['ne_planted'] for m in cand_metrics]):.1f} | "
          f"max {max(m['ne_planted'] for m in cand_metrics)}")
    print(f"  NW planted tiles — mean {statistics.mean([m['nw_planted'] for m in cand_metrics]):.1f}")
    print(f"  Peak hands — mean {statistics.mean([m['peak_hands'] for m in cand_metrics]):.1f} | "
          f"max {max(m['peak_hands'] for m in cand_metrics)}")
    print(f"  Movement turns — mean {statistics.mean([m['movement_turns'] for m in cand_metrics]):.1f}")
    print(f"  Animal escapes: {escape_episodes}/{n} episodes")
    print(f"  Runtime failures: {failure_episodes}/{n} episodes")

    print()
    print("--- Baseline (RM-050) ---")
    print(f"  Final bank — mean {statistics.mean(base_banks):>10,.0f} | "
          f"median {base_banks_sorted[n//2]:>10,} | "
          f"Q1 {base_banks_sorted[q1_idx]:>10,} | "
          f"min {base_banks_sorted[0]:>10,} | "
          f"max {base_banks_sorted[-1]:>10,}")

    print()
    print("--- Paired comparison (candidate - baseline) ---")
    print(f"  Bank diff — mean {statistics.mean(diffs):>+10,.0f} | "
          f"median {diffs_sorted[n//2]:>+10,} | "
          f"Q1 {diffs_sorted[q1_idx]:>+10,} | "
          f"min {diffs_sorted[0]:>+10,} | "
          f"max {diffs_sorted[-1]:>+10,}")

    total = cand_wins + cand_losses + cand_ties
    wr = cand_wins / total if total else 0.0
    lb, ub = wilson_ci(cand_wins, total)
    print(f"\n  W/L/T:   {cand_wins}/{cand_losses}/{cand_ties}")
    print(f"  Win rate: {wr:.3f}")
    print(f"  Wilson 95% CI: [{lb:.3f}, {ub:.3f}]")

    print()
    print("--- Gate checks ---")
    gate_pass = True
    if failure_episodes > 0:
        print(f"  FAIL: {failure_episodes} runtime failure(s)")
        gate_pass = False
    else:
        print(f"  PASS: 0 runtime failures")

    if escape_episodes > 0:
        print(f"  FAIL: {escape_episodes} episode(s) with animal escapes")
        gate_pass = False
    else:
        print(f"  PASS: 0 animal escapes")

    ne_purchased = sum(1 for m in cand_metrics if m["first_land_day"] is not None)
    ne_pct = ne_purchased / n * 100 if n else 0
    if ne_purchased == 0:
        print(f"  FAIL: NE never purchased (0/{n})")
        gate_pass = False
    else:
        print(f"  PASS: NE purchased in {ne_purchased}/{n} episodes ({ne_pct:.0f}%)")

    ne_planted_any = sum(1 for m in cand_metrics if m["ne_planted"] > 0)
    if ne_planted_any == 0:
        print(f"  FAIL: NE never planted in (0/{n})")
        gate_pass = False
    else:
        print(f"  PASS: NE planted in {ne_planted_any}/{n} episodes ({ne_planted_any/n*100:.0f}%)")

    print(f"\n  Overall: {'PASS' if gate_pass else 'FAIL'}")
    return 0 if gate_pass else 1


if __name__ == "__main__":
    sys.exit(main())
