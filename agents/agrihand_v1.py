"""main.py — Agrihand v4: value-based Kaggriculture agent (submission entry).

Every turn the agent answers one question for every possible use of money,
land and labor: "how many dollars does this bring back before the season
ends, at the prices the market will actually pay?" Nothing is a fixed rule.

  1. Market model   — replicates the engine price curve, projects each
                      product's market inventory forward from both farms'
                      visible production and the town's demand.
  2. Plans          — crop choice per free tile, animal purchases, crew size,
                      land purchase, feed wheat, and selling, each decided by
                      projected profit (config.py holds every knob).
  3. Jobs           — every tile task (water, harvest, feed, care, plant, ...)
                      becomes a job worth some dollars; workers are matched to
                      jobs by value per turn spent (walk + act), with a small
                      bonus for keeping last turn's target.

Engine facts relied on (verified against kaggriculture.py v1.32.6):
  * unit actions resolve before market orders in the same step;
  * PLANT for a crop is dropped for EVERY unit if more units plant it than seeds held;
  * FEED consumes the unit's carried wheat; PICKUP/DROP only work on the four
    shed-access tiles; carried items auto-drop at day end (shed overflow is
    deleted);
  * a plant dies after its 2nd consecutive unwatered night (planting day
    counts as unwatered); an animal escapes after its 2nd unfed night;
  * the step-718 action is the last one processed.

ENGINE CONTRACT: the runner calls agent(observation, configuration) and
loads the LAST callable in this module, so `agent` must stay last.
"""
from __future__ import annotations

import math

import config as C

_PRODUCTS = list(C.MARKET_PARAMS)

# Per-process memory: last turn's target per unit, so workers keep a job
# instead of flip-flopping. Reset every day (hands are re-hired daily).
_MEMORY = {"day": -1, "targets": {}}


# --------------------------------------------------------------------------
# Market model
# --------------------------------------------------------------------------

def _shape(func, x):
    x = max(0.0, x)
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    if func == "log10":
        return math.log10(1.0 + x)
    return x


def price_at(item, inventory):
    """Engine market_price() for `item` at market `inventory`."""
    p = C.MARKET_PARAMS[item]
    base, T = p["base"], p["T"]
    if inventory < C.MARKET_I0:
        f = p["below_func"]
        price = base + p["below_target"] * base / _shape(f, T) * _shape(f, C.MARKET_I0 - inventory)
    else:
        f = p["above_func"]
        price = base - p["above_target"] * base / _shape(f, T) * _shape(f, inventory - C.MARKET_I0)
    return max(C.PRICE_FLOOR, int(round(price)))


def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _harvest_age(crop):
    """Age (days) at which a non-ongoing crop, watered daily, reaches max yield."""
    c = C.CROPS[crop]
    window_start = (c["max_yield_day"] + 1) // 2
    return max(c["first_yield_day"], min(c["max_yield_day"], window_start + c["max_yield"] - 2))


def _units_at_age(crop, age):
    """Units a non-ongoing crop holds at `age` if watered every window day."""
    c = C.CROPS[crop]
    window_start = (c["max_yield_day"] + 1) // 2
    return min(c["max_yield"], 1 + max(0, min(age, c["max_yield_day"]) - window_start + 1))


def _animal_units_per_production(animal):
    """Base unit + care bonus (one per cared+fed day since the last production)."""
    a = C.ANIMALS[animal]
    return 1 + (a["interval"] if C.CARE_ENABLED else 0)


def _shop_rate(product):
    """Expected daily demand one newly unlocked (random) shop adds for `product`."""
    total = 0.0
    for goods in C.SHOPS.values():
        if product in goods:
            total += C.SHOP_TICKS_PER_DAY * (2 if len(goods) == 1 else 1)
    return total / len(C.SHOPS)


