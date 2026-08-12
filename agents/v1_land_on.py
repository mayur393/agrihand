"""A/B variant for RM-015: main.py with land-buying ENABLED.

Wraps the committed main.py agent and forces buy_land=True per call (the
committed default is OFF — this is the experimental arm). No module mutation.
`agent` is the LAST callable. Engine contract: agent(observation, configuration).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root: main.py

import main as _main


def agent(obs, configuration=None):
    return _main.agent(obs, configuration=configuration, buy_land=True)
