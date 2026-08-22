"""RM-044 — land expansion re-test at current scope (A/B variant, not committed).

RM-015/016 rejected land when the farm had a single farmer and no labor: the
farmer spread too thin. Now the agent has 4 hands + closest-first assignment,
and the cash trajectory bottoms ~$1.2k day 3-6 then climbs to ~$13.8k day 15.
Land (NE $1k -> SW $2k -> SE $4k) is affordable mid-season and 4 hands can work
it. This re-tests `buy_land=True` against the committed `buy_land=False`.

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
        buy_land=True,
    )
