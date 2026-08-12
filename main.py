"""main.py — THE submission entry point (PLAN.md §9, Step 3+).

Exposes `agent(obs)` for Kaggle's kaggriculture environment. Stdlib-only;
imports config.py. This is the v1 scaffold — the real strategy (plant/water/
harvest/move loop with all literals extracted to config.py) is the next step,
ported from ~/Downloads/main.py per PLAN.md §9 step 3.

Gates: must pass `eval/smoke.py --fast` before promotion, and
`eval/check_findings.py` runs first in both smoke tiers (TICKET-10) — do not
reference an unresolved mechanic from docs/findings.md.
"""
from __future__ import annotations


def agent(obs):
    """Return a valid per-turn action: {"farmer": [op,...], "hands": [...], "market": [...]}.

    Placeholder: always PASS. The scaffold intentionally makes no engine
    calls yet, so the RM-005 findings gate passes; real ops (and their
    mechanic dependencies) land with the v1 loop at RM-012.
    """
    return {"farmer": ["PASS"], "hands": [], "market": []}
