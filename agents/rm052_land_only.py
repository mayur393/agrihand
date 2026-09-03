"""rm052_land_only.py — RM-052: NE-only land expansion test (isolated candidate).

Fork of main.py (RM-050 baseline, origin/main 30fb6a5). Only land-expansion
behavior changes: BUY_LAND is enabled with a conservative gate that buys
only the first extra quadrant (NE, $1k). Everything else is identical.

Exposes `agent(obs)` for Kaggle's kaggriculture environment. Stdlib-only;
imports rm052_config.py (isolated config).

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

from rm052_config import (
    BFS_MAX_STEPS,
    CROPS,
    ANIMAL_BUILD_ACTIONS,
    ANIMAL_COSTS,
    ANIMAL_STRUCTURES,
    FIRST_ANIMAL_DAY,
    FIRST_HERD_WHEAT_BRIDGE,
    HANDS_BASE,
    HANDS_PER_ANIMAL,
    HIRE_THRESHOLD_TASKS,
    LAND_ORDER,
    LAND_PRICES,
    PRICE_FLOOR,
    PLANTS_PER_HAND,
    PRIMARY_ANIMAL,
    QUADRANT4_CASH_THRESHOLD,
    QUADRANT4_CROP,
    QUADRANT4_LATEST_DAY,
    QUADRANT4_RESERVE,
    SEED_COSTS,
    SHED_CAPACITY,
    SECONDARY_ANIMAL,
    SEED_STOCK_TARGET,
    TARGET_COWS,
    TARGET_SHEEP,
    NE_ONLY_LIMIT,
    WHEAT_BUFFER_BASE,
    WHEAT_BUFFER_PER_ANIMAL,
    WHEAT_MIN_TILES,
    WORKER_CROSS_ZONE_PENALTY,
    WORKER_ZONE_COUNT,
)

# Crops v1 plants by default (wheat + carrot). RM-036 PROMOTED the leaderboard
# mix (MELON, STRAWBERRY, WHEAT) with crop_spread=True: self-play 80/0 vs the
# animals-on wheat/carrot baseline, CI [0.954, 1.000]. The mix only has teeth
# when the crop actually spreads across the field (CROP_SPREAD).
V1_CROPS = ("WHEAT", "MELON", "STRAWBERRY")

# Farmer walks to the shed to DROP when carrying at least this many items
# (M7: shed is the real constraint; don't let overflow hit the day-end discard).
DROP_CARRY_THRESHOLD = 20

# Land-expansion A/B switch (RM-015). OFF is the committed default: A/B
# tournament (2026-08-13) proved a single farmer buying land LOSES to starter
# (land-ON 0/160 CI [0.000, 0.023] vs land-OFF 160/0 CI [0.977, 1.000]) — the
# farmer spreads too thin and walks instead of farming. RM-016 re-tests this
# WITH hired hands (the labor precondition) via a 2x2 A/B.
BUY_LAND = True

# Hand-hiring A/B switch (RM-016). 2x2 A/B (2026-08-13): both no-land arms
# win 160/0 CI [0.977, 1.000]; hands add no measurable benefit at v1 scope
# (avg margin 1114 with hands vs 1196 without over 6 seeds — noise). Land is
# the only factor that matters, and it's decisively bad either way. RM-036
# PROMOTED hands in the combo (animals + premium mix + early hire): self-play
# 80/0 vs the no-hands animals baseline, CI [0.954, 1.000]. Hands alone were
# neutral; hands as part of the combo are decisive.
HIRE_HANDS = True

# Early-hire switch (RM-036, PROMOTED): hire unconditionally on day 0-1
# (leaderboard norm, RM-035: 98.5% of seats hire day 0) instead of waiting
# for the backlog trigger. Days 2+ fall back to the RM-016 backlog rule.
EARLY_HIRE = True

# Crop-spread switch (RM-036, PROMOTED): PLANT picks the crop by tile-position
# hash instead of always the first crop with seeds in mix order. The old
# behavior made crop_mix a wheat-monoculture (verified 2026-08-16:
# WHEAT/MELON/STRAWBERRY mix plants WHEAT 2506/2506 times), which silently
# invalidated RM-017's mix A/Bs.
CROP_SPREAD = True

# Max hands hired per day. Fibonacci costs 1,1,2,3,5,8 — the 3rd+ hire is
# where daily cost stops being trivially cheap; the plan targets 1-2 hands.
# RM-042 ceiling search PROMOTED 4: closest-first cut movement 68.4% -> 52.2%,
# then each extra hand converts remaining walking into parallel work. 3 vs 2
# (73/80, 80/80, 77/80), 4 vs 3 (+$4,012 mean margin, never negative). 5 vs 4
# is neutral-negative (-$103, 36/40 negative) and 6 vs 5 is a non-monotonic
# +$1,438 single-seed anomaly — 4 is the last monotonic win, so 4 is committed.
MAX_HANDS_PER_DAY = 12

# Animal pipeline (RM-019/RM-020 / Ticket 05C) — PROMOTED (RM-021 Part A,
# 2026-08-16). Self-play A/B vs the previous committed baseline (crop-only):
# 80/0, CI [0.954, 1.000], zero escapes on the 50-episode --animals gate.
# When ON: exactly ONE GOOSE (buy→build coop→place), fed with carried wheat
# (M1), cared daily, fertilizer collected, eggs harvested. No cows/sheep, no
# multiple geese, no special fertilizer-selling optimizer (05E owns that).
ANIMALS_ENABLED = True

# Goose is the first animal (cheapest $300, 4-day first yield).
GOOSE_COST = ANIMAL_COSTS["GOOSE"]

# Task priorities (RM-014). Higher = more urgent. FEED/HARVEST etc. that v1
# doesn't use yet are present so the priority table is complete for RM-016+.
# RM-036: HARVEST_FEED_WHEAT (8) outranks everything — mature wheat when the
# feed reserve is below floor; the ladder only iterates _TASK_PRIORITY
# values, so a tile returning an unregistered priority is invisible.
# MAKE_WHEAT_ROOM (8): DIG a premium plant when the wheat floor is broken
# and the field has no empty tile — the feed reserve must displace premium
# crops rather than starve the animal.
_TASK_PRIORITY = {
    "HARVEST_FEED_WHEAT": 8,
    "MAKE_WHEAT_ROOM": 8,
    "WATER": 7, "FEED": 7,
    "HARVEST": 6,
    "COLLECT_FERTILIZER": 5,
    "FERTILIZE": 5,  # production multiplier for non-ongoing crops (MELON); RM-045
    "CARE": 4,
    "DIG": 3,
    "PLANT": 2,
    "PLACE": 1,
    "BUILD_STRUCTURE": 9,
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


def _carried_wheat(private, idx=0) -> int:
    """Wheat in one unit's carried inventory (for the RM-036 M7-displacement guard)."""
    invs = private["inventories"]
    if not invs or idx >= len(invs):
        return 0
    return invs[idx].get("WHEAT", 0)


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


