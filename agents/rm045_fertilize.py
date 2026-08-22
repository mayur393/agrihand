"""RM-045 — FERTILIZE melon for +2 yield (A/B variant, not committed).

The engine doubles the per-water-day yield bonus (+2 vs +1) for non-ongoing
crops when fertilized (fertilized_until_day >= day). Our agent already collects
free fertilizer from the goose but only sells it. This applies fertilizer to
MELON tiles (the highest-value non-ongoing crop in the committed mix) in their
accumulation window, using the same carry-then-act pattern as FEED.

Everything else matches committed defaults. `agent` is the LAST callable.
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
        fertilize_enabled=True,
    )
