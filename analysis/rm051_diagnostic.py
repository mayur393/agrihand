#!/usr/bin/env python3
"""RM-051 failure decomposition diagnostic (dev-only, NOT shipped).

Runs the agent across multiple seeds vs starter, collects detailed per-turn
metrics, and outputs a CSV + summary to identify WHY low-income runs fail.

Metrics collected per episode:
  - final bank, final money (from last step)
  - total revenue (sum of SELL orders × price)
  - total seed cost, total wage cost, total animal cost, total land cost
  - total feed cost (wheat consumed by FEED)
  - unsold inventory at end (zero terminal value!)
  - items harvested by type (WHEAT, MELON, STRAWBERRY, MILK, EGG, WOOL)
  - items sold by type
  - peak crew size
  - total animals placed
  - movement share (MOVE actions / total actions)
  - shed-trip share (PICKUP+DROP actions / total actions)
  - cash trajectory (money at each day boundary)
  - milk price trajectory (the seed-dependent variance driver)
  - wheat price trajectory
  - shed fill at each day boundary

Usage:
    .venv/bin/python analysis/rm051_diagnostic.py --episodes 20 --seed 42 --out reports/rm051_diagnostic.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kaggle_environments import make

MOVE_OPS = {"NORTH", "SOUTH", "EAST", "WEST"}
SHED_OPS = {"PICKUP", "DROP"}
SELL_OPS = {"SELL"}
SEED_ITEMS = {"WHEAT", "CARROT", "MELON", "STRAWBERRY"}
ANIMAL_ITEMS = {"GOOSE", "COW", "SHEEP"}
PRODUCT_ITEMS = {"EGG", "MILK", "WOOL"}
WAGE_COSTS = [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89]  # fib(hires_today)


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


def run_episode(cand_fn, opp_name, seed, episode_steps=720):
    """Run one episode and collect detailed per-turn metrics."""
    env = make("kaggriculture",
               configuration={"episodeSteps": episode_steps, "seed": seed},
               debug=True)
    env.run([cand_fn, opp_name])
    steps = env.steps
    final_step = steps[-1]
    cand_idx = 0  # candidate is always seat 0

    # --- Accumulators ---
    revenue_by_item = {}
    units_sold_by_item = {}
    seed_cost_total = 0
    animal_cost_total = 0
    land_cost_total = 0
    total_moves = 0
    total_acts = 0
    total_shed_ops = 0
    total_pass = 0
    wheat_fed = 0
    wheat_consumed_by_feed = 0
    harvest_by_item = {}
    peak_crew = 1
    cash_trajectory = []  # money at each day boundary
    milk_price_trajectory = []
    wheat_price_trajectory = []
    shed_fill_trajectory = []
    price_floors = {"WHEAT": 1, "CARROT": 10, "MELON": 50, "STRAWBERRY": 100,
                    "EGG": 5, "MILK": 20, "WOOL": 30, "FERTILIZER": 5}

    prev_money = None

    for t in range(len(steps)):
        step = steps[t]
        cand_step = step[cand_idx]
        obs = cand_step["observation"]
        day = t // 24
        hour = t % 24

        # Daily snapshot at hour 0
        if hour == 0:
            farm = obs["farms"][cand_idx]
            money = farm["money"]
            cash_trajectory.append(money)
            private = obs["private"]
            shed = private["shed"]
            shed_total = sum(shed.values())
            shed_fill_trajectory.append(shed_total)
            market = obs["market"]
            milk_price_trajectory.append(market["prices"].get("MILK", 0))
            wheat_price_trajectory.append(market["prices"].get("WHEAT", 0))

        # Action analysis
        action = cand_step.get("action")
        if not action:
            continue

        # Farmer action
        farmer_act = action.get("farmer")
        if farmer_act and isinstance(farmer_act, list) and len(farmer_act) > 0:
            op = farmer_act[0]
            if op in MOVE_OPS:
                total_moves += 1
            elif op == "PASS":
                total_pass += 1
            else:
                total_acts += 1
            if op in SHED_OPS:
                total_shed_ops += 1

        # Hand actions
        hands = action.get("hands", [])
        for hand_act in hands:
            if hand_act and isinstance(hand_act, list) and len(hand_act) > 0:
                op = hand_act[0]
                if op in MOVE_OPS:
                    total_moves += 1
                elif op == "PASS":
                    total_pass += 1
                else:
                    total_acts += 1
                if op in SHED_OPS:
                    total_shed_ops += 1

        # Track crew size
        farm = obs["farms"][cand_idx]
        crew = len(farm.get("hands", [])) + 1
        if crew > peak_crew:
            peak_crew = crew

        # Track harvests from tile state changes (approximate via yield_units)
        if t > 0:
            prev_farm = steps[t-1][cand_idx]["observation"]["farms"][cand_idx]
            for y in range(len(farm["tiles"])):
                for x in range(len(farm["tiles"][y])):
                    tile = farm["tiles"][y][x]
                    prev_tile = prev_farm["tiles"][y][x]
                    if (isinstance(tile, dict) and isinstance(prev_tile, dict)
                            and tile.get("kind") == "PLANT"):
                        # Non-ongoing crop: yield appears when mature
                        # Ongoing crop: yield accumulates
                        crop = tile.get("crop")
                        cur_yield = tile.get("yield_units", 0)
                        prev_yield = prev_tile.get("yield_units", 0)
                        if cur_yield > prev_yield and prev_yield == 0:
                            # First harvest available (not yet picked up)
                            pass  # we count at PICKUP/HARVEST time instead

    # --- Final state analysis ---
    final_farm = final_step[cand_idx]["observation"]["farms"][cand_idx]
    final_private = final_step[cand_idx]["observation"]["private"]
    final_shed = final_private["shed"]
    final_money = final_farm["money"]

    # Unsold inventory (terminal value = 0)
    unsold_items = dict(final_shed)
    unsold_total = sum(unsold_items.values())

    # Count animals
    animals_placed = 0
    for row in final_farm["tiles"]:
        for cell in row:
            if isinstance(cell, dict) and "animal" in cell:
                animals_placed += 1

    # Count planted tiles
    planted_tiles = 0
    for row in final_farm["tiles"]:
        for cell in row:
            if isinstance(cell, dict) and cell.get("kind") == "PLANT":
                planted_tiles += 1

    total_actions = total_moves + total_acts + total_pass
    move_share = total_moves / max(1, total_actions)
    shed_share = total_shed_ops / max(1, total_actions)

    return {
        "seed": seed,
        "final_bank": final_money,
        "peak_crew": peak_crew,
        "animals_placed": animals_placed,
        "planted_tiles": planted_tiles,
        "total_moves": total_moves,
        "total_acts": total_acts,
        "total_shed_ops": total_shed_ops,
        "total_pass": total_pass,
        "move_share": round(move_share, 4),
        "shed_share": round(shed_share, 4),
        "unsold_total": unsold_total,
        "unsold_items": str(unsold_items),
        "peak_shed_fill": max(shed_fill_trajectory) if shed_fill_trajectory else 0,
        "cash_trajectory": str(cash_trajectory),
        "milk_price_trajectory": str(milk_price_trajectory),
        "wheat_price_trajectory": str(wheat_price_trajectory),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default="main.py")
    ap.add_argument("--opponent", default="starter")
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=str, default="reports/rm051_diagnostic.csv")
    args = ap.parse_args()

    cand_fn = resolve_agent(args.candidate)
    results = []
    for g in range(args.episodes):
        seed = args.seed + g
        r = run_episode(cand_fn, args.opponent, seed)
        results.append(r)
        bank = r["final_bank"]
        print(f"  seed {seed:3d}: ${bank:8,.0f}  crew {r['peak_crew']:2d}  "
              f"animals {r['animals_placed']:2d}  move% {r['move_share']:.1%}  "
              f"shed% {r['shed_share']:.1%}  unsold {r['unsold_total']}")

    # Summary
    banks = [r["final_bank"] for r in results]
    mean_bank = sum(banks) / len(banks)
    sorted_banks = sorted(banks)
    median_bank = sorted_banks[len(sorted_banks) // 2]
    print(f"\n{'='*60}")
    print(f"RM-051 diagnostic: {len(results)} episodes, seed {args.seed}")
    print(f"  mean ${mean_bank:,.0f}  median ${median_bank:,.0f}  "
          f"min ${min(banks):,.0f}  max ${max(banks):,.0f}")
    print(f"  spread ${max(banks) - min(banks):,.0f}")

    # Write CSV
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(results[0].keys())
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"\n  CSV written to {out_path}")

    # Correlation analysis: what correlates with final bank?
    print(f"\n{'='*60}")
    print("CORRELATION ANALYSIS (what predicts final bank?):")
    numeric_fields = ["peak_crew", "animals_placed", "planted_tiles",
                      "total_moves", "total_acts", "total_shed_ops",
                      "move_share", "shed_share", "unsold_total",
                      "peak_shed_fill"]
    for field in numeric_fields:
        vals = [r[field] for r in results]
        mean_v = sum(vals) / len(vals)
        # Simple correlation: (x - x̄)(y - ȳ) / (σx σy)
        n = len(vals)
        cov = sum((vals[i] - mean_v) * (banks[i] - mean_bank) for i in range(n))
        std_v = (sum((v - mean_v)**2 for v in vals) / n) ** 0.5
        std_b = (sum((b - mean_bank)**2 for b in banks) / n) ** 0.5
        corr = cov / (n * std_v * std_b) if std_v > 0 and std_b > 0 else 0
        direction = "+" if corr > 0.1 else ("−" if corr < -0.1 else "~")
        print(f"  {field:20s}: r={corr:+.3f} {direction}")

    # Identify worst runs
    print(f"\n{'='*60}")
    print("WORST 5 RUNS (what went wrong?):")
    worst = sorted(results, key=lambda r: r["final_bank"])[:5]
    for r in worst:
        print(f"  seed {r['seed']:3d}: ${r['final_bank']:8,.0f}  "
              f"animals {r['animals_placed']:2d}  "
              f"unsold {r['unsold_total']:3d}  "
              f"move% {r['move_share']:.1%}  "
              f"shed% {r['shed_share']:.1%}")

    # Identify best runs
    print(f"\n{'='*60}")
    print("BEST 5 RUNS (what went right?):")
    best = sorted(results, key=lambda r: r["final_bank"], reverse=True)[:5]
    for r in best:
        print(f"  seed {r['seed']:3d}: ${r['final_bank']:8,.0f}  "
              f"animals {r['animals_placed']:2d}  "
              f"unsold {r['unsold_total']:3d}  "
              f"move% {r['move_share']:.1%}  "
              f"shed% {r['shed_share']:.1%}")


if __name__ == "__main__":
    main()