def _bfs_distances(start, tiles, board_size, max_steps=BFS_MAX_STEPS):
    """BFS distance from `start` to every reachable tile (LOCKED passable, M8).

    Matches `_bfs_nearest` reachability exactly; start tile is distance 0.
    Returns {(x, y): distance}. Tiles beyond `max_steps` are absent.
    """
    sx, sy = start
    dist = {(sx, sy): 0}
    frontier = deque([(sx, sy, 0)])
    while frontier:
        x, y, d = frontier.popleft()
        if d >= max_steps:
            continue
        for _, dx, dy in _MOVES:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < board_size and 0 <= ny < board_size):
                continue
            if (nx, ny) in dist:
                continue
            dist[(nx, ny)] = d + 1
            frontier.append((nx, ny, d + 1))
    return dist


def _tile_task_priority(tile, day, private, board_size, farm=None, crop_mix=V1_CROPS, animals_enabled=ANIMALS_ENABLED, fertilize_enabled=False) -> tuple[int, str]:
    """Highest-priority unmet task on a single tile, or (0, None).

    Priority (RM-014): WATER/FEED > HARVEST > COLLECT_FERTILIZER > CARE >
    DIG > PLANT > PLACE/BUILD_COOP. Only tasks the state supports are considered.
    `farm` is needed for BUILD_COOP (check if a coop already exists).
    """
    if tile is None:
        if animals_enabled and farm is not None and _needs_structure(farm, private):
            return (_TASK_PRIORITY["BUILD_STRUCTURE"], "BUILD_STRUCTURE")
        # RM-036: when the feed reserve is broken and we hold wheat seeds,
        # PLANT_WHEAT outranks everything. A decaying field plus daily
        # WATER/HARVEST/CARE duties can starve PLANT (priority 2) for the
        # whole season — wheat seeds sit unplanted and the animal escapes.
        if (animals_enabled and private["seeds"].get("WHEAT", 0) > 0
                and private["shed"].get("WHEAT", 0) < WHEAT_BUFFER_BASE + WHEAT_BUFFER_PER_ANIMAL
                and _live_wheat_tiles(farm) < WHEAT_MIN_TILES):
            return (_TASK_PRIORITY["HARVEST_FEED_WHEAT"], "PLANT")
        # PLANT on empty unlocked tile IF we have a seed for the mix.
        if any(private["seeds"].get(c, 0) > 0 for c in crop_mix):
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
            # RM-036: harvestable wheat outranks everything (including WATER)
            # when the feed reserve is below the floor. Otherwise mature wheat
            # waits behind the daily watering duty and the animal starves.
            if crop == "WHEAT" and animals_enabled and private["shed"].get("WHEAT", 0) < WHEAT_BUFFER_BASE + WHEAT_BUFFER_PER_ANIMAL:
                return (_TASK_PRIORITY["HARVEST_FEED_WHEAT"], "HARVEST")
            # RM-036: feed wheat bypasses the shed-room gate. A shed flooded
            # with premium goods (capacity 100) used to block wheat HARVEST
            # entirely; the FEED reserve then drained to zero and the animal
            # escaped. FEED consumes from carried inventory (M1), so wheat
            # harvested for feed never needs shed room.
            if crop == "WHEAT" and animals_enabled:
                return (_TASK_PRIORITY["HARVEST"], "HARVEST")
            if _shed_room(private) >= tile.get("yield_units", 0):
                return (_TASK_PRIORITY["HARVEST"], "HARVEST")
            return (0, None)
        # RM-036: when the feed reserve is broken and there are no empty tiles
        # for the wheat floor to plant on, DIG a non-wheat plant to make room.
        if (crop != "WHEAT" and animals_enabled
                and private["shed"].get("WHEAT", 0) < WHEAT_BUFFER_BASE + WHEAT_BUFFER_PER_ANIMAL
                and farm is not None
                and not _has_empty_tile(farm)
                and _live_wheat_tiles(farm) < WHEAT_MIN_TILES):
            return (_TASK_PRIORITY["MAKE_WHEAT_ROOM"], "DIG")
        if not tile.get("watered_today"):
            # RM-036: unwatered wheat outranks premium watering when the feed
            # reserve is broken. Young wheat dies after 2 unwatered days — if
            # watering duties starve it, no wheat ever matures and the animal
            # escapes even though the floor plants wheat.
            if (crop == "WHEAT" and animals_enabled
                    and private["shed"].get("WHEAT", 0) < WHEAT_BUFFER_BASE + WHEAT_BUFFER_PER_ANIMAL):
                return (_TASK_PRIORITY["HARVEST_FEED_WHEAT"], "WATER")
            return (_TASK_PRIORITY["WATER"], "WATER")
        # RM-045 FERTILIZE: apply to non-ongoing crops (wheat/melon) in their
        # yield-accumulation window when the tile is watered but not already
        # fertilized. Fertilizer doubles the per-water-day yield bonus (+2 vs
        # +1) for 3 days; only non-ongoing crops get the bonus (engine). The
        # goose already produces free fertilizer we currently just sell.
        if (fertilize_enabled and not crop_data.get("ongoing", False)
                and not tile.get("fertilized_until_day", -1) >= day
                and crop == "MELON"):
            return (_TASK_PRIORITY["FERTILIZE"], "FERTILIZE")
        return (0, None)
    if kind == "WEED":
        return (_TASK_PRIORITY["DIG"], "DIG")
    if "animal" in tile and animals_enabled:
        # FEED (M1): carries wheat from shed first; the unit must already have
        # it before walking to the animal (handled in _unit_action).
        if not tile.get("fed_today") and private["shed"].get("WHEAT", 0) > 0:
            return (_TASK_PRIORITY["FEED"], "FEED")
        # HARVEST: eggs/milk/wool when yield available.
        if tile.get("yield_units", 0) > 0:
            return (_TASK_PRIORITY["HARVEST"], "HARVEST")
        # COLLECT_FERTILIZER
        if tile.get("fertilizer_available"):
            return (_TASK_PRIORITY["COLLECT_FERTILIZER"], "COLLECT_FERTILIZER")
        # CARE
        if not tile.get("cared_today"):
            return (_TASK_PRIORITY["CARE"], "CARE")
    if kind in ANIMAL_BUILD_ACTIONS and animals_enabled:
        if "animal" not in tile and _shed_animal_for_structure(private, kind):
            return (_TASK_PRIORITY["PLACE"], "PLACE")
    return (0, None)


