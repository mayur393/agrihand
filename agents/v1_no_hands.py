"""A/B variant for RM-016: main.py with hand-hiring DISABLED.
Wraps the committed main.py agent, forces hire_hands=False. No module mutation.
agent is the LAST callable. Engine contract: agent(observation, configuration).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as _main


def agent(obs, configuration=None):
    return _main.agent(obs, configuration=configuration, hire_hands=False)
