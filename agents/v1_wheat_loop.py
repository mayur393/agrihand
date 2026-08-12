"""main.py — THE submission entry point (RM-012, v1 wheat/carrot loop).

Exposes `agent(obs)` for Kaggle's kaggriculture environment. Stdlib-only;
imports config.py. v1 is a port of the sample loop pattern (plant→water→
harvest→sell) with the mechanic corrections from docs/findings.md baked in:

  M1 (FEED uses carried inventory, not shed) — v1 has no animals, but if
      animal code is added later, wheat must be carried, not shed-pulled.
  M7 (no mid-day carried cap; shed capacity + end-of-day overflow discard
      is the real constraint) — harvesting is shed-room-aware: we never
      harvest more than the shed can absorb before the end-of-day drop.
  M8 (first-hand spawn = first FREE shed-access tile, NWSE) — no fixed
      (5,4) assumption anywhere; hands aren't wired in v1.

Sell policy: never sell below the per-crop floor (PRICE_FLOOR, strategy.md
floor rule). All tunables come from config.py — no bare literals for anything
already defined there.

ENGINE CONTRACT: kaggle_environments loads main.py by exec() and picks the
LAST callable defined in the module as the agent (get_last_callable returns
[v for v in env.values() if callable(v)][-1]). So `agent` MUST be the last
function defined in this file — no helper functions after it.
"""
from __future__ import annotations

from config import (
    CROPS,
    PRICE_FLOOR,
    SEED_COSTS,
    SHED_CAPACITY,
    WHEAT_BUFFER_BASE,
)

# Crops v1 actually plants (wheat + carrot). The others exist in config for
# later epics; keeping this explicit avoids accidental planting of premium
# crops whose glut dynamics v1 doesn't manage yet (strategy.md §3.4).
V1_CROPS = ("WHEAT", "CARROT")

# Plant only within this Chebyshev radius of the shed-access tile so
# harvest→DROP→SELL cycles stay short. The farmer operates a small NW field.
PLANT_RADIUS = 1

# Farmer walks to the shed to DROP when carrying at least this many items
# (M7: shed is the real constraint; don't let overflow hit the day-end discard).
DROP_CARRY_THRESHOLD = 20


def _shed_access_tile(board_size: int) -> tuple[int, int]:
    """First NW shed-access tile (the farmer's home), matching engine spawn."""
    half = board_size // 2
    return (half - 1, half - 1)  # NW: (4,4) on a 10x10 board


def _is_shed_adjacent(pos: tuple[int, int], board_size: int) -> bool:
    """True if `pos` is one of the four inner-corner tiles around the shed."""
    half = board_size // 2
    return tuple(pos) in {(half - 1, half - 1), (half, half - 1),
                          (half - 1, half), (half, half)}


def _shed_room(private) -> int:
    """Remaining shed capacity (M7: the only real inventory constraint)."""
    return max(0, SHED_CAPACITY - sum(private["shed"].values()))


def _carried_total(private) -> int:
    """Total items on the main farmer's carried inventory."""
    return sum(private["inventories"][0].values()) if private["inventories"] else 0


def _market_orders(me, private, market) -> list:
    """Queue market orders: buy seeds, sell shed stock above buffer."""
    orders: list = []

    # Buy seeds for the crops v1 plants, up to a small working stock.
    for crop in V1_CROPS:
        if private["seeds"].get(crop, 0) == 0 and me["money"] >= SEED_COSTS[crop]:
            orders.append(["BUY_SEED", crop, 1])

    # Sell shed stock. Keep a wheat buffer for future feeding (strategy.md);
    # never sell below the floor (M10). Staples (wheat/carrot) absorb gluts,
    # so selling them steadily is fine.
    shed = private["shed"]
    for item, qty in shed.items():
        if item in ("WHEAT", "CARROT"):
            buffer = WHEAT_BUFFER_BASE if item == "WHEAT" else 0
            excess = qty - buffer
            if excess > 0 and market["prices"].get(item, PRICE_FLOOR) > PRICE_FLOOR:
                orders.append(["SELL", item, excess])
        elif qty > 0 and market["prices"].get(item, PRICE_FLOOR) > PRICE_FLOOR:
            orders.append(["SELL", item, qty])

    # NOTE: v1 does NOT buy land (RM-015's job). Land costs $3k for all three
    # quadrants and v1 only farms the small NW field — expansion is a net cash
    # drain until the field-farming loop scales to it. Removing it beats the
    # starter by keeping cash productive instead of locked in idle land.
    return orders[:10]  # engine caps market orders per turn


def _step_toward(pos: tuple[int, int], target: tuple[int, int]) -> str:
    """One directional move toward `target` (N/S/E/W), no diagonal."""
    if pos[0] < target[0]:
        return "EAST"
    if pos[0] > target[0]:
        return "WEST"
    if pos[1] < target[1]:
        return "SOUTH"
    if pos[1] > target[1]:
        return "NORTH"
    return "PASS"


