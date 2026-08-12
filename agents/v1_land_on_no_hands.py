"""A/B variant for RM-016: land ON + hands OFF (RM-015's rejected combo + no hands).
Wraps the committed main.py agent. agent is the LAST callable.
Engine contract: agent(observation, configuration).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as _main


def agent(obs, configuration=None):
    return _main.agent(obs, configuration=configuration,
                       buy_land=True, hire_hands=False)
