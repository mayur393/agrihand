"""RM-036 leaderboard-informed combo candidate (A/B variant, not committed).

Combination under test (the verified leaderboard pattern, RM-035/leaderboard):
  - ANIMALS_ENABLED=True (already the committed baseline)
  - crop mix ("WHEAT", "MELON", "STRAWBERRY") — the dominant top-bracket mix
    (81% of top rows, ~$92.3k avg), NOT tomato/carrot (RM-017 tested those)
  - HIRE_HANDS=True + EARLY_HIRE=True — day 0-1 unconditional hire, the
    leaderboard norm (98.5% day-0 hire, RM-035), then backlog rule day 2+
  - CROP_SPREAD=True — plant the mix by tile-position hash. Without it the
    PLANT branch always picks the first crop with seeds, which is a wheat
    monoculture (verified 2026-08-16); RM-017's mix A/Bs were silent.

Hard rules respected (inherited from main.py): wheat buffer >= animals*2+5,
M7 shed-room-aware harvest, RM-018 sell-timing discipline untouched.

`agent` is the LAST callable (engine contract: get_last_callable picks the
last callable in the module).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root: main.py

import main as _main

COMBO_MIX = ("WHEAT", "MELON", "STRAWBERRY")


def agent(obs, configuration=None):
    return _main.agent(
        obs,
        configuration=configuration,
        animals_enabled=True,
        crop_mix=COMBO_MIX,
        hire_hands=True,
        early_hire=True,
        crop_spread=True,
    )
