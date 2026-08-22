"""RM-041 variant #2 — drop melon from the mix (A/B variant, not committed).

RM-040 found melon's controlled coefficient negative (-$106/unit). This drops
melon entirely: ~67% strawberry, ~33% wheat. Wheat stays as the feed reserve.
Everything else matches committed defaults (closest-first ON, animals ON, etc.).

`agent` is the LAST callable (engine contract).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as _main

MIX = ("STRAWBERRY", "STRAWBERRY", "WHEAT")


def agent(obs, configuration=None):
    return _main.agent(
        obs,
        configuration=configuration,
        crop_mix=MIX,
    )
