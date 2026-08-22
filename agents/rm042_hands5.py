"""RM-042 — MAX_HANDS_PER_DAY=5 probe (A/B variant, not committed).

Labor ceiling search: 3 beats 2, 4 beats 3. Does 5 (fibonacci cost 5 for the
5th hire) still pay, or is that the crossover? Everything else matches
committed defaults.

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
        max_hands_per_day=5,
    )
