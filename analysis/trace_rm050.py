#!/usr/bin/env python3
"""Trace one RM-050 candidate run to find the failure mode in low-income seeds."""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(".").resolve()))
from kaggle_environments import make

spec = importlib.util.spec_from_file_location("main", "main.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def run(seed):
    env = make("kaggriculture", configuration={"episodeSteps":720, "seed":seed}, debug=True)
    env.run([m.agent, "starter"])
    return env

def trace(seed):
    env = run(seed)
    cand = 0
    print(f"=== seed {seed} ===")
    last_money = None
    for t in range(0, len(env.steps), 24):
        step = env.steps[t]
        obs = step[cand]["observation"]
        farm = obs["farms"][cand]
        day = t // 24
        animals = Counter()
        structs = Counter()
        for row in farm["tiles"]:
            for cell in row:
                if isinstance(cell, dict):
                    if "animal" in cell:
                        animals[cell["animal"]] += 1
                    if cell.get("kind") in ("COOP","PASTURE"):
                        structs[cell["kind"]] += 1
        money = farm["money"]
        esc = any(isinstance(c,dict) and c.get("kind") in ("COOP","PASTURE") and "animal" not in c
                  for row in farm["tiles"] for c in row if isinstance(c,dict))
        print(f"day {day:2d} money ${money:8,.0f} crew {len(farm['hands'])+1:2d} animals {dict(animals)} structs {dict(structs)}")
        last_money = money
    return last_money

for seed in (8, 7, 3):
    m = trace(seed)
    print(f"  -> final ${m:,.0f}\n")
