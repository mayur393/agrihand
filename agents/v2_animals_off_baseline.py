"""Superseded committed baseline (crop-only, animals OFF) — archived at RM-021 Part A.

This is the baseline that was committed before the animals promotion: main.py
as of 2026-08-16 with ANIMALS_ENABLED forced False per call. Frozen for the
historical record and as a self-play opponent; the promotion decision that
superseded it is logged in docs/plan.md (RM-020/RM-021, 2026-08-16).

Engine contract: `agent` is the LAST callable defined in this file
(get_last_callable picks [v for v in env.values() if callable(v)][-1]).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root: main.py

import main as _main


def agent(obs, configuration=None):
    return _main.agent(obs, configuration=configuration, animals_enabled=False)
