"""RM-042 — MAX_HANDS_PER_DAY=6 probe (A/B variant, not committed).

Labor ceiling search continues: find where fibonacci hire cost (6th hire = $8)
finally exceeds marginal production. Everything else matches committed defaults.

`agent` is the LAST callable (engine contract).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as _main


def agent(obs, configuration=None):
    return _main.agent(
        obs,
        configuration=configuration,
        max_hands_per_day=6,
    )
