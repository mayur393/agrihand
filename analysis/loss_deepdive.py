#!/usr/bin/env python3
"""Deep-dive on a single rated loss: what did the winner do that we didn't?

DEV-ONLY. For a given episode JSON, compares the two seats' action streams and
state over time, focusing on the structural levers that separate winner from
loser: hires/day, land purchase days, animal purchases, and the crop/animals
mix at end of game.

Usage:
    .venv/bin/python analysis/loss_deepdive.py --episode /home/mayur/Projects/Dataset/96957419.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter


def analyze(path):
    d = json.load(open(path))
    steps = d["steps"]
    agents = d["info"]["Agents"]
    our = next(i for i, a in enumerate(agents) if a["Name"] == "Agrihand")
    opp = 1 - our
    print(f"episode {d['id']}: Agrihand=seat{our} vs {agents[opp]['Name']}=seat{opp}")

    # --- per-seat time series ---
    for seat, label in ((our, "us"), (opp, "opp")):
        hires_by_day = Counter()
        land_days = []
        animals_by_day = Counter()
        crew_peak = 0
        final = None
        for t, step in enumerate(steps):
            farm = step[0]["observation"]["farms"][seat]
            day = t // 24
            hires_by_day[day] = max(hires_by_day[day], farm.get("hires_today", 0))
            crew_peak = max(crew_peak, len(farm.get("hands", [])) + 1)
            if len(farm.get("unlocked_quadrants", [1])) > 1:
                land_days.append(day)
            n_animals = 0
            for row in farm.get("tiles", []):
                for cell in row:
                    if isinstance(cell, dict) and "animal" in cell:
                        n_animals += 1
            animals_by_day[day] = max(animals_by_day[day], n_animals)
            final = farm
        first_land = min(land_days) if land_days else None
        peak_animals = max(animals_by_day.values()) if animals_by_day else 0
        print(f"\n--- {label} (seat {seat}) ---")
        print(f"  final money: {final['money']:,.0f}")
        print(f"  peak crew: {crew_peak}")
        print(f"  first land day: {first_land} | final quadrants: {len(final['unlocked_quadrants'])}")
        print(f"  peak animals: {peak_animals}")
        print(f"  hires per day (day: count): {dict(sorted(hires_by_day.items())) if hires_by_day else 'none'}")
        # final tile composition
        crops = Counter()
        animals = Counter()
        for row in final.get("tiles", []):
            for cell in row:
                if isinstance(cell, dict):
                    if cell.get("kind") == "PLANT":
                        crops[cell.get("crop")] += 1
                    if "animal" in cell:
                        animals[cell.get("animal")] += 1
        print(f"  final crops: {dict(crops)}")
        print(f"  final animals: {dict(animals)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", required=True)
    args = ap.parse_args()
    analyze(args.episode)


if __name__ == "__main__":
    main()
