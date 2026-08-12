"""Demo agent for the visualizer — NOT a v1 candidate.

Purpose: make the game board come alive for team discussion. It uses the full
action set and assigns real per-unit tasks (greedy nearest-task BFS) so the
board shows hands walking, planting, watering, harvesting, digging, feeding,
and animals + fertilizer in play. Deliberately naive — real strategy lives in
main.py/config.py per PLAN.md. Not archived as a submitted variant and not
gated by eval/smoke.py.

Engine facts relied on (verified in kaggriculture.py):
- PLANT requires standing on an EMPTY tile; seeds are consumed directly from
  private["seeds"] (never via PICKUP/DROP).
- HARVEST requires yield_units > 0; yield only accrues when WATER is applied
  during the yield window: age_days in [(max_yield_day+1)//2, max_yield_day].
- WATER on a non-ongoing crop in the window adds bonus units (2 if fertilized).
"""
from __future__ import annotations

DIRS = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}

# Crop lifecycle facts (mirrors the engine's CROPS table — the tile dict does
# NOT carry first_yield_day/max_yield_day, so the agent must look them up by
# crop name).
CROPS = {
    "WHEAT":      {"first_yield_day": 2, "max_yield_day": 4, "ongoing": False},
    "CARROT":     {"first_yield_day": 2, "max_yield_day": 3, "ongoing": False},
    "TOMATO":     {"first_yield_day": 8, "max_yield_day": 8, "ongoing": True},
    "STRAWBERRY": {"first_yield_day": 10, "max_yield_day": 10, "ongoing": True},
    "MELON":      {"first_yield_day": 10, "max_yield_day": 12, "ongoing": False},
}


def _kind(t):
    return t.get("kind") if isinstance(t, dict) else None


def _task_for_tile(t, day):
    """Return a task key if this tile needs action this turn, else None."""
    k = _kind(t)
    if k == "WEED":
        return "DIG"
    if k == "PLANT":
        crop = CROPS.get(t.get("crop"), {})
        first = crop.get("first_yield_day", 0)
        age = day - t.get("planted_day", day)
        # Harvest only when the engine will accept it (age >= first_yield_day)
        # and there is yield to take. Otherwise water immature plants.
        if t.get("yield_units", 0) > 0 and age >= first:
            return "HARVEST"
        if not t.get("watered_today", True):
            return "WATER"
    if k == "ANIMAL":
        if not t.get("fed_today", True):
            return "FEED"
        return "CARE"
    return None


def _unit_action(me, pos, day, seeds):
    """One unit: act on its tile if a task is there, else step toward the
    nearest task tile (including empty tiles to plant on)."""
    x, y = pos
    tile = me["tiles"][y][x]
    task = _task_for_tile(tile, day)
    if task:
        return [task]
    # On an empty tile with seed in hand -> plant.
    if tile is None and seeds.get("WHEAT", 0) > 0:
        return ["PLANT", "WHEAT"]
    if isinstance(tile, dict) and tile.get("fertilizer_available"):
        return ["COLLECT_FERTILIZER"]

    # No task here: BFS toward the nearest actionable tile.
    best = None  # (dist, task, tx, ty)
    for yy in range(10):
        for xx in range(10):
            t = me["tiles"][yy][xx]
            task = _task_for_tile(t, day)
            if not task and t is None and seeds.get("WHEAT", 0) > 0:
                task = ("PLANT", "WHEAT")
            if not task:
                continue
            d = abs(xx - x) + abs(yy - y)
            if best is None or d < best[0]:
                best = (d, task, xx, yy)
    if best is None:
        return ["PASS"]
    _, task, tx, ty = best
    if tx == x and ty == y:
        return [task[0] if isinstance(task, tuple) else task]
    # step one tile toward it
    if tx != x:
        return ["EAST" if tx > x else "WEST"]
    return ["SOUTH" if ty > y else "NORTH"]


def agent(obs):
    player = obs["player"]
    me = obs["farms"][player]
    priv = obs["private"]
    day = obs.get("day", 0)
    money = me["money"]
    seeds = priv.get("seeds", {})
    shed = priv.get("shed", {})

    market = []
    if len(me["hands"]) < 2 and money >= 3:
        market.append(["HIRE"])
    have = set(me.get("unlocked_quadrants", []))
    if "NE" not in have and money >= 1500:
        market.append(["BUY_LAND"])
    elif "NE" in have and "SW" not in have and money >= 2500:
        market.append(["BUY_LAND"])
    if money >= 200 and shed.get("GOOSE", 0) < 2:
        market.append(["BUY_ANIMAL", "GOOSE", 1])
    elif money >= 1500 and shed.get("COW", 0) < 1:
        market.append(["BUY_ANIMAL", "COW", 1])
    # keep a small seed buffer; buy back when empty
    if seeds.get("WHEAT", 0) <= 1 and money >= 10:
        market.append(["BUY_SEED", "WHEAT", 3])
    # sell staples that are sitting in the shed
    for item in ("WHEAT", "CARROT", "EGG"):
        qty = shed.get(item, 0)
        if qty > 0:
            market.append(["SELL", item, qty])

    farmer = _unit_action(me, tuple(me["farmer"]), day, seeds)
    hands = [_unit_action(me, tuple(h), day, seeds) for h in me["hands"]]
    return {"farmer": farmer, "hands": hands, "market": market}