class Market:
    """Projects each product's market inventory forward t days."""

    def __init__(self, obs, me, opp, private, day):
        self.day = day
        self.inventory = obs["market"]["inventory"]
        self.prices = obs["market"]["prices"]
        shops = obs["town"]["unlocked_shops"]
        self.daily_demand = {}
        for p in _PRODUCTS:
            d = 0.0 if p == "FERTILIZER" else 1.0  # town center, once a day
            for s in shops:
                goods = C.SHOPS[s]
                if p in goods:
                    d += C.SHOP_TICKS_PER_DAY * (2 if len(goods) == 1 else 1)
            self.daily_demand[p] = d
        self.n_shops = len(shops)
        self.me, self.opp, self.private = me, opp, private
        self._supply_cache = {}
        self.extra = {p: 0.0 for p in _PRODUCTS}  # units our plans add this turn

    def demand(self, product, t):
        d = self.daily_demand[product] * t * C.DEMAND_WEIGHT
        rate = _shop_rate(product)
        if rate:
            # future unlocks happen at the start of day 3, 6, ... (max 8 shops)
            n = self.n_shops
            u = (self.day // C.SHOP_UNLOCK_INTERVAL_DAYS + 1) * C.SHOP_UNLOCK_INTERVAL_DAYS
            while n < C.MAX_SHOPS and u < self.day + t:
                d += rate * (self.day + t - u) * C.DEMAND_WEIGHT
                n += 1
                u += C.SHOP_UNLOCK_INTERVAL_DAYS
        return d

    def _farm_supply(self, farm, t):
        """Units of each product `farm` will produce within t days (visible state)."""
        out = {p: 0.0 for p in _PRODUCTS}
        day = self.day
        for row in farm["tiles"]:
            for tile in row:
                if not isinstance(tile, dict):
                    continue
                if tile.get("kind") == "PLANT":
                    crop = tile["crop"]
                    c = C.CROPS[crop]
                    age = day - tile["planted_day"]
                    if c["ongoing"]:
                        units = tile.get("yield_units", 0)
                        for k in range(c["max_yield"]):
                            avail = c["first_yield_day"] + k * c["interval"]
                            if age < avail <= age + t:
                                units += 1
                        out[crop] += units
                    else:
                        target = _harvest_age(crop)
                        if age + t >= target:
                            out[crop] += max(tile.get("yield_units", 0), _units_at_age(crop, target))
                elif "animal" in tile:
                    a = C.ANIMALS[tile["animal"]]
                    since = day - tile.get("placed_day", day)
                    productive = max(0, t - max(0, a["first_yield_day"] - since))
                    out[a["product"]] += (tile.get("yield_units", 0)
                                          + productive * _animal_units_per_production(tile["animal"]) / a["interval"])
                    out["FERTILIZER"] += t
        return out

    def supply(self, t):
        key = int(math.ceil(t))
        if key not in self._supply_cache:
            ours = self._farm_supply(self.me, key)
            theirs = self._farm_supply(self.opp, key)
            stock = {p: self.private["shed"].get(p, 0) for p in _PRODUCTS}
            for inv in self.private["inventories"]:
                for p, n in inv.items():
                    if p in stock:
                        stock[p] += n
            self._supply_cache[key] = {
                p: ours[p] + stock[p] + C.OPPONENT_SUPPLY_WEIGHT * theirs[p] for p in _PRODUCTS}
        return self._supply_cache[key]

    def projected_price(self, product, t, extra_units=0.0):
        """Price of `product` about t days from now, after our planned extra units."""
        inv = (self.inventory[product] + self.supply(t)[product] + self.extra[product]
               + extra_units - self.demand(product, t))
        return price_at(product, inv)


# --------------------------------------------------------------------------
# Economic evaluations
# --------------------------------------------------------------------------

def _crop_plan_value(market, crop, day):
    """(profit, rate_per_tile_day, units, cycle_days) for planting `crop` today."""
    c = C.CROPS[crop]
    days_left = C.LAST_HARVEST_DAY - day
    if days_left < c["first_yield_day"]:
        return None
    if c["ongoing"]:
        units = sum(1 for k in range(c["max_yield"])
                    if c["first_yield_day"] + k * c["interval"] <= days_left)
        last = min(days_left, c["first_yield_day"] + (c["max_yield"] - 1) * c["interval"])
        cycle = last + 1
        sale_t = (c["first_yield_day"] + last) / 2.0
        waters = cycle * 0.5 + 1  # every other day keeps it alive
    else:
        target = min(_harvest_age(crop), days_left)
        units = _units_at_age(crop, target)
        cycle = max(1, target)
        sale_t = target
        window_start = (c["max_yield_day"] + 1) // 2
        waters = max(0, target - window_start + 1) + window_start * 0.5 + 1
    price = market.projected_price(crop, sale_t, units / 2.0)
    labor = (waters + 2) * C.LABOR_COST_PER_ACTION
    profit = units * price - c["seed"] - labor
    return profit, profit / cycle, units, cycle


def plan_crops(market, day, n_tiles, commit=True):
    """Greedy crop plan for n free tiles; each pick raises that crop's projected glut."""
    plan = []
    added = {}
    for _ in range(n_tiles):
        best = None
        for crop in C.CROPS:
            v = _crop_plan_value(market, crop, day)
            if v is None:
                continue
            profit, rate, units, _cycle = v
            if profit < C.MIN_CROP_PROFIT:
                continue
            if best is None or rate > best[1]:
                best = (crop, rate, profit, units)
        if best is None:
            break
        crop, rate, profit, units = best
        plan.append((crop, rate, profit))
        market.extra[crop] += units
        added[crop] = added.get(crop, 0) + units
    if not commit:
        for crop, u in added.items():
            market.extra[crop] -= u
    return plan


def marginal_crop_rate(market, day):
    plan = plan_crops(market, day, 1, commit=False)
    return plan[0][1] if plan else 0.0


def animal_value(market, animal, day, herd_extra=0):
    """Expected season profit of buying one `animal` today."""
    a = C.ANIMALS[animal]
    days_left = C.LAST_HARVEST_DAY - day
    place_day = day + 1
    productions = 0
    avail = place_day + a["first_yield_day"]
    while avail <= C.LAST_HARVEST_DAY:
        productions += 1
        avail += a["interval"]
    units = productions * _animal_units_per_production(animal)
    if units <= 0:
        return -a["cost"]
    t_mid = (a["first_yield_day"] + 1 + days_left) / 2.0
    price = market.projected_price(a["product"], t_mid, units / 2.0 + herd_extra * units)
    live_days = max(0, days_left - 1)
    fert_price = market.projected_price("FERTILIZER", live_days / 2.0, live_days / 2.0)
    feed = live_days * max(market.prices.get("WHEAT", 25), C.MARKET_PARAMS["WHEAT"]["base"])
    labor = live_days * C.ANIMAL_LABOR_ACTIONS * C.LABOR_COST_PER_ACTION
    return units * price + live_days * fert_price - feed - labor - a["cost"]


# --------------------------------------------------------------------------
# Farm helpers
# --------------------------------------------------------------------------

def _shed_tiles(board):
    h = board // 2
    return [(h - 1, h - 1), (h, h - 1), (h - 1, h), (h, h)]


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _step(pos, target):
    """One move toward target. The board has no obstacles (LOCKED is walkable)."""
    dx, dy = target[0] - pos[0], target[1] - pos[1]
    if dx and abs(dx) >= abs(dy):
        return "EAST" if dx > 0 else "WEST"
    if dy:
        return "SOUTH" if dy > 0 else "NORTH"
    return "PASS"


def _carried(private, idx):
    invs = private["inventories"]
    return invs[idx] if idx < len(invs) else {}


def _sellable_value(inv, prices):
    return sum(n * prices.get(item, 0) for item, n in inv.items() if item in prices)


# --------------------------------------------------------------------------
# The planner
# --------------------------------------------------------------------------

class Planner:
    def __init__(self, obs):
        self.player = obs["player"]
        self.me = obs["farms"][self.player]
        self.opp = obs["farms"][1 - self.player]
        self.private = obs["private"]
        self.day = obs["day"]
        self.hour = obs.get("hour", 0)
        self.step = self.day * C.TURNS_PER_DAY + self.hour
        self.board = len(self.me["tiles"])
        self.tiles = self.me["tiles"]
        self.shed = self.private["shed"]
        self.seeds = self.private["seeds"]
        self.money = float(self.me["money"])
        self.market = Market(obs, self.me, self.opp, self.private, self.day)
        self.prices = self.market.prices
        self.last_day = self.day >= C.SEASON_DAYS - 1
        self.units = [tuple(self.me["farmer"])] + [tuple(h) for h in self.me["hands"]]
        self.shed_tiles = _shed_tiles(self.board)
        self.build_target = None
        self.want_animal = None
        self.structure_ready = False
        self._scan()

    # ---- state scan ------------------------------------------------------
    def _scan(self):
        self.free_tiles, self.weeds, self.empty_structs = [], [], []
        self.animal_tiles, self.plant_tiles = [], []
        for y, row in enumerate(self.tiles):
            for x, t in enumerate(row):
                if t == "LOCKED":
                    continue
                if t is None:
                    self.free_tiles.append((x, y))
                elif t.get("kind") == "WEED":
                    self.weeds.append((x, y))
                elif t.get("kind") == "PLANT":
                    self.plant_tiles.append((x, y))
                elif "animal" in t:
                    self.animal_tiles.append((x, y))
                elif t.get("kind") in C.BUILD_OP:
                    self.empty_structs.append((x, y))
        self.carried_total = {}
        for inv in self.private["inventories"]:
            for item, n in inv.items():
                self.carried_total[item] = self.carried_total.get(item, 0) + n
        self.unplaced = {a: self.shed.get(a, 0) + self.carried_total.get(a, 0) for a in C.ANIMALS}
        self.n_animals = len(self.animal_tiles) + sum(self.unplaced.values())

    def _near_shed(self, tiles):
        return sorted(tiles, key=lambda p: min(_dist(p, s) for s in self.shed_tiles))

    # ---- strategic plans -------------------------------------------------
    def plan(self):
        m = self.market
        self.crop_rate = marginal_crop_rate(m, self.day)
        if not self.last_day:
            self._plan_animals()
        n_free = len(self.free_tiles) + len(self.weeds) - (1 if self.build_target else 0)
        self.crop_plan = plan_crops(m, self.day, max(0, n_free)) if not self.last_day else []

    def _plan_animals(self):
        if (self.n_animals >= C.MAX_ANIMALS
                or sum(self.unplaced.values()) >= C.MAX_UNPLACED_ANIMALS):
            return
        m = self.market
        best, best_v = None, C.ANIMAL_MIN_PROFIT
        opportunity = 0.0
        if len(self.free_tiles) + len(self.weeds) <= C.ANIMAL_OPPORTUNITY_FREE_TILES:
            opportunity = (self.crop_rate * max(0, C.LAST_HARVEST_DAY - self.day)
                           * C.ANIMAL_TILE_OPPORTUNITY)
        for animal in C.ANIMALS:
            v = animal_value(m, animal, self.day) - opportunity
            if v > best_v:
                best, best_v = animal, v
        if best is None:
            return
        self.want_animal = best
        structure = C.ANIMALS[best]["structure"]
        empty_ok = [p for p in self.empty_structs if self.tiles[p[1]][p[0]]["kind"] == structure]
        pending = sum(n for a, n in self.unplaced.items() if C.ANIMALS[a]["structure"] == structure)
        if len(empty_ok) <= pending:
            cands = self._near_shed(self.free_tiles) or self._near_shed(self.weeds)
            if cands:
                self.build_target = (cands[0], structure)
        # The animal can wait in the shed while its structure goes up this turn
        # or next, so a structure under construction counts as ready.
        self.structure_ready = len(empty_ok) + (1 if self.build_target else 0) > pending

    # ---- market orders ---------------------------------------------------
    def market_orders(self, job_count):
        orders_hire, orders_sell, orders_buy = [], [], []
        prices = self.prices
        budget = self.money - C.CASH_RESERVE

        # Hire: size the crew to today's job load; stop when a hire costs more
        # than the work it would do.
        turns_left = C.TURNS_PER_DAY - 1 - self.hour
        if turns_left > 2:
            needed_units = math.ceil(job_count * C.TURNS_PER_JOB / turns_left)
            if self.day >= C.MIN_CREW_FROM_DAY and not self.last_day:
                needed_units = max(needed_units, C.MIN_CREW)
            want = needed_units - len(self.units)
            hires = self.me["hires_today"]
            while want > 0 and len(orders_hire) < C.MAX_MARKET_ORDERS - 2:
                cost = _fib(hires)
                if cost > C.MAX_HIRE_COST or cost > budget:
                    break
                if cost > C.HIRE_VALUE_PER_JOB * turns_left / C.TURNS_PER_JOB:
                    break
                orders_hire.append(["HIRE"])
                budget -= cost
                hires += 1
                want -= 1

        # Sell: demand-matched. Each product sells only while the next unit
        # still fetches the reserve price; the rest waits in the shed for the
        # town to drain the market. Shed pressure or season end sells all.
        days_left = C.SEASON_DAYS - 1 - self.day
        feed_reserve = 0
        if not self.last_day and self.n_animals:
            feed_reserve = C.FEED_RESERVE_PER_ANIMAL * self.n_animals + C.FEED_RESERVE_BASE
        shed_used = sum(self.shed.values())
        carried_goods = sum(n for item, n in self.carried_total.items() if item in C.MARKET_PARAMS)
        sell_all = (days_left <= C.SELL_ALL_DAYS_LEFT
                    or shed_used + carried_goods >= C.SELL_PRESSURE_FILL)
        inventory = self.market.inventory
        expected_income = 0.0
        for item in _PRODUCTS:
            qty = self.shed.get(item, 0)
            if self.last_day:
                qty += self.carried_total.get(item, 0)  # same-step drops sell too
            if item == "WHEAT":
                qty -= max(0, feed_reserve - self.carried_total.get("WHEAT", 0))
            if qty <= 0:
                continue
            if not sell_all:
                reserve = C.SELL_RESERVE_FRACTION * C.MARKET_PARAMS[item]["base"]
                inv = inventory[item]
                n = 0
                while n < qty and price_at(item, inv + n) >= reserve:
                    n += 1
                qty = n
            if qty <= 0:
                continue
            orders_sell.append(["SELL", item, int(qty)])
            expected_income += qty * prices.get(item, 0) * 0.5
        budget += expected_income

        if not self.last_day:
            # Feed wheat: keep the reserve topped up for the whole herd.
            have = self.shed.get("WHEAT", 0) + self.carried_total.get("WHEAT", 0)
            need = feed_reserve - have
            if need > 0:
                need = min(need, self.n_animals * (days_left + 1))
                cost = need * (prices.get("WHEAT", 25) + 2)
                if cost <= budget + C.CASH_RESERVE:
                    orders_buy.append(["BUY_PRODUCT", "WHEAT", int(need)])
                    budget -= cost

            # Animal purchase (only when a matching empty structure is waiting).
            if self.want_animal and self.structure_ready:
                cost = C.ANIMALS[self.want_animal]["cost"]
                if budget - cost >= C.ANIMAL_CASH_RESERVE and shed_used < C.SHED_CAPACITY - 5:
                    orders_buy.append(["BUY_ANIMAL", self.want_animal, 1])
                    budget -= cost

            # Land: next quadrant when the farm is full and more tiles pay back.
            land = self._land_price(budget)
            if land:
                orders_buy.append(["BUY_LAND"])
                budget -= land

            # Seeds for the crop plan, best crops first, leaving cash for the
            # animals the planner still wants.
            if self.want_animal:
                reserve_count = C.ANIMAL_SEED_RESERVE_COUNT
                if self.day <= C.OPENING_LAST_DAY:
                    reserve_count = max(reserve_count, C.OPENING_ANIMALS - self.n_animals)
                budget -= C.ANIMALS[self.want_animal]["cost"] * reserve_count
            needed = {}
            for crop, _rate, _profit in self.crop_plan:
                needed[crop] = needed.get(crop, 0) + 1
            for crop, _rate, _profit in self.crop_plan:
                n = needed.get(crop, 0) - self.seeds.get(crop, 0)
                if n <= 0:
                    continue
                price = C.CROPS[crop]["seed"]
                n = min(n, int(max(0, budget) // price))
                if n > 0:
                    orders_buy.append(["BUY_SEED", crop, n])
                    budget -= n * price
                needed[crop] = 0

        orders = orders_hire + orders_sell + orders_buy
        return orders[:C.MAX_MARKET_ORDERS]

    def _land_price(self, budget):
        n_extra = len(self.me["unlocked_quadrants"]) - 1
        if n_extra >= len(C.LAND_ORDER) or self.day > C.LAND_LAST_DAY:
            return 0
        price = C.LAND_PRICES[n_extra]
        if budget - price < C.CASH_RESERVE:
            return 0
        if len(self.free_tiles) + len(self.weeds) > C.LAND_FREE_TILE_TRIGGER:
            return 0
        quadrant_tiles = (self.board // 2) ** 2
        plan = plan_crops(self.market, self.day, quadrant_tiles, commit=False)
        days = C.LAST_HARVEST_DAY - self.day
        value = sum(rate for _c, rate, _p in plan) * days * C.LAND_UTILIZATION
        return price if value >= price * C.LAND_ROI else 0

    # ---- jobs --------------------------------------------------------------
    def jobs(self):
        """List of (value, target, kind, arg, needs_item)."""
        jobs = []
        day, hour = self.day, self.hour
        prices = self.prices
        m = self.market
        harvest_ok = not self.last_day or hour <= C.LAST_HARVEST_HOUR

        for (x, y) in self.plant_tiles:
            t = self.tiles[y][x]
            crop = t["crop"]
            c = C.CROPS[crop]
            age = day - t["planted_day"]
            price = prices.get(crop, 0)
            y_units = t.get("yield_units", 0)
            window_start = (c["max_yield_day"] + 1) // 2
            ready = False
            if age >= c["first_yield_day"] and y_units > 0 and harvest_ok:
                if c["ongoing"] or self.last_day:
                    ready = True
                else:
                    target = _harvest_age(crop)
                    if (age > c["max_yield_day"] or y_units >= c["max_yield"]
                            or (age >= target and (t["watered_today"] or hour >= 18))
                            or day + (target - age) > C.LAST_HARVEST_DAY):
                        ready = True
            if ready:
                urgency = 1.5 if (not c["ongoing"] and age >= c["max_yield_day"]) else 1.0
                jobs.append((max(1.0, y_units * price) * urgency, (x, y), "HARVEST", None, None))
                continue
            if self.last_day or t["watered_today"]:
                continue
            gain = 0.0
            if not c["ongoing"] and window_start <= age <= c["max_yield_day"] and y_units < c["max_yield"]:
                bonus = 2 if t.get("fertilized_until_day", -1) >= day else 1
                gain = bonus * m.projected_price(crop, max(0, _harvest_age(crop) - age))
            if t.get("consecutive_unwatered", 0) >= 1:
                if c["ongoing"]:
                    remaining = y_units + sum(1 for k in range(c["max_yield"])
                                              if c["first_yield_day"] + k * c["interval"] > age)
                else:
                    remaining = max(y_units, _units_at_age(crop, _harvest_age(crop)))
                keep = max(C.WATER_KEEP_ALIVE_MIN, remaining * price)
                jobs.append((keep + gain, (x, y), "WATER", None, None))
            else:
                jobs.append((gain + C.WATER_ROUTINE_VALUE, (x, y), "WATER", None, None))

        for (x, y) in self.animal_tiles:
            t = self.tiles[y][x]
            a = C.ANIMALS[t["animal"]]
            product_price = prices.get(a["product"], 0)
            if t.get("yield_units", 0) > 0 and harvest_ok:
                full = t["yield_units"] >= a["max_held"] - 1
                jobs.append((t["yield_units"] * product_price * (1.5 if full else 1.0),
                             (x, y), "HARVEST", None, None))
            if t.get("fertilizer_available"):
                jobs.append((prices.get("FERTILIZER", 0), (x, y), "COLLECT_FERTILIZER", None, None))
            if day <= C.SEASON_DAYS - 2 and not t.get("fed_today"):
                v = C.FEED_VALUE_DANGER if t.get("consecutive_unfed", 0) >= 1 else C.FEED_VALUE_NORMAL
                jobs.append((v, (x, y), "FEED", None, "WHEAT"))
            if C.CARE_ENABLED and day <= C.SEASON_DAYS - 3 and not t.get("cared_today"):
                care = product_price if t.get("fed_today") else product_price * C.CARE_UNFED_FRACTION
                jobs.append((care, (x, y), "CARE", None, None))

        if not self.last_day:
            for (x, y) in self.empty_structs:
                kind = self.tiles[y][x]["kind"]
                for animal, n in self.unplaced.items():
                    if n > 0 and C.ANIMALS[animal]["structure"] == kind:
                        jobs.append((C.PLACE_VALUE, (x, y), "PLACE", animal, animal))
                        break
            reserved = None
            if self.build_target:
                (bx, by), structure = self.build_target
                reserved = (bx, by)
                if self.tiles[by][bx] is None:
                    jobs.append((C.BUILD_VALUE, reserved, C.BUILD_OP[structure], None, None))
                else:
                    jobs.append((C.BUILD_VALUE, reserved, "DIG", None, None))
            # plant: hand out the crop plan (best first), limited by seeds in stock
            stock = dict(self.seeds)
            queue = []
            for crop, _rate, profit in self.crop_plan:
                if stock.get(crop, 0) > 0:
                    stock[crop] -= 1
                    queue.append((crop, profit))
            queue.sort(key=lambda cp: -cp[1])
            spots = [p for p in self._near_shed(self.free_tiles) if p != reserved]
            for pos, (crop, profit) in zip(spots, queue):
                jobs.append((max(C.MIN_CROP_PROFIT, profit), pos, "PLANT", crop, None))
            dig_value = max(C.DIG_MIN_VALUE, self.crop_rate * 2)
            for pos in self.weeds:
                if pos != reserved:
                    jobs.append((dig_value, pos, "DIG", None, None))

        # Drops: keep the day-end auto-drop from overflowing (overflow is
        # deleted), and empty every pocket on the last day so it can be sold.
        carried_units = sum(n for item, n in self.carried_total.items() if item in C.MARKET_PARAMS)
        shed_units = sum(self.shed.values())
        must_drop = self.last_day and hour >= 12
        if must_drop or shed_units + carried_units > C.SHED_SAFE_FILL:
            for idx in range(len(self.units)):
                v = _sellable_value(_carried(self.private, idx), prices)
                if v > 0:
                    jobs.append((v * (2.0 if must_drop else 1.0), ("SHED", idx), "DROP", None, None))
        return jobs

    # ---- assignment --------------------------------------------------------
    def assign(self, jobs):
        """Greedy matching of units to jobs by dollars per turn spent."""
        if _MEMORY["day"] != self.day:
            _MEMORY["day"] = self.day
            _MEMORY["targets"] = {}
        sticky = _MEMORY["targets"]
        candidates = []
        for ui, pos in enumerate(self.units):
            inv = _carried(self.private, ui)
            nearest_shed = min(_dist(pos, s) for s in self.shed_tiles)
            for ji, (value, target, kind, arg, need) in enumerate(jobs):
                if kind == "DROP":
                    if target[1] != ui:
                        continue
                    d = nearest_shed
                elif need and inv.get(need, 0) <= 0:
                    if self.shed.get(need, 0) <= 0:
                        continue
                    d = min(_dist(pos, s) + _dist(s, target) for s in self.shed_tiles) + 1
                else:
                    d = _dist(pos, target)
                score = value / (d + 1.0) ** C.DIST_EXPONENT
                if sticky.get(ui) == (target, kind):
                    score *= C.STICKY_BONUS
                candidates.append((score, ui, ji))
        candidates.sort(reverse=True)
        taken_units, taken_jobs, result = set(), set(), {}
        for _score, ui, ji in candidates:
            if ui in taken_units or ji in taken_jobs:
                continue
            taken_units.add(ui)
            taken_jobs.add(ji)
            result[ui] = jobs[ji]
            if len(taken_units) == len(self.units):
                break
        _MEMORY["targets"] = {ui: (j[1], j[2]) for ui, j in result.items()}
        return result

    def unit_action(self, ui, job):
        if job is None:
            return ["PASS"]
        pos = self.units[ui]
        _value, target, kind, arg, need = job
        inv = _carried(self.private, ui)
        if kind == "DROP":
            if pos in self.shed_tiles:
                return ["DROP"]
            return [_step(pos, min(self.shed_tiles, key=lambda s: _dist(pos, s)))]
        if need and inv.get(need, 0) <= 0:
            if pos in self.shed_tiles:
                if need == "WHEAT":
                    unfed = sum(1 for (x, y) in self.animal_tiles
                                if not self.tiles[y][x].get("fed_today"))
                    n = max(1, unfed - self.carried_total.get("WHEAT", 0))
                    return ["PICKUP", "WHEAT", int(min(n, self.shed.get("WHEAT", 0)))]
                return ["PICKUP", need, 1]
            hop = min(self.shed_tiles, key=lambda s: _dist(pos, s) + _dist(s, target))
            return [_step(pos, hop)]
        if pos != target:
            return [_step(pos, target)]
        if kind in ("PLANT", "PLACE"):
            return [kind, arg]
        return [kind]

    def act(self):
        self.plan()
        jobs = self.jobs()
        assignment = self.assign(jobs)
        actions = [self.unit_action(ui, assignment.get(ui)) for ui in range(len(self.units))]
        # PLANT is all-or-nothing per crop: never plant more units than seeds held.
        demand = {}
        for i, a in enumerate(actions):
            if a[0] == "PLANT":
                demand[a[1]] = demand.get(a[1], 0) + 1
                if demand[a[1]] > self.seeds.get(a[1], 0):
                    actions[i] = ["PASS"]
        useful = sum(1 for j in jobs if j[0] > C.WATER_ROUTINE_VALUE)
        return {"farmer": actions[0], "hands": actions[1:], "market": self.market_orders(useful)}


def agent(obs, configuration=None):
    """Kaggle entry point: one action dict per turn."""
    return Planner(obs).act()