def _field_tiles(board_size: int) -> list[tuple[int, int]]:
    """Fixed 3x3 field around the shed-access tile (NW corner), scan order.

    Chebyshev radius PLANT_RADIUS (=1) around home (4,4). Scan order is a
    deterministic row-major sweep so the farmer cycles the whole field.
    """
    home = _shed_access_tile(board_size)
    hx, hy = home
    tiles = []
    for dy in range(-PLANT_RADIUS, PLANT_RADIUS + 1):
        for dx in range(-PLANT_RADIUS, PLANT_RADIUS + 1):
            x, y = hx + dx, hy + dy
            if 0 <= x < board_size and 0 <= y < board_size:
                tiles.append((x, y))
    return tiles


def _next_field_tile(me, private, day, board_size) -> tuple[int, int] | None:
    """Next field tile needing attention, in deterministic scan order.

    Priority within the field: harvest-ready plant > unwatered plant > weed >
    empty-with-seed. Returns None if the whole field is idle.
    """
    fx, fy = me["farmer"]
    for pass_no in (0, 1):
        for (x, y) in _field_tiles(board_size):
            t = me["tiles"][y][x]
            if t is None:
                if pass_no == 1 and any(private["seeds"].get(c, 0) > 0 for c in V1_CROPS):
                    return (x, y)
                continue
            if not isinstance(t, dict):
                continue
            if t.get("kind") == "WEED":
                if pass_no == 0:
                    return (x, y)
            elif t.get("kind") == "PLANT":
                age = day - t.get("planted_day", day)
                crop_data = CROPS.get(t.get("crop"), {})
                mature = age >= crop_data.get("first_yield_day", 99) and t.get("yield_units", 0) > 0
                if pass_no == 0 and (mature or not t.get("watered_today")):
                    return (x, y)
    return None


def agent(obs):
    """Return a valid per-turn action dict.

    v1 farmer policy — a small deterministic field around the shed, cycled
    in priority order each turn:
      1. Standing on a mature, harvestable plant AND shed has room -> HARVEST.
         If shed is full, DROP what we carry first (M7: never let overflow be
         silently discarded at day end).
      2. Standing on an unwatered plant -> WATER.
      3. Standing on a weed -> DIG.
      4. Standing on an empty field tile with seed -> PLANT.
      5. Carrying too much -> walk to shed and DROP (M7).
      6. Otherwise move to the next field tile that needs attention
         (harvest-ready / unwatered / empty / weed), in a fixed scan order
         around the shed (no BFS yet — RM-014).
    Market orders run every turn regardless of the farmer action.
    """
    player = obs["player"]
    me = obs["farms"][player]
    private = obs["private"]
    board_size = len(me["tiles"])
    day = obs["day"]
    fx, fy = me["farmer"]
    tile = me["tiles"][fy][fx]

    market = _market_orders(me, private, obs["market"])

    def _action(farmer_action):
        return {"farmer": farmer_action, "hands": [], "market": market}

    # --- 1. Harvest when mature + shed has room (M7-aware) ---
    if isinstance(tile, dict) and tile.get("kind") == "PLANT":
        crop = tile["crop"]
        crop_data = CROPS[crop]
        age = day - tile["planted_day"]
        if age >= crop_data["first_yield_day"] and tile.get("yield_units", 0) > 0:
            if _shed_room(private) >= tile["yield_units"]:
                return _action(["HARVEST"])
            # shed full: DROP what we carry (if any) to make room, else PASS
            if _carried_total(private) > 0 and _is_shed_adjacent((fx, fy), board_size):
                return _action(["DROP"])
            return _action(["PASS"])
        if not tile.get("watered_today"):
            return _action(["WATER"])
        # watered + immature: fall through to movement (don't get stuck on one tile)

    # --- 2. Weed -> DIG ---
    if isinstance(tile, dict) and tile.get("kind") == "WEED":
        return _action(["DIG"])

    # --- 3. Empty field tile with seed -> PLANT ---
    home = _shed_access_tile(board_size)
    if tile is None and max(abs(fx - home[0]), abs(fy - home[1])) <= PLANT_RADIUS:
        for crop in V1_CROPS:
            if private["seeds"].get(crop, 0) > 0:
                return _action(["PLANT", crop])
        return _action(["PASS"])

    # --- 4. Carrying too much -> walk to shed and DROP (M7) ---
    if _carried_total(private) >= DROP_CARRY_THRESHOLD:
        if _is_shed_adjacent((fx, fy), board_size):
            return _action(["DROP"])
        return _action([_step_toward((fx, fy), home)])

    # --- 5. Move to the next field tile needing attention (scan order) ---
    target = _next_field_tile(me, private, day, board_size)
    if target is not None:
        return _action([_step_toward((fx, fy), target)])
    return _action(["PASS"])
