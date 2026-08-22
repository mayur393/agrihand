"""Superseded committed baseline (animals ON, wheat/carrot, no hands) — archived at RM-036.

This is the baseline that was committed after RM-021 Part A: ANIMALS_ENABLED=True,
crop_mix=("WHEAT","CARROT"), HIRE_HANDS=False, EARLY_HIRE=False, CROP_SPREAD=False.
Superseded by the RM-036 combo promotion (MELON/STRAWBERRY/WHEAT + early hire +
crop spread). Frozen for self-play and history; the promotion decision is
logged in docs/plan.md (RM-036, 2026-08-16).

`agent` is the LAST callable (engine contract: get_last_callable picks the
last callable in the module).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root: main.py

import main as _main


def agent(obs, configuration=None):
    return _main.agent(
        obs,
        configuration=configuration,
        animals_enabled=True,
        crop_mix=("WHEAT", "CARROT"),
        hire_hands=False,
        early_hire=False,
        crop_spread=False,
    )
