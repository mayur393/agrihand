"""RM-042 — MAX_HANDS_PER_DAY=4 probe (A/B variant, not committed).

Follow-up to the 3-hand promotion: does a 4th hand (fibonacci cost 3) add more
than it costs, or is 3 the ceiling? Everything else matches committed defaults.

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
        max_hands_per_day=4,
    )
