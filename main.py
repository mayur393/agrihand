"""main.py — THE submission entry point (RM-014, BFS task assignment).

Exposes `agent(obs)` for Kaggle's kaggriculture environment. Stdlib-only;
imports config.py. v1.2 replaces the deterministic scan-order loop with a
real task-assignment system: a priority-ordered task list per turn
(WATER/FEED > HARVEST > COLLECT_FERTILIZER > CARE > DIG > PLANT > PLACE),
then BFS from each unit's position to the nearest tile matching the
highest-priority unmet task.

Mechanic corrections baked in (docs/findings.md):
  M1 (FEED uses carried inventory, not shed) — a FEED task must ensure the
      unit carries wheat before reaching the animal. No animals in v1, but
      `assign_task` is per-unit so RM-016 reuses it unchanged.
  M7 (no mid-day carried cap; shed capacity + end-of-day overflow discard
      is the real constraint) — harvesting is shed-room-aware.
  M8 (LOCKED tiles passable, not actionable) — BFS may path through LOCKED
      tiles but no task ever targets one.

Compute budget (RM-008/TICKET-03): BFS is capped at BFS_MAX_STEPS (16 =
half-board) from config.py; worst-case single-farmer turn is benchmarked
and logged in docs/findings.md.

ENGINE CONTRACT: kaggle_environments loads main.py by exec() and picks the
LAST callable defined in the module as the agent (get_last_callable returns
[v for v in env.values() if callable(v)][-1]). So `agent` MUST be the last
function defined in this file — no helper functions after it.
"""
from __future__ import annotations

from collections import deque

from config import (
    BFS_MAX_STEPS,
    CASH_RESERVE_BUFFER,
    CROPS,
    HIRE_THRESHOLD_TASKS,
    LAND_ORDER,
    LAND_PRICES,
    PRICE_FLOOR,
    SEED_COSTS,
    SHED_CAPACITY,
    WHEAT_BUFFER_BASE,
)

# Crops v1 actually plants (wheat + carrot). The others exist in config for
# later epics; keeping this explicit avoids accidental planting of premium
# crops whose glut dynamics v1 doesn't manage yet (strategy.md §3.4).
V1_CROPS = ("WHEAT", "CARROT")

# Farmer walks to the shed to DROP when carrying at least this many items
# (M7: shed is the real constraint; don't let overflow hit the day-end discard).
DROP_CARRY_THRESHOLD = 20

# Land-expansion A/B switch (RM-015). OFF is the committed default: A/B
# tournament (2026-08-13) proved a single farmer buying land LOSES to starter
# (land-ON 0/160 CI [0.000, 0.023] vs land-OFF 160/0 CI [0.977, 1.000]) — the
# farmer spreads too thin and walks instead of farming. RM-016 re-tests this
# WITH hired hands (the labor precondition) via a 2x2 A/B.
BUY_LAND = False

# Hand-hiring A/B switch (RM-016). 2x2 A/B (2026-08-13): both no-land arms
# win 160/0 CI [0.977, 1.000]; hands add no measurable benefit at v1 scope
# (avg margin 1114 with hands vs 1196 without over 6 seeds — noise). Land is
# the only factor that matters, and it's decisively bad either way. Committed
# default OFF (simpler, marginally better margin). Revisit with animals
# (RM-019) when daily FEED/CARE tasks create a real labor need.
HIRE_HANDS = False

# Max hands hired per day. Fibonacci costs 1,1,2,3,5,8 — the 3rd+ hire is
# where daily cost stops being trivially cheap; the plan targets 1-2 hands.
MAX_HANDS_PER_DAY = 2

# Task priorities (RM-014). Higher = more urgent. FEED/HARVEST etc. that v1
# doesn't use yet are present so the priority table is complete for RM-016+.
_TASK_PRIORITY = {
    "WATER": 7, "FEED": 7,
    "HARVEST": 6,
    "COLLECT_FERTILIZER": 5,
    "CARE": 4,
    "DIG": 3,
    "PLANT": 2,
    "PLACE": 1,
}

