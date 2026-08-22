"""RM-041 variant #1 — strawberry-heavy crop mix (A/B variant, not committed).

RM-040's rating-controlled regression found strawberry the clean positive lever
(+$144/unit) vs wheat (-$78) and melon (-$106). This weights the mix 2:1:1 toward
strawberry: 50% strawberry, 25% wheat, 25% melon. Everything else matches the
committed defaults (animals ON, premium mix, early hire, crop spread, land OFF,
closest-first ON).

`agent` is the LAST callable (engine contract).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root: main.py

import main as _main

MIX = ("STRAWBERRY", "STRAWBERRY", "WHEAT", "MELON")


def agent(obs, configuration=None):
    return _main.agent(
        obs,
        configuration=configuration,
        crop_mix=MIX,
    )
