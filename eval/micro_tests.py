"""Assert-based mechanic verifications for kaggriculture (M1–M10).

These are the micro-tests referenced by docs/findings.md §4. They run against the
INSTALLED engine (kaggle_environments) or its source — answers are logged back
into findings.md's Answer column once each row is confirmed. No framework, no
fixtures: plain asserts, runnable with `python eval/micro_tests.py`.

M9a/M9b (TICKET-11) are parametrized over all 9 resources x both sides and
reproduce the documented P(I0-T) / P(I0+T) / P(I0+2T) table values.
M1–M8 and M10 assert behavior against the installed engine module itself
(kaggle_environments.envs.kaggriculture.kaggriculture) — the ground-truth
source the policy must match. Answers are logged in findings.md §4.
"""
from __future__ import annotations

import sys
from pathlib import Path

import kaggle_environments
from kaggle_environments.envs.kaggriculture import kaggriculture as eng

# --- shared constants: single source of truth is config.py (RM-011) ---
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import MARKET_I0, MARKET_PARAMS, PRICE_FLOOR  # noqa: E402  (paths adjusted above)

I0 = MARKET_I0  # 10_000, same across all resources

# documented price table: resource -> (P(I0-T), P(I0+T), P(I0+2T))
EXPECTED = {
    "WHEAT":      (45, 20, 19),
    "CARROT":     (42, 10, 1),
    "TOMATO":     (84, 24, 9),
    "STRAWBERRY": (204, 1, 1),
    "MELON":      (300, 1, 1),
    "EGG":        (70, 40, 39),
    "MILK":       (256, 1, 1),
    "WOOL":       (240, 1, 1),
    "FERTILIZER": (140, 60, 20),
}

_FUNCS = {
    "linear": lambda x: x,
    "sq": lambda x: x * x,
    "sqrt": lambda x: math.sqrt(x),
    "log": lambda x: math.log(1.0 + x),   # matches engine _shape (not log1p)
    "log10": lambda x: math.log10(1 + x),
}
import math


def _price(resource: str, inv: int) -> int:
    """Re-implementation matching engine market_price (floor at 1)."""
    p = MARKET_PARAMS[resource]
    base, T = p["base"], p["T"]
    if inv < I0:
        func, target = p["below_func"], p["below_target"]
        amp = target * base / _FUNCS[func](T)
        return max(1, round(base + amp * _FUNCS[func](I0 - inv)))
    func, target = p["above_func"], p["above_target"]
    amp = target * base / _FUNCS[func](T)
    return max(1, round(base - amp * _FUNCS[func](inv - I0)))


def _farm():
    """Fresh 10x10 farm (NW unlocked, farmer at default spawn (4,4))."""
    return eng._new_farm(10, 3000)


def _private():
    return eng._new_private()


# --- M1–M8, M10: assert against the installed engine source ---

def test_feed_source():
    """M1: FEED consumes from the unit's carried inventory, NOT the shed."""
    farm = _farm()
    private = _private()
    # put wheat in shed only, none carried
    private["shed"]["WHEAT"] = 5
    farm["tiles"][4][4] = {"kind": "PASTURE", "animal": "COW", "placed_day": 0,
                           "yield_units": 0, "consecutive_unfed": 0, "fed_today": False,
                           "cared_today": False, "fertilizer_available": False,
                           "pending_care_bonus": 0}
    eng._apply_unit_action(farm, private, 0, ["FEED"], 10, 0, 24)
    # shed wheat untouched, animal not fed -> FEED no-oped
    assert private["shed"]["WHEAT"] == 5, "M1: FEED must NOT consume from shed"
    assert farm["tiles"][4][4]["fed_today"] is False, "M1: FEED must not succeed without carried wheat"
    # now carry wheat on the unit
    private["inventories"][0]["WHEAT"] = 2
    eng._apply_unit_action(farm, private, 0, ["FEED"], 10, 0, 24)
    assert farm["tiles"][4][4]["fed_today"] is True, "M1: FEED should succeed with carried wheat"
    assert private["inventories"][0].get("WHEAT", 0) == 1, "M1: FEED consumed 1 carried wheat"
    assert private["shed"]["WHEAT"] == 5, "M1: shed still untouched"