# Direction vectors (y grows downward).
_MOVES = (("NORTH", 0, -1), ("SOUTH", 0, 1), ("EAST", 1, 0), ("WEST", -1, 0))


def _shed_access_tile(board_size: int) -> tuple[int, int]:
    """First NW shed-access tile (the farmer's home), matching engine spawn."""
    half = board_size // 2
    return (half - 1, half - 1)  # NW: (4,4) on a 10x10 board


def _harvestable_yield(tile, day) -> int:
    """Yield_units if `tile` is a harvestable plant now, else 0.

    Used for the M7 shed-room check: DROP only when it unblocks an actual
    harvest (a mature plant with yield we can't yet store).
    """
    if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
        return 0
    crop = tile.get("crop")
    crop_data = CROPS.get(crop, {})
    age = day - tile.get("planted_day", day)
    if age < crop_data.get("first_yield_day", 99):
        return 0
    return tile.get("yield_units", 0)


def _in_field(pos: tuple[int, int], tiles) -> bool:
    """True if `pos` is a plantable tile (unlocked, not LOCKED) near the shed.

    The field is the set of unlocked tiles the farmer can work. Bought land is
    included so expansion is actually usable (not just walked through), but
    the single farmer still cycles the nearest-needs-first via BFS.
    """
    x, y = pos
    t = tiles[y][x]
    if t == "LOCKED":
        return False
    return True


def _is_shed_adjacent(pos: tuple[int, int], board_size: int) -> bool:
    """True if `pos` is one of the four inner-corner tiles around the shed."""
    half = board_size // 2
    return tuple(pos) in {(half - 1, half - 1), (half, half - 1),
                          (half - 1, half), (half, half)}


def _shed_room(private) -> int:
    """Remaining shed capacity (M7: the only real inventory constraint)."""
    return max(0, SHED_CAPACITY - sum(private["shed"].values()))


def _carried_total(private, idx=0) -> int:
    """Total items on a unit's carried inventory (idx 0 = farmer, 1+ = hands).

    Matches the engine's per-unit inventory slots (private["inventories"][idx]).
    """
    invs = private["inventories"]
    if not invs or idx >= len(invs):
        return 0
    return sum(invs[idx].values())


def _bfs_nearest(start, tiles, board_size, is_target, max_steps=BFS_MAX_STEPS):
    """BFS from `start` to the nearest tile where is_target(x, y) is True.

    The start tile itself is a candidate (distance 0) — a unit standing on a
    task tile should act in place, not walk away. LOCKED tiles are passable
    but never actionable (M8). Returns the target (x, y) or None if none is
    reachable within `max_steps`.
    """
    sx, sy = start
    if is_target(sx, sy):
        return start
    seen = {start}
    frontier = deque([(sx, sy, 0)])
    while frontier:
        x, y, d = frontier.popleft()
        if d >= max_steps:
            continue
        for _, dx, dy in _MOVES:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < board_size and 0 <= ny < board_size):
                continue
            if (nx, ny) in seen:
                continue
            seen.add((nx, ny))
            if is_target(nx, ny):
                return (nx, ny)
            frontier.append((nx, ny, d + 1))
    return None


def _tile_task_priority(tile, day, private, board_size) -> tuple[int, str]:
    """Highest-priority unmet task on a single tile, or (0, None).

    Priority (RM-014): WATER/FEED > HARVEST > COLLECT_FERTILIZER > CARE >
    DIG > PLANT > PLACE. Only tasks the state supports are considered.
    """
    if tile is None:
        # PLANT on empty unlocked tile IF within the planned field (near the
        # shed). Chasing any empty tile with seed causes the farmer to wander
        # the whole board; the field is where harvest→DROP cycles are short.
        if any(private["seeds"].get(c, 0) > 0 for c in V1_CROPS):
            # field radius check happens in the caller via _in_field()
            return (_TASK_PRIORITY["PLANT"], "PLANT")
        return (0, None)
    if tile == "LOCKED":
        return (0, None)  # never actionable (M8)
    if not isinstance(tile, dict):
        return (0, None)

    kind = tile.get("kind")
    if kind == "PLANT":
        crop = tile.get("crop")
        crop_data = CROPS.get(crop, {})
        age = day - tile.get("planted_day", day)
        if age >= crop_data.get("first_yield_day", 99) and tile.get("yield_units", 0) > 0:
            # harvestable — but only if shed has room (M7), else it's not
            # actionable this turn (the unit should DROP first instead)
            if _shed_room(private) >= tile.get("yield_units", 0):
                return (_TASK_PRIORITY["HARVEST"], "HARVEST")
            return (0, None)
        if not tile.get("watered_today"):
            return (_TASK_PRIORITY["WATER"], "WATER")
        return (0, None)
    if kind == "WEED":
        return (_TASK_PRIORITY["DIG"], "DIG")
    # COOP/PASTURE structures (no animals yet in v1) — PLACE/COLLECT/CARE/FEED
    # arrive with RM-016/RM-019. Not actionable in v1.
    return (0, None)


