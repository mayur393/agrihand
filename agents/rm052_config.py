"""rm052_config.py — Isolated config for RM-052 NE-only land expansion test.

Fork of config.py (origin/main RM-050 baseline). Only the land-expansion
constants are changed; everything else is an exact copy to guarantee the
candidate's non-land behavior is identical to the baseline.

Changes from config.py:
  - NE_ONLY_LIMIT = 1 (new): restrict BUY_LAND to the first extra quadrant only
  - QUADRANT4_LATEST_DAY = 10 (was 16): buy earlier in the season
  - QUADRANT4_CASH_THRESHOLD = 4500 (was 9000): lower barrier to entry
  - QUADRANT4_RESERVE = 1500 (was 1000): keep more cash after purchase

All tunables documented with comments linking to the PLAN section that
justifies them. No bare numeric literals in decision logic (TICKET-06).
"""
from __future__ import annotations

# --- Strategy phases (PLAN.md §3.3) -----------------------------------------
# Land expansion: cash reserve kept before buying a quadrant (PLAN.md §3.3).
CASH_RESERVE_BUFFER = 300

# RM-052: limit land purchases to this many extra quadrants.
# 1 = NE only ($1k). 2 = NE + SW ($3k total). 3 = full chain ($7k total).
# This ticket tests NE only; SW/SE remain disabled.
NE_ONLY_LIMIT = 1

# Quadrant #4 policy (TICKET-04/09/16, docs/strategy.md; RE-DERIVED RM-021):
# buy only if day <= QUADRANT4_LATEST_DAY AND money >= QUADRANT4_CASH_THRESHOLD
# AND post-purchase money >= QUADRANT4_RESERVE.
# RM-052: relaxed gates for NE-only test:
#   - day <= 10: earlier window, before mid-season plateau
#   - money >= 4500: NE costs $1k, need ~$3.5k operating capital
#   - reserve >= 1500: enough for one seed restock + emergency
QUADRANT4_LATEST_DAY = 10
QUADRANT4_CASH_THRESHOLD = 4500
QUADRANT4_RESERVE = 1500
QUADRANT4_CROP = "MELON"  # committed default per TICKET-16; None = Q4 disabled

# --- Animals (PLAN.md §3.3 "Days 8–20") --------------------------------------
# Keep wheat buffer >= (WHEAT_BUFFER_PER_ANIMAL * animals) + WHEAT_BUFFER_BASE.
WHEAT_BUFFER_PER_ANIMAL = 2
WHEAT_BUFFER_BASE = 5

# RM-036: production-side wheat reserve. The sell buffer above protects shed
# wheat from sales, but FEED drains it 1/day/animal — if the planted mix
# drifts to premium crops (crop_spread), production can't replenish and the
# animal starves even though the sell rule was never broken. When animals are
# enabled and live wheat tiles drop below this floor, PLANT forces WHEAT.
WHEAT_MIN_TILES = 6

# RM-050 diagnostic candidate (docs/rm050-total-rework-plan.md).
SEED_STOCK_TARGET = 3
ANIMAL_COSTS = {"GOOSE": 300, "COW": 400, "SHEEP": 500}
ANIMAL_STRUCTURES = {"GOOSE": "COOP", "COW": "PASTURE", "SHEEP": "PASTURE"}
ANIMAL_BUILD_ACTIONS = {"COOP": "BUILD_COOP", "PASTURE": "BUILD_PASTURE"}
PRIMARY_ANIMAL = "COW"
SECONDARY_ANIMAL = "SHEEP"
TARGET_COWS = 8
TARGET_SHEEP = 0
FIRST_ANIMAL_DAY = 0
FIRST_HERD_WHEAT_BRIDGE = WHEAT_BUFFER_BASE + WHEAT_BUFFER_PER_ANIMAL
MAX_HANDS_PER_DAY = 12
HANDS_BASE = 2
HANDS_PER_ANIMAL = 1
PLANTS_PER_HAND = 3
WORKER_ZONE_COUNT = 5
WORKER_CROSS_ZONE_PENALTY = 4

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

# Crop growth windows (engine CROPS table; docs/findings.md M-rows). Needed by
# main.py's harvest gate — no bare literals in decision logic (TICKET-06).
# first_yield_day: earliest day HARVEST succeeds; max_yield_day: single-yield
# crops expire; ongoing: re-yields every `interval` days after first_yield_day.
CROPS = {
    "WHEAT":      {"first_yield_day": 2, "max_yield_day": 4, "interval": 0, "ongoing": False},
    "CARROT":     {"first_yield_day": 2, "max_yield_day": 3, "interval": 0, "ongoing": False},
    "TOMATO":     {"first_yield_day": 8, "max_yield_day": 8, "interval": 1, "ongoing": True},
    "STRAWBERRY": {"first_yield_day": 10, "max_yield_day": 10, "interval": 2, "ongoing": True},
    "MELON":      {"first_yield_day": 10, "max_yield_day": 12, "interval": 0, "ongoing": False},
}

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
