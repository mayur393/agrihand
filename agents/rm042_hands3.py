"""RM-042 — MAX_HANDS_PER_DAY=3 probe (A/B variant, not committed).

Movement is now 52% after closest-first; idle is ~0%. More hands in parallel
may convert remaining walking into productive actions (each hand acts in the
same turn as the farmer, so a hand costs coins, not turns). This raises the
daily hire cap from 2 to 3; everything else matches committed defaults.

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
        max_hands_per_day=3,
    )