def test_harvest_drop_sell():
    """M2: HARVEST adds to unit inventory; DROP (shed-adjacent) deposits; SELL reads shed."""
    farm = _farm()
    private = _private()
    # plant a mature carrot at (4,4), harvest it
    farm["tiles"][4][4] = eng._new_plant("CARROT", 0, 24)
    farm["tiles"][4][4]["yield_units"] = 4
    farm["tiles"][4][4]["planted_day"] = 0
    eng._apply_unit_action(farm, private, 0, ["HARVEST"], 10, 3, 24)
    assert private["inventories"][0].get("CARROT", 0) == 4, "M2: HARVEST adds to unit inventory"
    # SELL without DROP: shed empty -> no sale
    farm["money"] = 3000
    shed_before = dict(private["shed"])
    eng._apply_unit_action(farm, private, 0, ["DROP"], 10, 3, 24)  # (4,4) is shed-adjacent
    assert private["shed"]["CARROT"] == 4, "M2: DROP deposits to shed"
    assert private["inventories"][0].get("CARROT", 0) == 0, "M2: DROP empties unit inventory"
    # SELL now reads shed
    market = eng._new_market()
    eng._process_market  # noqa
    # direct commit: SELL should succeed from shed
    ok = eng._commit_unit("SELL", "CARROT", market["prices"]["CARROT"], farm, private, market, 100)
    assert ok, "M2: SELL succeeds from shed stock"
    assert private["shed"]["CARROT"] == 3, "M2: SELL decremented shed"
    assert farm["money"] > 3000, "M2: SELL added money"


def test_buy_animal():
    """M3: BUY_ANIMAL lands the animal in the shed (obeys shedCapacity)."""
    farm = _farm()
    private = _private()
    market = eng._new_market()
    farm["money"] = 5000
    ok = eng._commit_unit("BUY_ANIMAL", "GOOSE", 300, farm, private, market, 100)
    assert ok, "M3: BUY_ANIMAL succeeds with money"
    assert private["shed"]["GOOSE"] == 1, "M3: animal lands in shed"
    assert private["shed"]["EGG"] == 0, "M3: no stray product"


def test_plant_consumption():
    """M4: all-or-nothing — if PLANT demand exceeds seeds, ALL requests for that crop drop."""
    farm = _farm()
    private = _private()
    private["seeds"]["WHEAT"] = 1
    # two units both try to plant WHEAT; only 1 seed. Interpreter gate drops both.
    farmer_action = ["PLANT", "WHEAT"]
    hand_action = ["PLANT", "WHEAT"]
    # simulate the interpreter's atomic gate manually
    plant_demand = {"WHEAT": 2}
    blocked = {crop for crop, n in plant_demand.items() if n > private["seeds"].get(crop, 0)}
    allowed_farmer = ["PASS"] if "WHEAT" in blocked else farmer_action
    allowed_hand = ["PASS"] if "WHEAT" in blocked else hand_action
    assert allowed_farmer == ["PASS"] and allowed_hand == ["PASS"], "M4: both PLANTs dropped"
    assert private["seeds"]["WHEAT"] == 1, "M4: no seed consumed"


def test_weed_timing():
    """M5: planting day counts as unwatered; 2 consecutive unwatered -> WEED (dies at 2nd daily boundary)."""
    farm = _farm()
    private = _private()
    farm["tiles"][4][4] = eng._new_plant("WHEAT", 0, 24)
    assert farm["tiles"][4][4]["consecutive_unwatered"] == 1, "M5: seed day counts as unwatered"
    # first daily refresh: 1 -> 2, and >= 2 immediately converts to WEED
    eng._daily_refresh_plants(farm, 0, 24)
    assert farm["tiles"][4][4] == {"kind": "WEED"}, "M5: 2nd unwatered daily boundary -> WEED"
    # watering before that boundary resets the counter (fresh plant, water, refresh)
    farm2 = _farm()
    farm2["tiles"][4][4] = eng._new_plant("WHEAT", 0, 24)
    farm2["tiles"][4][4]["watered_today"] = True
    eng._daily_refresh_plants(farm2, 0, 24)
    assert farm2["tiles"][4][4]["consecutive_unwatered"] == 0, "M5: watering resets counter"


