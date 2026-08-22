"""RM-041 variant #3 — strawberry-dominant crop mix (A/B variant, not committed).

Upper-bound probe: 75% strawberry, 25% wheat. Only meaningful if variants #1/#2
show a positive slope for strawberry share. Everything else matches committed
defaults (closest-first ON, animals ON, etc.).

`agent` is the LAST callable (engine contract).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as _main

MIX = ("STRAWBERRY", "STRAWBERRY", "STRAWBERRY", "WHEAT")


def agent(obs, configuration=None):
    return _main.agent(
        obs,
        configuration=configuration,
        crop_mix=MIX,
    )