def _count_structures(farm, structure: str) -> int:
    return sum(1 for row in farm["tiles"] for t in row
               if isinstance(t, dict) and t.get("kind") == structure)


def _count_animal_type(farm, animal: str) -> int:
    return sum(1 for row in farm["tiles"] for t in row
               if isinstance(t, dict) and t.get("animal") == animal)


def _count_animals(farm) -> int:
    """Number of placed animals (for the wheat buffer scaling)."""
    return sum(1 for row in farm["tiles"] for t in row
               if isinstance(t, dict) and "animal" in t)


def _owned_animal_count(private, farm, animal: str) -> int:
    return (_count_animal_type(farm, animal) + private["shed"].get(animal, 0)
            + sum(inv.get(animal, 0) for inv in private["inventories"]))


def _pasture_owned_count(private, farm) -> int:
    return sum(_owned_animal_count(private, farm, animal)
               for animal in (PRIMARY_ANIMAL, SECONDARY_ANIMAL))


def _needs_structure(farm, private) -> bool:
    return (_pasture_owned_count(private, farm) < TARGET_COWS + TARGET_SHEEP
            and _count_structures(farm, ANIMAL_STRUCTURES[PRIMARY_ANIMAL])
            <= _pasture_owned_count(private, farm))


def _shed_animal_for_structure(private, structure: str):
    for animal in (PRIMARY_ANIMAL, SECONDARY_ANIMAL):
        if (ANIMAL_STRUCTURES[animal] == structure
                and private["shed"].get(animal, 0) > 0):
            return animal
    return None


def _live_wheat_tiles(farm) -> int:
    """Live wheat plants (PLANT kind, not dead/weed) for the RM-036 floor."""
    return sum(1 for row in farm["tiles"] for t in row
               if isinstance(t, dict) and t.get("kind") == "PLANT" and t.get("crop") == "WHEAT")


