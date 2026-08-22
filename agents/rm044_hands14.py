"""RM-044 — MAX_HANDS_PER_DAY=14 probe (A/B variant, not committed).

Leaderboard winners run peak_crew 14 / total_hires 263; we cap at 4. Fibonacci
hire cost (1,1,2,3,5,8,13,21...) is trivial at ~$30k scale. This tests the
leaderboard's actual crew size against the committed 4-hand cap.

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
        max_hands_per_day=14,
    )
