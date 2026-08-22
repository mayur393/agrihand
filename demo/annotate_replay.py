#!/usr/bin/env python3
"""Annotate a kaggriculture replay with per-step plain-language captions.

Turns each step's raw actions + resulting state into human-readable lines
covering every engine action and entity (crops, animals, products, shops,
fertilizer, shed, land, market). Stdlib-only; read-only on the replay.

Usage:
    .venv/bin/python demo/annotate_replay.py <replay.json> > annotated.json
Output: JSON list, one object per step:
    {"step":N, "day":D, "hour":H,
     "players": [{"name":..., "caption":[...], "money":..., "shed":..., "seeds":...}],
     "prices": {...}, "shops": [...]}
"""
from __future__ import annotations

import json
import sys

# --- engine truth (mirrors kaggriculture.py constants) ----------------------
CROPS = {
    "WHEAT":      {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}
ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP",    "product": "EGG"},
    "COW":   {"cost": 400, "structure": "PASTURE", "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "product": "WOOL"},
}
SHOPS = {
    "BAKERY": ["EGG", "WHEAT"], "PIZZA_SHOP": ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT": ["EGG", "WHEAT", "STRAWBERRY"], "YARN_STORE": ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"], "PET_CAFE": ["CARROT"],
    "SMOOTHIE_SHOP": ["STRAWBERRY", "MILK"], "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}
LAND_ORDER = ["NE", "SW", "SE"]
LAND_PRICES = [1000, 2000, 4000]
MOVE = {"NORTH": "moved north", "SOUTH": "moved south", "EAST": "moved east", "WEST": "moved west"}
STRUCTURE = {"COOP": "coop", "PASTURE": "pasture"}


def fib(n: int) -> int:
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def describe_market(actions: list, obs: dict) -> list[str]:
    """Human lines for the market orders of one player this step."""
    lines = []
    me = obs["farms"][obs["player"]]
    money = me["money"]
    for a in actions or []:
        if not isinstance(a, list) or not a:
            continue
        op = a[0]
        if op == "BUY_SEED" and len(a) >= 3:
            crop, n = a[1], a[2]
            cost = CROPS[crop]["seed"] * n
            lines.append(f"Bought {n}× {crop.lower()} seed (${cost}).")
        elif op == "BUY_PRODUCT" and len(a) >= 3:
            item, n = a[1], a[2]
            price = obs.get("market", {}).get("prices", {}).get(item, "?")
            lines.append(f"Bought {n}× {item.lower()} from market (${price}/ea).")
        elif op == "BUY_ANIMAL" and len(a) >= 3:
            animal, n = a[1], a[2]
            cost = ANIMALS[animal]["cost"] * n
            lines.append(f"Bought {n}× {animal.lower()} (${cost}) → shed.")
        elif op == "SELL" and len(a) >= 3:
            item, n = a[1], a[2]
            price = obs.get("market", {}).get("prices", {}).get(item, "?")
            lines.append(f"Sold {n}× {item.lower()} (${price}/ea).")
        elif op == "HIRE":
            # Obs is post-hire: hands already includes the new hire, and
            # hires_today is the count after this hire. The cost of the hire
            # just made = fib(hires_today - 1)  (1,1,2,3,...).
            n_hands = len(me.get("hands", []))
            cost = fib(max(0, me.get("hires_today", 1) - 1))
            lines.append(f"Hired hand (${cost}, {n_hands} total hands).")
        elif op == "BUY_LAND":
            idx = len(me.get("unlocked_quadrants", [])) - 1
            quad = LAND_ORDER[idx] if 0 <= idx < len(LAND_ORDER) else "?"
            price = LAND_PRICES[idx] if 0 <= idx < len(LAND_PRICES) else "?"
            lines.append(f"Unlocked {quad} quadrant (${price}).")
        elif op == "PASS":
            lines.append("No market order.")
    return lines


def describe_unit(ops: list, obs: dict, who: str) -> list[str]:
    """Human lines for one unit's (farmer/hand) actions this step."""
    lines = []
    me = obs["farms"][obs["player"]]
    tile = me["tiles"][me["farmer"][1]][me["farmer"][0]] if who == "farmer" else None
    for a in ops or []:
        if not isinstance(a, list) or not a:
            continue
        op = a[0]
        if op in MOVE:
            lines.append(f"{MOVE[op]}.")
        elif op == "PASS":
            lines.append("Waited (PASS).")
        elif op == "PICKUP" and len(a) >= 2:
            item = a[1]
            lines.append(f"Picked up {item.lower()} from shed.")
        elif op == "PLANT" and len(a) >= 2:
            lines.append(f"Planted {a[1].lower()} seed.")
        elif op == "WATER":
            lines.append("Watered crop (helps it grow/yield).")
        elif op == "HARVEST":
            lines.append("Harvested a mature crop → inventory.")
        elif op == "FERTILIZE":
            lines.append("Applied fertilizer (boosts yield).")
        elif op == "DIG":
            lines.append("Cleared a weed.")
        elif op == "FEED":
            lines.append("Fed an animal.")
        elif op == "CARE":
            lines.append("Cared for an animal (keeps it healthy).")
        elif op == "COLLECT_FERTILIZER":
            lines.append("Collected fertilizer.")
        elif op == "BUILD_COOP":
            lines.append("Built a coop.")
        elif op == "BUILD_PASTURE":
            lines.append("Built a pasture.")
        elif op == "PLACE" and len(a) >= 2:
            animal = a[1]
            lines.append(f"Placed {animal.lower()} in {STRUCTURE.get(ANIMALS[animal]['structure'], 'structure')}.")
        elif op == "SELL":
            lines.append("Sold item from shed.")
    return lines


def annotate_step(step, idx: int, players: list[str]) -> dict:
    # step is a list of per-agent dicts: {"observation":..., "action":..., "status":..., "reward":...}
    o0 = step[0]["observation"]
    out = {
        "step": o0.get("step", idx),
        "day": o0.get("day", 0),
        "hour": o0.get("hour", 0),
        "players": [],
        "prices": (o0.get("market", {}) or {}).get("prices", {}),
        "shops": (o0.get("town", {}) or {}).get("unlocked_shops", []),
    }
    for i, s in enumerate(step):
        obs = s["observation"]
        me = obs["farms"][i]
        priv = obs.get("private", {}) or {}
        act = s.get("action") if isinstance(s.get("action"), dict) else {}
        caption = []
        caption += describe_unit([act.get("farmer", ["PASS"])], obs, "farmer")
        for h in act.get("hands", []) or []:
            caption += describe_unit([h], obs, "hand")
        caption += describe_market(act.get("market", []) or [], obs)
        out["players"].append({
            "name": players[i] if i < len(players) else f"Player {i+1}",
            "caption": caption,
            "money": me.get("money", 0),
            "shed": priv.get("shed", {}),
            "seeds": priv.get("seeds", {}),
        })
    return out


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    replay = json.load(open(sys.argv[1]))
    players = [a.get("name", f"Player {i+1}") for i, a in enumerate(replay.get("info", {}).get("Agents", []))]
    steps = replay.get("steps", [])
    out = [annotate_step(st, i, players) for i, st in enumerate(steps)]
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