def _has_empty_tile(farm) -> bool:
    """True if any tile is None (plantable but empty) — for the RM-036 DIG gate."""
    return any(t is None for row in farm["tiles"] for t in row)


def _count_unfed_animals(farm) -> int:
    """Count animals that still need feeding today (for batch PICKUP optimization)."""
    return sum(1 for row in farm["tiles"] for t in row
               if isinstance(t, dict) and "animal" in t and not t.get("fed_today"))


def _count_backlog(farm, private, day, board_size, crop_mix=V1_CROPS, animals_enabled=ANIMALS_ENABLED, fertilize_enabled=False) -> int:
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
            p, task = _tile_task_priority(tiles[y][x], day, private, board_size,
                                          farm, crop_mix, animals_enabled,
                                          fertilize_enabled)
            if p >= urgent:
                count += 1
    return count


def _assign_task(unit_pos, farm, private, day, board_size, crop_mix=V1_CROPS, animals_enabled=ANIMALS_ENABLED, claimed_targets=None, crop_spread=CROP_SPREAD, fertilize_enabled=False):
    """Per-unit task assignment: nearest tile with the highest-priority unmet task.

    Structured to be reusable for hired hands (RM-016): takes a unit position
    and farm state, returns (target, task) or None. The engine applies one
    action per unit per turn, so `agent` decides act-in-place vs move using
    this.

    `claimed_targets` (05E): optional set of (x, y) already reserved by another
    unit this turn; those tiles are excluded from consideration. Per-turn local
    set, never module-level.

    Returns (target, task, action_spec):
      - target: (x, y) tile for the task
      - task: one of WATER/HARVEST/DIG/PLANT
      - action_spec: the action to take once AT the target
    """
    tiles = farm["tiles"]
    claimed_targets = claimed_targets or set()
    # Priority ladder: try each priority class from highest to lowest, and
    # BFS to the nearest tile of that class. Priority first, distance second.
    for pri in sorted(set(_TASK_PRIORITY.values()), reverse=True):
        targets = []
        for y in range(board_size):
            for x in range(board_size):
                if (x, y) in claimed_targets:
                    continue
                t = tiles[y][x]
                p, task = _tile_task_priority(t, day, private, board_size,
                                              farm, crop_mix, animals_enabled,
                                              fertilize_enabled)
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


def _closest_first_assign(units, farm, private, day, board_size, crop_mix, animals_enabled, claimed_targets, fertilize_enabled=False):
    """Assign all units to distinct task tiles, closest-unit-first (RM-042 #1).

    Replaces farmer-first greedy with a single global matching: for each unit,
    compute BFS distances to every task tile, then assign each unit to its
    nearest *unclaimed* tile (ties broken by unit order). The result is the
    same (target, task, action_spec) shape `_unit_action` already consumes,
    so the caller path is unchanged; only the assignment objective changes.

    `claimed_targets` is mutated in place with the chosen targets (per-turn
    local, same contract as the greedy path). Returns a dict unit_index ->
    (target, task, action_spec) or None.
    """
    tiles = farm["tiles"]

    # Enumerate all task tiles once, with their (priority, task, action_spec).
    task_tiles = []  # (x, y, priority, task)
    for y in range(board_size):
        for x in range(board_size):
            t = tiles[y][x]
            p, task = _tile_task_priority(t, day, private, board_size,
                                          farm, crop_mix, animals_enabled,
                                          fertilize_enabled)
            if p == 0:
                continue
            if task == "PLANT" and not _in_field((x, y), tiles):
                continue
            task_tiles.append((x, y, p, task))

    assigned = {}
    for ui, pos in enumerate(units):
        if not task_tiles:
            break
        dist = _bfs_distances(pos, tiles, board_size)
        # nearest unclaimed tile, keyed by (distance, -priority) so a higher
        # priority breaks a distance tie.
        best = None
        best_key = None
        for x, y, pri, task in task_tiles:
            d = dist.get((x, y))
            if d is None:
                continue
            zone_penalty = 0
            if (ui > 0 and pri < _TASK_PRIORITY["FEED"]
                    and y % WORKER_ZONE_COUNT != (ui - 1) % WORKER_ZONE_COUNT):
                zone_penalty = WORKER_CROSS_ZONE_PENALTY
            key = (d + zone_penalty, -pri, d)
            if best_key is None or key < best_key:
                best_key = key
                best = ((x, y), task)
        if best is None:
            assigned[ui] = None
            continue
        target, task = best
        assigned[ui] = (target, task, _action_for_task(task))
        claimed_targets.add(target)
        task_tiles = [(x, y, p, t) for (x, y, p, t) in task_tiles
                      if (x, y) != target]
    return assigned


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
    if task == "BUILD_STRUCTURE":
        return ["BUILD_PASTURE"]
    if task == "PLACE":
        # PLACE is handled by the carry-goose pipeline in _unit_action, not by
        # a direct action spec. Returning PICKUP here would make a unit standing
        # on the coop try to grab from a non-shed tile. Keep it inert.
        return ["PASS"]
    if task == "FEED":
        return ["FEED"]
    if task == "CARE":
        return ["CARE"]
    if task == "COLLECT_FERTILIZER":
        return ["COLLECT_FERTILIZER"]
    if task == "FERTILIZE":
        return ["FERTILIZE"]
    return ["PASS"]


