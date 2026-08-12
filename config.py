"""Config.py — single source of truth for all tunable strategy constants (TICKET-06).

Imported by main.py and eval/tournament.py. Every constant carries a comment
linking to the PLAN.md section / docs that justify it. No bare numeric literals
in decision logic — change tunables here, keep the reasoning in docs/strategy.md.

Ships in the submission bundle (stdlib-only, no import concerns on the host).
"""
from __future__ import annotations

# --- Strategy phases (PLAN.md §3.3) -----------------------------------------
# Land expansion: cash reserve kept before buying a quadrant (PLAN.md §3.3).
CASH_RESERVE_BUFFER = 300

# Quadrant #4 policy (TICKET-04/09/16, docs/strategy.md):
# buy only if day <= QUADRANT4_LATEST_DAY AND money >= QUADRANT4_CASH_THRESHOLD
# AND post-purchase money >= QUADRANT4_RESERVE. Land order is pinned NE->SW->SE.
QUADRANT4_LATEST_DAY = 16
QUADRANT4_CASH_THRESHOLD = 6000
QUADRANT4_RESERVE = 1000
QUADRANT4_CROP = "MELON"  # committed default per TICKET-16; None = Q4 disabled

# --- Animals (PLAN.md §3.3 "Days 8–20") --------------------------------------
# Keep wheat buffer >= (WHEAT_BUFFER_PER_ANIMAL * animals) + WHEAT_BUFFER_BASE.
WHEAT_BUFFER_PER_ANIMAL = 2
WHEAT_BUFFER_BASE = 5

# --- Labor (PLAN.md §3.2/3.3) ------------------------------------------------
# Hire a hand when standing-task count exceeds what the farmer alone can do.
HIRE_THRESHOLD_TASKS = 5

# --- Market / sale policy (PLAN.md §3.4) -------------------------------------
# Sell window: first turns after a town-consumption tick (prices highest).
SELL_WINDOW_TICKS = 2
# Buy FERTILIZER only below this price (and only in melon/tomato season).
FERTILIZER_BUY_MAX_PRICE = 120

# --- Compute budget (PLAN.md §3.5, TICKET-03) --------------------------------
# Cap BFS search radius (half-board); keep worst-case turn < ~100ms.
BFS_MAX_STEPS = 16

# --- Stretch goal (TICKET-05) ------------------------------------------------
# Opponent-aware premium sale timing. Default OFF; validated ON-vs-OFF in
# tournament before any promotion. Date-scoped Aug 25–Sep 10 (PLAN.md §6).
OPPONENT_AWARE_SELL_TIMING = False

# --- Engine constants (mirror kaggle_environments; kept here for tuning) -----
# Land order + prices (pinned by the engine; PLAN.md §3.3, rules-notes.md).
LAND_ORDER = ["NE", "SW", "SE"]
LAND_PRICES = [1000, 2000, 4000]

# NOTE (M7, verified 2026-08-12): there is NO mid-day cap on carried inventory.
# Units can hold unlimited items; the only constraint is shed capacity (host
# shedCapacity=100), enforced at DROP / PLACE-deposit / end-of-day auto-drop
# (overflow discarded). Do NOT add a per-unit cap assumption here — TICKET-07's
# "stockpiling does not bypass the cap" premise was overturned by the engine.
SHED_CAPACITY = 100  # host default; mirror for policy planning only

# Seed costs (engine CROPS table; docs/findings.md M-rows).
SEED_COSTS = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}

# Price-curve constants for the market-price function (docs/findings.md M9a/M9b).
MARKET_I0 = 10_000
# Floor below which no market price drops (engine PRICE_FLOOR; findings M10).
PRICE_FLOOR = 1

# Full price model per resource (docs/findings.md §4 M9a/M9b + micro_tests.py).
# Mirrors the engine's MARKET_PARAMS exactly: price(inv) = base + sign*amp*f(|inv-I0|),
# amp = target*base/f(T), sign +1 below I0 (scarcity) / -1 above (glut).
# Single source of truth for main.py's floor-price logic (RM-018) — change here,
# not in micro_tests.py. Verified against the engine 2026-08-12 (M9a/M9b ✅).
MARKET_PARAMS = {
    "WHEAT":       {"base": 25,  "T": 400,  "below_func": "sqrt",   "below_target": 0.80, "above_func": "log",    "above_target": 0.20},
    "CARROT":      {"base": 35,  "T": 450,  "below_func": "log",    "below_target": 0.20, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":      {"base": 60,  "T": 200,  "below_func": "linear", "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY":  {"base": 120, "T": 100,  "below_func": "sqrt",   "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":       {"base": 250, "T": 300,  "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":         {"base": 50,  "T": 332,  "below_func": "linear", "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":        {"base": 160, "T": 122,  "below_func": "sqrt",   "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":        {"base": 200, "T": 105,  "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
    "FERTILIZER":  {"base": 100, "T": 200,  "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}