def _count_backlog(farm, private, day, board_size) -> int:
    """Number of URGENT unmet tasks this turn (WATER/HARVEST/DIG — priority >= DIG).

    Used for the hire decision (RM-016). PLANT is excluded: every empty tile
    is technically plantable, so counting it inflates the backlog to ~always
    hire. The real signal is urgent care tasks the farmer can't clear alone.
    """
    count = 0
    tiles = farm["tiles"]
    urgent = _TASK_PRIORITY["DIG"]  # DIG=3 and above are urgent
    for y in range(board_size):
        for x in range(board_size):
            p, task = _tile_task_priority(tiles[y][x], day, private, board_size)
            if p >= urgent:
                count += 1
    return count


def _assign_task(unit_pos, farm, private, day, board_size):
    """Per-unit task assignment: nearest tile with the highest-priority unmet task.

    Structured to be reusable for hired hands (RM-016): takes a unit position
    and farm state, returns (target, task) or None. The engine applies one
    action per unit per turn, so `agent` decides act-in-place vs move using
    this.

    Returns (target, task, action_spec):
      - target: (x, y) tile for the task
      - task: one of WATER/HARVEST/DIG/PLANT
      - action_spec: the action to take once AT the target
    """
    tiles = farm["tiles"]
    # Priority ladder: try each priority class from highest to lowest, and
    # BFS to the nearest tile of that class. Priority first, distance second.
    for pri in sorted(set(_TASK_PRIORITY.values()), reverse=True):
        targets = []
        for y in range(board_size):
            for x in range(board_size):
                t = tiles[y][x]
                p, task = _tile_task_priority(t, day, private, board_size)
                if p == pri:
                    # PLANT only on unlocked tiles (not LOCKED) — bought land is
                    # workable, and BFS still picks the nearest empty tile first.
                    if task == "PLANT" and not _in_field((x, y), tiles):
                        continue
                    targets.append((x, y, task))
        if not targets:
            continue
        target_set = set((t[0], t[1]) for t in targets)
        tgt = _bfs_nearest(unit_pos, tiles, board_size,
                           lambda x, y, ts=target_set: (x, y) in ts)
        if tgt is not None:
            task = next(task for (x, y, task) in targets if (x, y) == tgt)
            return (tgt, task, _action_for_task(task))
    return None


def _action_for_task(task):
    """Action spec to apply once standing on the task target."""
    if task == "WATER":
        return ["WATER"]
    if task == "HARVEST":
        return ["HARVEST"]
    if task == "DIG":
        return ["DIG"]
    if task == "PLANT":
        # caller resolves which crop
        return ["PLANT", None]
    return ["PASS"]


