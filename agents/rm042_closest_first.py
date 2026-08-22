"""RM-042 lever #1 — closest-unit-first task assignment (A/B variant, not committed).

Hypothesis: the committed agent assigns the farmer first, then hands, so the
farmer can claim a tile a hand is already standing next to; the hand then walks
far for its second choice. Closest-first matching assigns every unit to its
nearest unclaimed tile in one pass, cutting wasted movement (measured 68.4% of
all unit-turns are MOVEs).

This wrapper flips `closest_first=True` on the committed `main.agent`; every
other default stays identical (animals ON, premium mix, early hire, crop spread,
land OFF). `agent` is the LAST callable (engine contract).
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
        closest_first=True,
    )
