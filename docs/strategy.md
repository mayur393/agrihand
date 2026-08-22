# Agrihand — Strategy Decisions & Rationale

This file records *why* each policy choice exists. Numbers referenced here are the defaults in `config.py` — change tunables there, keep the reasoning here (TICKET-06).

## Win/loss-first principle cross-check (TICKET-08)

Principle (from PLAN.md §1): *Prioritize reliably beating whoever we're matched against over maximizing absolute coin margin — a defensive agent that wins by $1 outranks a volatile one that sometimes wins big and sometimes collapses.*

Existing rules checked against it:

| Rule | Aligns with win/loss-first? | Note |
|---|---|---|
| Wheat buffer ≥ animals×2+5 | ✅ Yes | Defensive posture — prevents animal escape, a catastrophic loss of both assets and income. |
| Never sell below per-crop floor price | ✅ Yes | Avoids dumping into gluts, which crashes price and hurts us in future turns. |
| Premium goods sold in small batches into demand ticks | ✅ Yes | Protects future sale prices (anti-volatility). |
| Land expansion with cash reserve buffer | ✅ Yes | Avoids cash-starvation mid-season (bankruptcy = certain loss). |
| Mean margin in tournament output | ⚠️ Diagnostic only | Tracked for trend insight, **never** a promotion criterion. Promotion is win-rate CI only (TICKET-01). |
| Opponent-aware sell timing (stretch) | ⚠️ Conditional | Expected win-rate effect may be positive (sell before the opponent's glut lands), **but this is higher-variance than the rest of the ruleset**: it front-runs a predicted opponent action from a noisy signal (visible `yield_units` shows what's *harvestable*, not when the opponent will actually *sell*), which the win/loss-first principle explicitly deprioritizes over low-variance reliable wins. This tension is weighed deliberately, not assumed aligned — the feature stays flag-OFF by default and needs CI-gated evidence before promotion (TICKET-05). |

Other rows re-checked (TICKET-12): the remaining ✅ rows (wheat buffer, floor-price, premium batches, land reserve) are all defensive/low-variance and directly reduce loss probability — they genuinely align and need no ⚠️ treatment. Mean margin is already marked ⚠️ Diagnostic.

Rule of thumb for future tuning: if a proposed change increases expected *margin* but not expected *win rate* (or increases variance), it fails the principle and needs explicit justification.

## Quadrant #4 policy — ROI reasoning (TICKET-04)

**Default Q4 crop is melon — a committed decision (TICKET-16).** Rationale below. Config knobs: `QUADRANT4_LATEST_DAY` (16), `QUADRANT4_CASH_THRESHOLD` (6000), `QUADRANT4_RESERVE` (1000), `QUADRANT4_CROP` (`"MELON"`); setting `QUADRANT4_CASH_THRESHOLD = None` hard-disables Q4 (the fallback if the melon gamble is ever deemed not worth it).

Decision: buy quadrant #4 ($4k) **only if** `day <= 16` AND `money >= 6000` AND post-purchase reserve `>= 1000`, and plant it with melon.

**Land order is pinned (verified from the competition page):** quadrants are bought in fixed order — **NE ($1k) → SW ($2k) → SE ($4k)** — so quadrant #4 is always the **SE** quadrant, and by the time Q4 is on the table (day ≤ 16) NE and SW are already owned. Tactical implication worth exploiting: the first hired hand of each day spawns at **(5,4), which sits in the NE quadrant** — buying NE first ($1k, the cheapest) means that spawn lands on owned, unlocked land from day one instead of on a locked tile, so "buy Q2 early" is specifically "buy NE early."