def _market_orders(me, private, market, day, step=0, buy_land=BUY_LAND, hire_hands=HIRE_HANDS, board_size=10, crop_mix=V1_CROPS, timed_sell=False, animals_enabled=ANIMALS_ENABLED, early_hire=EARLY_HIRE, max_hands_per_day=MAX_HANDS_PER_DAY) -> list:
    """Queue market orders: buy seeds, sell shed stock, buy land, hire hands."""
    orders: list = []

    # HIRE goes FIRST (RM-036): the engine caps market orders per turn
    # (orders[:10]), and a full shed of sell orders used to truncate HIRE out
    # of the queue — the farm ran with zero hands while tasks piled up, and
    # the goose starved. Labor is the highest-priority order when it fires.
    # Committed baseline unaffected: hire_hands=False emits no HIRE at all.
    if hire_hands:
        early = early_hire and day <= 1
        backlog = _count_backlog(me, private, day, board_size, crop_mix, animals_enabled)
        production_surface = sum(1 for row in me["tiles"] for tile in row
                                 if isinstance(tile, dict) and tile.get("kind") == "PLANT")
        desired_hands = min(max_hands_per_day, HANDS_BASE
                            + _count_animals(me) * HANDS_PER_ANIMAL
                            + production_surface // PLANTS_PER_HAND)
        if ((early or (backlog > HIRE_THRESHOLD_TASKS
                       and me["hires_today"] < desired_hands))
                and me["hires_today"] < max_hands_per_day):
            orders.append(["HIRE"])  # one HIRE per turn; engine processes it

    # Buy seeds for the crops in the mix, up to a small working stock.
    # dict.fromkeys dedupes a weighted mix (repeated entries) so a duplicate
    # crop does not queue duplicate BUY_SEED orders (RM-041).
    for crop in dict.fromkeys(crop_mix):
        stock = private["seeds"].get(crop, 0)
        if stock < SEED_STOCK_TARGET and me["money"] >= SEED_COSTS[crop]:
            orders.append(["BUY_SEED", crop, SEED_STOCK_TARGET - stock])
    # RM-036: when the wheat floor is broken (animals enabled), accumulate
    # wheat seeds up to WHEAT_MIN_TILES so the field can actually reach the
    # floor — the 1-seed restock above caps live wheat at ~1 tile, which
    # cannot sustain 1 feed/day.
    if animals_enabled and _live_wheat_tiles(farm=me) < WHEAT_MIN_TILES:
        if (private["seeds"].get("WHEAT", 0) < WHEAT_MIN_TILES
                and me["money"] >= SEED_COSTS["WHEAT"]):
            orders.append(["BUY_SEED", "WHEAT", 1])

    if (animals_enabled and day == FIRST_ANIMAL_DAY
            and _owned_animal_count(private, me, PRIMARY_ANIMAL) == 0
            and private["shed"].get("WHEAT", 0) < FIRST_HERD_WHEAT_BRIDGE):
        orders.append(["BUY_PRODUCT", "WHEAT", FIRST_HERD_WHEAT_BRIDGE - private["shed"].get("WHEAT", 0)])

    # Sell shed stock. Keep a wheat buffer for future feeding (strategy.md);
    # never sell below the floor (M10). Staples (wheat/carrot) absorb gluts,
    # so selling them steadily is fine.
    #
    # TIMED-SELL (RM-018): town consumes every 4 steps (shops) and 24 steps
    # (center); prices are highest right after a tick (inventory drained). When
    # timed_sell is ON, bias sells to the window immediately following a tick
    # (step % 4 == 0) instead of dumping the full shed every turn. This is the
    # wheat/carrot scoping (option a) — premium timing comes later if this
    # mechanism shows teeth in self-play.
    shop_interval = 4  # engine townShopSellInterval default (rules-notes.md)
    in_sell_window = (not timed_sell) or (step % shop_interval == 0)

    shed = private["shed"]
    # When animals are enabled, the wheat buffer must cover the daily feed
    # cost: WHEAT_BUFFER_PER_ANIMAL (2) × animals + WHEAT_BUFFER_BASE (5).
    # For one goose that's 7 wheat. Do NOT sell below this reserve.
    wheat_buffer = WHEAT_BUFFER_BASE
    if animals_enabled:
        animal_count = _count_animals(farm=me)
        # Reserve for the planned first animal even before it is bought
        # (RM-020). The spec floor is animals×2+5, but with zero animals that
        # sells down to 5 and makes the first purchase unfeedable — the buy
        # gate below needs 7 wheat, so the sell floor must hold 7 too.
        if animal_count == 0:
            animal_count = 1
        wheat_buffer += WHEAT_BUFFER_PER_ANIMAL * animal_count

    for item, qty in shed.items():
        if item in ("WHEAT", "CARROT"):
            buffer = wheat_buffer if item == "WHEAT" else 0
            excess = qty - buffer
            if excess > 0 and market["prices"].get(item, PRICE_FLOOR) > PRICE_FLOOR:
                # timed-sell: sell only in the window (else hold)
                if in_sell_window:
                    orders.append(["SELL", item, excess])
        elif qty > 0 and market["prices"].get(item, PRICE_FLOOR) > PRICE_FLOOR:
            if in_sell_window:
                orders.append(["SELL", item, qty])

    # RM-036 shed-space rescue: when animals are enabled and the shed is too
    # full for the wheat feed reserve, sell premium goods even at the $1
    # floor. M10: at floor, a SELL does NOT add to market inventory, so this
    # clears space without glutting the market. Without it, floor-priced
    # premium goods fill the shed and wheat DROPs get silently discarded
    # (engine DROP deletes carried items when room is 0) — the animal starves.
    if animals_enabled and _shed_room(private) < wheat_buffer:
        for item, qty in shed.items():
            if qty <= 0 or item in ("WHEAT", "GOOSE", "COW", "SHEEP"):
                continue
            orders.append(["SELL", item, qty])

    # BUY_PRODUCT is intentionally NOT issued in v1 (RM-018 rule): we grow
    # everything ourselves, and buying back is a net-zero trap. If it is ever
    # added (e.g. fertilizer for melon season), it MUST be restricted to
    # WHEAT/FERTILIZER only — never premium goods. No BUY_PRODUCT order exists
    # anywhere in this code path, which enforces the rule by absence.

    if animals_enabled:
        candidate = None
        if _owned_animal_count(private, me, PRIMARY_ANIMAL) < TARGET_COWS:
            candidate = PRIMARY_ANIMAL
        elif _owned_animal_count(private, me, SECONDARY_ANIMAL) < TARGET_SHEEP:
            candidate = SECONDARY_ANIMAL
        if candidate is not None and me["money"] >= ANIMAL_COSTS[candidate]:
            owned = _pasture_owned_count(private, me)
            pastures = _count_structures(me, ANIMAL_STRUCTURES[candidate])
            structure_ready = pastures > owned or (owned == 0 and day == FIRST_ANIMAL_DAY)
            wheat_shortfall = max(0, wheat_buffer + (WHEAT_BUFFER_PER_ANIMAL if owned else 0)
                                  - private["shed"].get("WHEAT", 0))
            if wheat_shortfall:
                orders.append(["BUY_PRODUCT", "WHEAT", wheat_shortfall])
            if structure_ready:
                orders.append(["BUY_ANIMAL", candidate, 1])

    # Buy land: quadrant #4 policy (RM-021). The engine's pinned order is
    # NE ($1k) -> SW ($2k) -> SE ($4k) with no skip-to-SE path, so "Q4" means
    # owning the whole extra chain (Q4 = SE, the 4th quadrant). The gate is
    # day <= QUADRANT4_LATEST_DAY AND money >= QUADRANT4_CASH_THRESHOLD AND
    # post-purchase reserve >= QUADRANT4_RESERVE. When the gate opens, each
    # turn buys the next pinned quadrant in the chain until the chain is done.
    # RM-015/016 already rejected "buy land whenever cash allows" for the
    # crop-only baseline; this is a different question (land + animals +
    # melon), so it goes through the same A/B discipline, not an assumption.
    if buy_land:
        n_extra = len(me["unlocked_quadrants"]) - 1  # NW is always there
        if (
            n_extra < NE_ONLY_LIMIT  # RM-052: restrict to NE only
            and day <= QUADRANT4_LATEST_DAY
            and QUADRANT4_CASH_THRESHOLD is not None
            and me["money"] >= QUADRANT4_CASH_THRESHOLD
            and me["money"] - LAND_PRICES[n_extra] >= QUADRANT4_RESERVE
        ):
            orders.append(["BUY_LAND"])

    priority = {"HIRE": 0, "BUY_SEED": 1, "BUY_PRODUCT": 2,
                "BUY_ANIMAL": 3, "SELL": 4, "BUY_LAND": 5}
    orders.sort(key=lambda order: priority.get(order[0], len(priority)))
    return orders[:10]


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


def _unit_action(pos, farm, private, day, board_size, idx=0, crop_mix=V1_CROPS, animals_enabled=ANIMALS_ENABLED, claimed_targets=None, crop_spread=CROP_SPREAD, assigned_override=None, fertilize_enabled=False):
    """One unit's action (farmer or hand): act in place or move toward task.

    Shared by farmer + hands (RM-016). Returns a farmer/hand action list, e.g.
    ["WATER"], ["HARVEST"], ["PLANT", "WHEAT"], ["EAST"], or ["PASS"].
    `idx` is the inventory slot (0 = farmer, 1+ = hands) for the M7 carry check.
    `claimed_targets` (05E): optional shared set; targets chosen by earlier
    units are excluded from this unit's selection, and this unit's chosen
    target is added to the set after assignment (per-turn local, never global).
    `assigned_override` (RM-042): optional precomputed (target, task, action_spec)
    from the closest-first global matching; when set, this unit acts on it
    instead of recomputing `_assign_task` for itself.
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

    if animals_enabled:
        inv = private["inventories"][idx] if idx < len(private["inventories"]) else {}
        carried_animal = next((animal for animal in (PRIMARY_ANIMAL, SECONDARY_ANIMAL)
                               if inv.get(animal, 0) > 0), None)
        shed_animal = next((animal for animal in (PRIMARY_ANIMAL, SECONDARY_ANIMAL)
                            if private["shed"].get(animal, 0) > 0), None)
        if carried_animal is None and shed_animal is not None:
            if _is_shed_adjacent(pos, board_size):
                return ["PICKUP", shed_animal, 1]
            return [_step_toward(pos, _shed_access_tile(board_size))]
        if carried_animal is not None:
            empty_structure = _find_empty_structure(
                farm, board_size, ANIMAL_STRUCTURES[carried_animal])
            if empty_structure is not None:
                if empty_structure == pos:
                    return ["PLACE", carried_animal]
                return [_step_toward(pos, empty_structure)]
            if _is_shed_adjacent(pos, board_size):
                return ["PLACE", carried_animal]
            return [_step_toward(pos, _shed_access_tile(board_size))]

    # RM-036 FEED mission for a unit that already carries wheat (M1): the
    # _tile_task_priority FEED condition requires shed wheat > 0, so once a
    # unit has picked up the wheat the FEED task disappears and the drop-guard
    # below would force a pickup→drop ping-pong that starves the animal.
    # This branch makes "carry wheat + unfed animal" a self-contained mission:
    # walk to the nearest unfed animal and FEED. Claims the target so other
    # units don't pile onto the same animal this turn.
    if animals_enabled and _carried_wheat(private, idx) > 0:
        def _unfed_animal(x, y):
            t = farm["tiles"][y][x]
            return (isinstance(t, dict) and "animal" in t and not t.get("fed_today"))
        tgt = _bfs_nearest(pos, farm["tiles"], board_size, _unfed_animal)
        if tgt is not None:
            if claimed_targets is not None:
                claimed_targets.add(tgt)
            if tgt == pos:
                return ["FEED"]
            return [_step_toward(pos, tgt)]

    # M1: FEED requires carried wheat. If the assigned task is FEED and this
    # unit isn't carrying wheat, first go to the shed and PICKUP one. Then walk
    # to the animal and FEED. This is the same carry-then-act pattern as PLACE.
    if assigned_override is not None:
        assigned = assigned_override
    else:
        assigned = _assign_task(
            pos,
            farm,
            private,
            day,
            board_size,
            crop_mix,
            animals_enabled,
            claimed_targets,
            crop_spread,
            fertilize_enabled,
        )
    on_feed_mission = False
    on_fertilize_mission = False
    if assigned is not None and animals_enabled:
        target, task, _ = assigned
        if task == "FEED":
            on_feed_mission = True
            carried_wheat = private["inventories"][idx].get("WHEAT", 0) if idx < len(private["inventories"]) else 0
            if carried_wheat == 0 and private["shed"].get("WHEAT", 0) > 0:
                # Batch PICKUP: grab enough wheat for ALL unfed animals in one trip,
                # not 1 wheat per trip. Saves ~7 round trips/day with 8 animals.
                pending = _count_unfed_animals(farm)
                if pending > 0:
                    want = min(pending, private["shed"].get("WHEAT", 0))
                    if _is_shed_adjacent(pos, board_size):
                        return ["PICKUP", "WHEAT", want]
                    return [_step_toward(pos, _shed_access_tile(board_size))]
        # RM-045 FERTILIZE: carry-then-act like FEED. FERTILIZE consumes 1
        # carried FERTILIZER (engine). Pick it up at the shed first, then walk
        # to the fertilizable melon tile.
        if task == "FERTILIZE":
            on_fertilize_mission = True
            carried_fert = private["inventories"][idx].get("FERTILIZER", 0) if idx < len(private["inventories"]) else 0
            if carried_fert == 0 and private["shed"].get("FERTILIZER", 0) > 0:
                if _is_shed_adjacent(pos, board_size):
                    return ["PICKUP", "FERTILIZER", 1]
                return [_step_toward(pos, _shed_access_tile(board_size))]

    # RM-036 guard: when animals are enabled and this unit is NOT on a FEED
    # mission, carried wheat must be dropped at the shed before the day-end
    # auto-drop. The engine's `_drop_inventories_to_shed` fills the shed in
    # inventory order and discards the rest (M7) — a shed full of
    # melon/strawberry displaces carried wheat, the buffer dies, and the
    # animal escapes. Skipping FEED missions avoids a pickup→drop ping-pong.
    if animals_enabled and not on_feed_mission and _carried_wheat(private, idx) > 0:
        if _is_shed_adjacent(pos, board_size):
            return ["DROP"]
        return [_step_toward(pos, _shed_access_tile(board_size))]

    if assigned is None:
        return ["PASS"]

    target, task, action_spec = assigned

    if claimed_targets is not None:
        claimed_targets.add(target)
    if target == pos:
        if task == "PLANT":
            # RM-036: production-side wheat reserve. FEED drains shed wheat
            # 1/day/animal; when the spread field drifts to premium crops,
            # production can't replenish it and the animal starves even with
            # the sell-side buffer intact. If live wheat tiles fall below
            # WHEAT_MIN_TILES and we hold a wheat seed, force WHEAT.
            if animals_enabled and _live_wheat_tiles(farm) < WHEAT_MIN_TILES:
                if private["seeds"].get("WHEAT", 0) > 0:
                    return ["PLANT", "WHEAT"]
            # RM-036: the priority-8 empty-tile PLANT above only exists when
            # the feed reserve is broken — but the same force-WHEAT rule must
            # hold for that path too (it does; this branch is reached first).
            if crop_spread:
                # RM-036: pick by tile-position hash so the mix actually
                # spreads. Old behavior planted the first crop with seeds
                # (mix order) every time, which made any mix a wheat
                # monoculture (verified 2026-08-16) and silently invalidated
                # RM-017's mix A/Bs.
                available = [c for c in crop_mix if private["seeds"].get(c, 0) > 0]
                if not available:
                    return ["PASS"]
                return ["PLANT", available[(pos[0] * 7 + pos[1] * 13) % len(available)]]
            for crop in crop_mix:
                if private["seeds"].get(crop, 0) > 0:
                    return ["PLANT", crop]
            return ["PASS"]
        if task == "BUILD_STRUCTURE":
            return ["BUILD_PASTURE"]
        return action_spec
    return [_step_toward(pos, target)]


def _find_empty_structure(farm, board_size, structure):
    """First empty compatible structure, or None."""
    for y in range(board_size):
        for x in range(board_size):
            t = farm["tiles"][y][x]
            if isinstance(t, dict) and t.get("kind") == structure and "animal" not in t:
                return (x, y)
    return None


def _effective_crop_mix(me, crop_mix=V1_CROPS, q4_enabled=True) -> tuple:
    """Crop mix for this turn (RM-021 Q4).

    When the Q4 chain is fully owned (all 3 extra quadrants unlocked) and the
    Q4 policy is enabled, add QUADRANT4_CROP (MELON, TICKET-16) to the mix so
    empty Q4 tiles get planted with the committed Q4 crop. The base mix is
    still planted everywhere else — PLANT picks the first available seed in
    mix order, so MELON is appended last to keep wheat/carrot priority on
    the original field.
    """
    if q4_enabled and QUADRANT4_CROP is not None:
        n_extra = len(me["unlocked_quadrants"]) - 1
        if n_extra >= len(LAND_ORDER) and QUADRANT4_CROP not in crop_mix:
            return tuple(crop_mix) + (QUADRANT4_CROP,)
    return tuple(crop_mix)


def agent(obs, configuration=None, buy_land=BUY_LAND, hire_hands=HIRE_HANDS, crop_mix=V1_CROPS, timed_sell=False, animals_enabled=ANIMALS_ENABLED, early_hire=EARLY_HIRE, crop_spread=CROP_SPREAD, closest_first=True, max_hands_per_day=MAX_HANDS_PER_DAY, fertilize_enabled=False):
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
    step = obs.get("step", day * 24 + obs.get("hour", 0))

    # Q4 crop policy (RM-021): add MELON to the mix once the full Q4 chain is
    # owned, so the new quadrant is planted with the committed Q4 crop.
    effective_mix = _effective_crop_mix(me, crop_mix, q4_enabled=buy_land)

    # Per-turn claimed targets (05E): local to this agent() call, empty every
    # turn. Farmer picks first, then each hand picks from the remaining targets.
    # RM-042 closest_first: precompute a global closest-unit-first matching so
    # the farmer can't steal a hand's nearby tile and force a long second walk.
    claimed_targets = set()
    units = [(me["farmer"][0], me["farmer"][1])] + [(hx, hy) for hx, hy in me["hands"]]
    overrides = None
    if closest_first:
        overrides = _closest_first_assign(
            units, me, private, day, board_size, effective_mix,
            animals_enabled, claimed_targets, fertilize_enabled)

    market = _market_orders(me, private, obs["market"], day, step=step,
                            buy_land=buy_land, hire_hands=hire_hands,
                            board_size=board_size, crop_mix=effective_mix,
                            timed_sell=timed_sell, animals_enabled=animals_enabled,
                            early_hire=early_hire, max_hands_per_day=max_hands_per_day)

    farmer_action = _unit_action((me["farmer"][0], me["farmer"][1]),
                                 me, private, day, board_size, idx=0,
                                 crop_mix=effective_mix, animals_enabled=animals_enabled,
                                 claimed_targets=claimed_targets, crop_spread=crop_spread,
                                 assigned_override=overrides.get(0) if overrides else None,
                                 fertilize_enabled=fertilize_enabled)
    hand_actions = [_unit_action((hx, hy), me, private, day, board_size,
                                 idx=i + 1, crop_mix=effective_mix,
                                 animals_enabled=animals_enabled,
                                 claimed_targets=claimed_targets, crop_spread=crop_spread,
                                 assigned_override=overrides.get(i + 1) if overrides else None,
                                 fertilize_enabled=fertilize_enabled)
                    for i, (hx, hy) in enumerate(me["hands"])]

    return {"farmer": farmer_action, "hands": hand_actions, "market": market}
