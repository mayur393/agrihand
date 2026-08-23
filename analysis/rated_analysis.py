#!/usr/bin/env python3
"""Analyze our rated episodes: outcome, opponent, and loss mechanism.

DEV-ONLY. Reads downloaded replay JSONs and summarizes each rated episode:
winner, our final bank vs opponent, and the structural deltas (crew, tiles,
animals, land) that separate us from the opponent in losses. This is causal
signal on OUR bot, not leaderboard correlation.

Usage:
    .venv/bin/python analysis/rated_analysis.py --replay-dir data/raw/replays
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def seat_summary(replay, seat):
    """Peak crew, tiles planted, animals, land owned, final money for a seat."""
    steps = replay["steps"]
    peak_crew = 0
    peak_animals = 0
    max_land = 1
    peak_tiles = 0
    first_land = None
    for t, step in enumerate(steps):
        farm = step[0]["observation"]["farms"][seat]
        day = t // 24
        peak_crew = max(peak_crew, len(farm.get("hands", [])) + 1)
        max_land = max(max_land, len(farm.get("unlocked_quadrants", [1])))
        if first_land is None and len(farm.get("unlocked_quadrants", [1])) > 1:
            first_land = day
        # peak simultaneous live plants (not cumulative)
        plants = 0
        for row in farm.get("tiles", []):
            for cell in row:
                if isinstance(cell, dict):
                    if cell.get("kind") == "PLANT":
                        plants += 1
                    if "animal" in cell:
                        peak_animals = max(peak_animals, 1)
        peak_tiles = max(peak_tiles, plants)
    final = steps[-1][0]["observation"]["farms"][seat]
    return {
        "final_money": final["money"],
        "peak_crew": peak_crew,
        "tiles_planted": peak_tiles,
        "max_land": max_land,
        "first_land": first_land,
        "has_animal": peak_animals > 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay-dir", default=str(Path(__file__).resolve().parent.parent / "data" / "raw" / "replays"))
    args = ap.parse_args()

    d = Path(args.replay_dir)
    files = sorted(d.glob("episode-*-replay.json"))
    if not files:
        print("no replay files found")
        return

    print(f"{'episode':>9s} {'our_money':>10s} {'opp_money':>10s} {'result':>6s} "
          f"{'our_crew':>8s} {'opp_crew':>8s} {'our_tiles':>9s} {'opp_tiles':>9s} "
          f"{'our_land':>8s} {'opp_land':>8s}")
    wins = losses = ties = 0
    rows = []
    for f in files:
        replay = json.loads(f.read_text())
        eid = f.stem.replace("episode-", "").replace("-replay", "")
        # identify our seat: both agents may be us (self-play) — use name
        info = replay.get("info", {})
        agents = info.get("Agents", [])
        # Our team name on the ladder is "Agrihand". Seat order varies, so
        # find our seat by name; the other seat is the opponent.
        our_seat = None
        for i, a in enumerate(agents):
            if a.get("Name") == "Agrihand":
                our_seat = i
        if our_seat is None:
            # fallback: if we can't find "Agrihand", skip this replay
            continue
        opp_seat = 1 - our_seat

        a = seat_summary(replay, our_seat)
        b = seat_summary(replay, opp_seat)
        if a["final_money"] > b["final_money"]:
            result = "WIN"
            wins += 1
        elif a["final_money"] < b["final_money"]:
            result = "LOSS"
            losses += 1
        else:
            result = "TIE"
            ties += 1

        rows.append((eid, a, b, result, False))
        print(f"{eid:>9s} {a['final_money']:>10,.0f} {b['final_money']:>10,.0f} "
              f"{result:>6s} {a['peak_crew']:>8d} {b['peak_crew']:>8d} "
              f"{a['tiles_planted']:>9d} {b['tiles_planted']:>9d} "
              f"{a['max_land']:>8d} {b['max_land']:>8d}")

    print(f"\nW/L/T: {wins}/{losses}/{ties}")

    # loss-mechanism deltas
    losses_rows = [r for r in rows if r[3] == "LOSS" and not r[4]]
    if losses_rows:
        print(f"\n=== loss deltas (ours minus opponent) — {len(losses_rows)} rated losses ===")
        print(f"{'episode':>9s} {'d_money':>9s} {'d_crew':>7s} {'d_tiles':>8s} {'d_land':>7s}")
        for eid, a, b, _, _ in losses_rows:
            print(f"{eid:>9s} {a['final_money']-b['final_money']:>9,.0f} "
                  f"{a['peak_crew']-b['peak_crew']:>7d} "
                  f"{a['tiles_planted']-b['tiles_planted']:>8d} "
                  f"{a['max_land']-b['max_land']:>7d}")


if __name__ == "__main__":
    main()