Revenue model — units carried through explicitly (units/tile/day × $/unit × days × tiles):
- Buying at day 16 leaves ~14 days of use.
- **Melon (committed Q4 crop):** 0.55 units/tile/day × $250 ≈ **$137/tile/day** at base → ×14 days ≈ ~$1,900/tile → ×25 tiles ≈ **~$48,000 gross at base**. Realized price is far lower and path-dependent — a 25-tile glut (~150 units on the market) hits `sq 3.60` above-target and **crashes to the $1 floor** (P(I0+T)=P(I0+2T)=$1). Melon barely reacts to scarcity (`log 0.20` below → P(I0−T)=$300), so upside is capped by how *we* manage the glut, not by town demand.
- **Wheat (staples — the fallback if melon is discarded):** 0.80 units/tile/day × $25 ≈ **$20/tile/day** → ×14 days ≈ $280/tile → ×25 tiles ≈ **~$7,000 gross**. Wheat absorbs gluts (above-side `log 0.2`; P(I0+2T)=$19, only ~24% under base), so realized price stays near base — revenue *plausibly clears the $4k cost* even for staples. (TICKET-09 correction: an earlier draft treated "yield/tile/day" as a dollar figure and concluded revenue couldn't cover cost — off by ~an order of magnitude.)

So the case for caution does **not** rest on a revenue shortfall. It rests on:
- **(a) Price-crash risk:** the committed melon wave (25 tiles ≈ 150 units) depresses the price of every melon we sell *across the whole farm* (market inventory is shared), not just Q4's output — exactly the volatility the win/loss-first principle forbids. Melon's realized value is dominated by **sale timing into the first-turn-after-demand-tick window** (§3.4), not by gross yield.
- **(b) Labor:** 25 tiles of daily watering ≈ 25 actions/day ≈ 1–2 hands beyond the main farmer. Daily hire cost is fibonacci: 1st hand $1, 2nd hand $1, 3rd hand $2 — **cheap per day**, but hands must be re-hired and re-paid daily, and the opportunity cost is farmer/hand actions diverted from harvest/liquidation near season end. Miss 2 water days and the tile weeds — wasting seed + labor.
- **(c) Crop-mix timing:** melon planted by day 16 harvests one window (first yield day 10 → ~day 26), leaving no second chance if timing is misjudged; wheat/carrot would get 3–4 cycles.

**Working-capital derivation of $6,000 (TICKET-16):** Q4 needs land ($4,000) + seeds. Melon seed costs $80 → 25 tiles = **$2,000** in seeds. $6,000 − $4,000 − $2,000 = $0 — but the `QUADRANT4_RESERVE` check uses *pre-seed-purchase* money, since seeds are bought in subsequent market turns (the market order for seeds comes after the BUY_LAND order), so the buy is jointly fundable. Because the crop is **committed to melon**, the seed component is not arbitrary — it's the actual seed bill for the default Q4 plan. (Wheat seeds at $10 → $250 for the fallback mix would make $6,000 *over*-funded — the threshold is sized for the melon default.)

**Decision rule:** the buy is a melon gamble, made only when the conditions hold. If the melon gamble is discarded (price floor reached pre-plant, or the window missed), fall back to wheat/carrot on Q4 (cheap seeds, glut-absorbing) or skip the purchase — never plant melon into a glutted market.

Hands-cost note (TICKET-16 — corrected): the earlier writeup's "sweeping 7000 additionally funds ~2 hands' daily cost" misread the fibonacci schedule — 2 hands cost **$2 total** that day (1,1,2,...), not ~$1k — and is dropped. Labor cost is real but per-day-cheap; the real cost is *opportunity* (actions diverted from harvest/liquidation).

--- SUPERSEDED 2026-08-16 (RM-021) ---
The $6,000 threshold above assumed NE/SW already owned. The engine's land order is pinned NE→SW→SE with no skip, and the committed baseline owns nothing — the honest gate is the full chain: $1k+$2k+$4k+$2k melon seeds = $9,000. `QUADRANT4_CASH_THRESHOLD` is now **9000** in config.py (with `QUADRANT4_LATEST_DAY=16`, `QUADRANT4_RESERVE=1000`). Measured day-16 cash under the committed baseline (~$4.0–4.4k, 6 seeds) never reaches this, so the gate is dormant-but-correct rather than dead: it activates automatically if a future income change (e.g. RM-036's combo test) pushes cash past $9k. The original TICKET-16 reasoning above is kept as-is as the record of how the mistake happened.

## Opponent-aware sell timing — noise caveat (TICKET-05)

Scoped: Aug 25–Sep 10 only, per the PLAN.md §6 timeline row *"Aug 25 – Sep 10 | Cows/sheep + care/fertilizer. **Stretch window: opponent-aware premium sale timing (TICKET-05)...**"* — this feature must not be built or CI-tested before that phase gate. Flag: `OPPONENT_AWARE_SELL_TIMING`, default `False`.

Caveat documented for future tuning: **visible `yield_units` shows what is harvestable, not when the opponent will harvest or sell.** An opponent may harvest late, hold in the shed, or sell in dribbles — the visible signal overstates their imminent market impact. Validating this feature means:
1. Tournament with flag ON vs flag OFF vs the same opponents (CI rule, TICKET-01).
2. Only promote if ON beats OFF with LB > 0.50 — a marginal or ambiguous result keeps it OFF.
3. If it misbehaves on the ladder, flip the flag off in config and re-submit; core logic is untouched.

## config.py purpose (TICKET-06)

`config.py` is the single source of truth for all tunable strategy thresholds, imported by both `main.py` and `eval/tournament.py`. Every constant carries a comment linking back to the PLAN.md section that justifies it. Parameter sweeps edit one file — no literals buried in decision logic. Ships in the submission bundle (stdlib-only, so no import concerns on the host).

## Inventory reality — M7 correction (verified 2026-08-12)

**There is no mid-day cap on carried inventory** (engine `_apply_unit_action`: PICKUP/DROP/HARVEST impose no per-unit limit). The only constraint is **shed capacity (host `shedCapacity` = 100)**, enforced at DROP / PLACE-deposit / end-of-day auto-drop — and end-of-day auto-drop **discards overflow** (`_drop_inventories_to_shed`: moves up to capacity, discards the rest). Consequences for policy:

- **The constraint moved from "mid-day per-unit cap" (TICKET-07's premise, overturned) to "end-of-day shed capacity + overflow discard" — and it's sharper.** A unit harvesting > (shed room) items into its carry in one day will silently lose the excess at day end.
- **RM-012 / RM-018 must not over-harvest right before a day boundary.** Harvest quantity should be capped by *current shed room*, not just by carried capacity — e.g. harvest-then-drop cycles keep the shed draining, or harvest only as much as the shed can absorb before the end-of-day drop. This is a real loss mechanism, not a theoretical one.
- **RM-014 (task assignment)**: a unit assigned to FEED must carry wheat *before* walking to the animal (M1 — FEED reads carried inventory only). "Carry wheat" is part of the FEED task itself, not an engine-provided precondition. Same for HARVEST→DROP: a harvester with a full carry must cycle back to the shed.
- **M8 (spawn precision)**: first-hand spawn is the first FREE shed-access tile in NWSE order — (4,4) NW → (5,4) NE → (4,5) SW → (5,5) SE — so (5,4) only when free. The NE-early rationale survives (buying NE unlocks the tile the hand would otherwise land on locked), but "spawns at (5,4)" is a simplification: a hand standing there (or the farmer) pushes the spawn to the next free tile. NE-first expansion still holds as a strategy.
