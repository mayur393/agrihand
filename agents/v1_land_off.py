"""A/B variant for RM-015: main.py with land-buying DISABLED.

Wraps the committed main.py agent and forces buy_land=False per call (no
module mutation — avoids cross-contamination when both variants run in one
tournament process). `agent` is the LAST callable (engine contract:
get_last_callable picks [v for v in env.values() if callable(v)][-1]).
Engine contract: runner calls agent(observation, configuration).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root: main.py

import main as _main


def agent(obs, configuration=None):
    return _main.agent(obs, configuration=configuration, buy_land=False)