def _market_orders(me, private, market, day, buy_land=BUY_LAND, hire_hands=HIRE_HANDS, board_size=10) -> list:
    """Queue market orders: buy seeds, sell shed stock, buy land, hire hands."""
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

    # Buy land: next quadrant in the PINNED order NE->SW->SE, when cash allows
    # after keeping the reserve buffer.
    #
    # M8-honest note: NE-first is NOT because "a hand spawns at (5,4)" — that
    # was a simplification (the real mechanic is first-free NWSE shed-access
    # tile). NE is simply first in the engine's pinned LAND_ORDER, so we buy
    # it first because the engine requires the order. No hand-spawn reasoning.
    if buy_land:
        n_extra = len(me["unlocked_quadrants"]) - 1  # NW is always there
        if n_extra < len(LAND_ORDER) and me["money"] - LAND_PRICES[n_extra] >= CASH_RESERVE_BUFFER:
            orders.append(["BUY_LAND"])

    # Hire hands when the task backlog exceeds what the farmer alone can clear
    # (RM-016). Hands reset daily (engine clears hands + hires_today at day
    # end), so this is a daily re-hire decision. Fibonacci cost: 1,1,2,3,5,8 —
    # hire up to MAX_HANDS_PER_DAY while the backlog stays high; the daily
    # cost of 1-2 hands ($1-2) is trivially cheap vs the extra actions.
    if hire_hands:
        backlog = _count_backlog(me, private, day, board_size)
        if backlog > HIRE_THRESHOLD_TASKS and me["hires_today"] < MAX_HANDS_PER_DAY:
            orders.append(["HIRE"])  # one HIRE per turn; engine processes it

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


def _unit_action(pos, farm, private, day, board_size, idx=0):
    """One unit's action (farmer or hand): act in place or move toward task.

    Shared by farmer + hands (RM-016). Returns a farmer/hand action list, e.g.
    ["WATER"], ["HARVEST"], ["PLANT", "WHEAT"], ["EAST"], or ["PASS"].
    `idx` is the inventory slot (0 = farmer, 1+ = hands) for the M7 carry check.
    """
    fx, fy = pos
    tile = farm["tiles"][fy][fx]

    # M7: DROP when it unblocks a harvest (yield > shed room) or above carry
    # threshold — never let overflow hit the end-of-day discard.
    if _carried_total(private, idx) > 0 and (
        _carried_total(private, idx) >= DROP_CARRY_THRESHOLD
        or _shed_room(private) < _harvestable_yield(tile, day)
    ):
        if _is_shed_adjacent(pos, board_size):
            return ["DROP"]
        return [_step_toward(pos, _shed_access_tile(board_size))]

    assigned = _assign_task(pos, farm, private, day, board_size)
    if assigned is None:
        return ["PASS"]

    target, task, action_spec = assigned
    if target == pos:
        if task == "PLANT":
            for crop in V1_CROPS:
                if private["seeds"].get(crop, 0) > 0:
                    return ["PLANT", crop]
            return ["PASS"]
        return action_spec
    return [_step_toward(pos, target)]


def agent(obs, configuration=None, buy_land=BUY_LAND, hire_hands=HIRE_HANDS):
    """Return a valid per-turn action dict (RM-016 farm hands).

    ENGINE CONTRACT: the runner calls agent(observation, configuration) — TWO
    positional args. `configuration` is the env config dict (ignored here);
    it MUST be accepted or the engine's second arg lands in `buy_land` (a
    non-empty dict is truthy, which silently enables land buying). `buy_land`
    and `hire_hands` are per-call overrides so A/B variants (RM-015/016) can
    toggle features without mutating the shared module; the submission
    defaults are BUY_LAND / HIRE_HANDS.

    Per turn:
      1. Build market orders (seeds, sell, land, hire).
      2. Farmer + each hand (in their ACTUAL positions, M8) get a task via
         BFS and act in place or move toward it (shared _unit_action).
    """
    player = obs["player"]
    me = obs["farms"][player]
    private = obs["private"]
    board_size = len(me["tiles"])
    day = obs["day"]

    market = _market_orders(me, private, obs["market"], day,
                            buy_land=buy_land, hire_hands=hire_hands,
                            board_size=board_size)

    farmer_action = _unit_action((me["farmer"][0], me["farmer"][1]),
                                 me, private, day, board_size, idx=0)
    hand_actions = [_unit_action((hx, hy), me, private, day, board_size, idx=i + 1)
                    for i, (hx, hy) in enumerate(me["hands"])]

    return {"farmer": farmer_action, "hands": hand_actions, "market": market}