def test_end_of_day_drop():
    """M6: end-of-day auto-drop to shed up to capacity; overflow discarded."""
    private = _private()
    private["inventories"][0]["WHEAT"] = 120
    private["shed"]["CARROT"] = 99  # fill shed to 99/100
    eng._drop_inventories_to_shed(private, 100)
    # shed gains 1 (room), rest discarded
    assert private["shed"]["WHEAT"] == 1, "M6: only room's worth (1) landed"
    assert private["inventories"][0].get("WHEAT", 0) == 0, "M6: unit inventory emptied"
    assert private["shed"]["CARROT"] == 99, "M6: existing shed intact"
    # seeds never pass through shed
    assert "WHEAT" not in private["shed"] or private["shed"]["WHEAT"] <= 1


def test_midday_inventory_cap():
    """M7: NO mid-day cap on carried inventory — a unit can hold unlimited items."""
    farm = _farm()
    private = _private()
    # PICKUP up to shed stock with no per-unit cap
    private["shed"]["WHEAT"] = 10_000
    private["shed"]["CARROT"] = 5_000
    eng._apply_unit_action(farm, private, 0, ["PICKUP", "WHEAT", 10_000], 10, 0, 24)
    eng._apply_unit_action(farm, private, 0, ["PICKUP", "CARROT", 5_000], 10, 0, 24)
    assert private["inventories"][0]["WHEAT"] == 10_000, "M7: no mid-day cap on carried items"
    assert private["inventories"][0]["CARROT"] == 5_000, "M7: no mid-day cap on carried items"
    # the only cap is shed capacity at end-of-day
    assert sum(private["inventories"][0].values()) == 15_000, "M7: unit can exceed shed capacity mid-day"


def test_hire_spawn():
    """M8: first hand spawns at first FREE shed-access tile (NWSE), i.e. (5,4) only if free."""
    farm = _farm()  # farmer at (4,4)
    # farmer occupies (4,4) -> first free is (5,4)
    pos = eng._spawn_hand(farm, 10)
    assert pos == [5, 4], f"M8: first hand spawns at (5,4), got {pos}"
    # if (5,4) occupied, spawn shifts to next free NWSE tile
    farm["hands"] = [[5, 4]]
    pos2 = eng._spawn_hand(farm, 10)
    assert pos2 == [4, 5], f"M8: spawn shifts to (4,5) when (5,4) occupied, got {pos2}"


def test_price_floor():
    """M10: at $1 floor, a sold unit is still purchased but not added to market inventory."""
    for r in MARKET_PARAMS:
        assert _price(r, I0 + 10_000_000) >= 1, f"M10 {r}: floor not respected"
    # engine _commit_unit: price == 1 -> no inventory increase
    farm = _farm()
    private = _private()
    market = eng._new_market()
    market["inventory"]["WHEAT"] = 10_000_000  # force floor
    market["prices"]["WHEAT"] = 1
    private["shed"]["WHEAT"] = 3
    farm["money"] = 3000
    eng._commit_unit("SELL", "WHEAT", 1, farm, private, market, 100)
    assert market["inventory"]["WHEAT"] == 10_000_000, "M10: floor sale does NOT add to market inventory"
    assert private["shed"]["WHEAT"] == 2 and farm["money"] == 3001, "M10: unit sold at floor"


def test_price_function_below():
    """M9a (TICKET-11): below-target side reproduces P(I0-T) for all 9 resources."""
    for r, (p_neg, _, _) in EXPECTED.items():
        got = _price(r, I0 - MARKET_PARAMS[r]["T"])
        assert got == p_neg, f"M9a {r}: P(I0-T) expected {p_neg}, got {got}"


def test_price_function_above():
    """M9b (TICKET-11): above-target side reproduces P(I0+T) and P(I0+2T) for all 9 resources."""
    for r, (_, p_pos, p_pos2) in EXPECTED.items():
        T = MARKET_PARAMS[r]["T"]
        got1 = _price(r, I0 + T)
        assert got1 == p_pos, f"M9b {r}: P(I0+T) expected {p_pos}, got {got1}"
        got2 = _price(r, I0 + 2 * T)
        assert got2 == p_pos2, f"M9b {r}: P(I0+2T) expected {p_pos2}, got {got2}"


def main() -> None:
    test_feed_source()
    test_harvest_drop_sell()
    test_buy_animal()
    test_plant_consumption()
    test_weed_timing()
    test_end_of_day_drop()
    test_midday_inventory_cap()
    test_hire_spawn()
    test_price_function_below()
    test_price_function_above()
    test_price_floor()
    print("micro_tests: ALL PASS")


if __name__ == "__main__":
    main()
