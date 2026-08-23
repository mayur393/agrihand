#!/usr/bin/env python3
"""RM-052A: milk marginal economics by market regime.

Compares the current RM-050 agent (8 cows) against a no-animal variant
across identical seeds. Groups results into good/bad milk-price regimes
to determine if milk is marginally profitable even at low prices.

Usage:
    .venv/bin/python analysis/rm052a_milk_economics.py --episodes 20 --seed 42
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kaggle_environments import make
import importlib.util

# Load the agent module
spec = importlib.util.spec_from_file_location("main", str(ROOT / "main.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def run_episode(agent_fn, seed, episode_steps=720):
    """Run one episode, return (final_bank, milk_price_at_day15, opponent_bank)."""
    env = make("kaggriculture",
               configuration={"episodeSteps": episode_steps, "seed": seed},
               debug=True)
    env.run([agent_fn, "starter"])
    final = env.steps[-1]
    c0 = final[0]["observation"]["farms"][0]["money"]
    c1 = final[1]["observation"]["farms"][1]["money"]

    # Get milk price at day 15
    steps = env.steps
    milk_price = 0
    if len(steps) > 15 * 24:
        obs15 = steps[15 * 24][0]["observation"]
        milk_price = obs15["market"]["prices"].get("MILK", 0)

    return c0, milk_price, c1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    # Agent variants
    cow_agent = m.agent  # current: 8 cows, animals_enabled=True

    def no_animal_agent(obs, configuration=None, **kwargs):
        return m.agent(obs, configuration, animals_enabled=False, **kwargs)

    seeds = list(range(args.seed, args.seed + args.episodes))

    print("Running RM-052A: milk marginal economics")
    print(f"  {len(seeds)} seeds, same seeds for both variants\n")

    results = []  # (seed, cow_bank, no_animal_bank, milk_price, cow_win, no_animal_win)

    for seed in seeds:
        cow_bank, milk_price, opp1 = run_episode(cow_agent, seed)
        no_bank, _, opp2 = run_episode(no_animal_agent, seed)
        # opp should be the same for same seed
        cow_win = cow_bank > opp1
        no_win = no_bank > opp2
        results.append((seed, cow_bank, no_bank, milk_price, cow_win, no_win))
        regime = "GOOD" if milk_price >= 200 else ("MID" if milk_price >= 150 else "BAD")
        print(f"  seed {seed:3d}: milk@15=${milk_price:3d} [{regime}]  "
              f"8-cow=${cow_bank:8,.0f} ({'W' if cow_win else 'L'})  "
              f"no-ani=${no_bank:8,.0f} ({'W' if no_win else 'L'})  "
              f"delta=${cow_bank - no_bank:+,.0f}")

    # Summary by regime
    print(f"\n{'='*70}")
    print("SUMMARY BY MILK-PRICE REGIME")

    good = [(s, c, n, mp, cw, nw) for s, c, n, mp, cw, nw in results if mp >= 200]
    mid = [(s, c, n, mp, cw, nw) for s, c, n, mp, cw, nw in results if 150 <= mp < 200]
    bad = [(s, c, n, mp, cw, nw) for s, c, n, mp, cw, nw in results if mp < 150]

    for label, group in [("GOOD (milk≥$200)", good), ("MID ($150-199)", mid), ("BAD (milk<$150)", bad)]:
        if not group:
            print(f"\n  {label}: no episodes in this regime")
            continue
        cow_banks = [c for _, c, _, _, _, _ in group]
        no_banks = [n for _, _, n, _, _, _ in group]
        deltas = [c - n for _, c, n, _, _, _ in group]
        cow_wins = sum(1 for _, _, _, _, cw, _ in group if cw)
        no_wins = sum(1 for _, _, _, _, _, nw in group if nw)

        print(f"\n  {label}: {len(group)} episodes")
        print(f"    8-cow:   mean ${sum(cow_banks)/len(cow_banks):8,.0f}  "
              f"min ${min(cow_banks):8,.0f}  max ${max(cow_banks):8,.0f}  "
              f"W/L {cow_wins}/{len(group)-cow_wins}")
        print(f"    no-ani:  mean ${sum(no_banks)/len(no_banks):8,.0f}  "
              f"min ${min(no_banks):8,.0f}  max ${max(no_banks):8,.0f}  "
              f"W/L {no_wins}/{len(group)-no_wins}")
        print(f"    delta:   mean ${sum(deltas)/len(deltas):+8,.0f}  "
              f"min ${min(deltas):+8,.0f}  max ${max(deltas):+8,.0f}")

    # Overall
    all_cow = [c for _, c, _, _, _, _ in results]
    all_no = [n for _, _, n, _, _, _ in results]
    all_delta = [c - n for _, c, n, _, _, _ in results]
    all_cow_w = sum(1 for _, _, _, _, cw, _ in results if cw)
    all_no_w = sum(1 for _, _, _, _, _, nw in results if nw)

    print(f"\n{'='*70}")
    print(f"OVERALL: {len(results)} episodes")
    print(f"  8-cow:   mean ${sum(all_cow)/len(all_cow):8,.0f}  "
          f"min ${min(all_cow):8,.0f}  max ${max(all_cow):8,.0f}  "
          f"W/L {all_cow_w}/{len(results)-all_cow_w}")
    print(f"  no-ani:  mean ${sum(all_no)/len(all_no):8,.0f}  "
          f"min ${min(all_no):8,.0f}  max ${max(all_no):8,.0f}  "
          f"W/L {all_no_w}/{len(results)-all_no_w}")
    print(f"  delta:   mean ${sum(all_delta)/len(all_delta):+8,.0f}  "
          f"min ${min(all_delta):+8,.0f}  max ${max(all_delta):+8,.0f}")

    # Key question: is milk profitable in bad regimes?
    if bad:
        bad_delta = [c - n for _, c, n, _, _, _ in bad]
        bad_mean = sum(bad_delta) / len(bad_delta)
        print(f"\n{'='*70}")
        print(f"KEY QUESTION: Is milk profitable in bad regimes (milk < $200)?")
        print(f"  Mean delta (8-cow - no-ani): ${bad_mean:+,.0f}")
        if bad_mean > 0:
            print(f"  ANSWER: YES — milk adds ${bad_mean:+,.0f} even at low prices")
            print(f"  -> Keep cows, close the milk branch")
        else:
            print(f"  ANSWER: NO — milk destroys ${abs(bad_mean):,.0f} at low prices")
            print(f"  -> Test milk-light policy (fewer cows or goose-only)")


if __name__ == "__main__":
    main()
