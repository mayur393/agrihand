# Agrihand — Findings & Verification Log

Ground-truth mechanics, benchmark numbers, and researched limits. Every entry is filled from the installed `kaggle_environments` source or a live run — **no guesses**. Each item below is confirmed by an assert-based micro-test in `eval/micro_tests.py` once the engine is installed (see §3).

## 1. Engine & environment

- [x] `kaggle-environments` version pinned: `1.32.6` (installed 2026-08-09 via `scripts/setup.sh`)
- [x] Local Python: 3.12.13 (`/usr/bin/python3.12`; venv at `.venv`) — host Python 3.14 is ahead of sim deps (see public repo setup notes)

## 2. Timing benchmarks (TICKET-02)

- [x] **Single 720-turn episode wall-clock** (vs `pass`, `random`, `starter`): `1.9 s` vs `starter` (measured 2026-08-12, `.venv/bin/python`, PASS placeholder agent) — logged at setup, drives the smoke-tier budgets below.
- Fast gate (`smoke.py --fast`: 3 ep × 3 opponents @ 200 steps): observed `~9 s` total (2026-08-12, 9 episodes, 0 failures)
- Full gate (`smoke.py --full`: 50 ep × 3 opponents @ 720 steps): observed `~5 min` total (2026-08-12, 150 episodes, 0 failures)

## 3. Host per-turn compute limit (TICKET-03)

- [ ] **Timeout search:** checked `kaggle_environments` source (`agents.py`/runner) + Kaggle agent-competition docs for a per-step/per-action timeout.
  - Result: `___` (exact value) **or** "no explicit timeout found; verified via <source searched>".
- [ ] **Worst-case BFS turn benchmark:** max hands, fully unlocked 10×10 board, all units pathing: `___ ms` (target < ~100 ms).
- [ ] Mitigations if close to a limit: `BFS_MAX_STEPS` radius cap (default 16), shed-path caching, task-queue truncation. See PLAN.md §3.5.

## 4. Mechanic verifications (assert-based tests in `eval/micro_tests.py`)

**Hard gate (TICKET-10):** `eval/check_findings.py` — invoked from **both** smoke tiers (`smoke.py --fast` and `--full`) before any episodes run — scans `main.py`/`config.py` for the keywords below and **fails loudly** (mechanic ID + open question) if a match is found on a row whose Answer is still `___`. **This is enforced, not just stated.**

⚠️ **Heuristic caveat (TICKET-10):** keyword matching is a heuristic — it can false-positive (a keyword appears but the mechanic isn't actually relied on) and false-negative (a mechanic is relied on through a name not listed in the keyword column). A pass means "no known-unresolved dependency", not "provably safe". Keep the keyword column honest as mechanics and code evolve.

| # | Mechanic | Question | Keyword(s) in main.py/config.py | Answer (from env source) | Test |
|---|---|---|---|---|---|
| M1 | FEED wheat source | Does FEED consume from shed or carried inventory? | `FEED` | `___` | `test_feed_source()` |
| M2 | HARVEST → SELL flow | Harvest goes to inventory; DROP to shed required before SELL (SELL reads shed)? | `HARVEST, DROP, SELL` | `___` | `test_harvest_drop_sell()` |
| M3 | BUY_ANIMAL | Animal lands in shed? | `BUY_ANIMAL` | `___` | `test_buy_animal()` |
| M4 | PLANT simultaneous consumption | All-or-nothing seed consumption when multiple units plant same turn? | `PLANT` | `___` | `test_plant_consumption()` |
| M5 | Decay/weed timing | Exact turn plant becomes WEED (2 consecutive unwatered; seed day counts as first) | `consecutive_unwatered` | `___` | `test_weed_timing()` |
| M6 | End-of-day auto-drop | Unit inventory auto-drops to shed at day end; overflow discarded? | `inventories` | `___` | `test_end_of_day_drop()` |
| M7 | **Mid-day carried-inventory cap (TICKET-07)** | Is there a cap on farmer/hand carried items *before* end-of-day auto-drop? Spec: "stockpiling on farmer/hand inventories does not bypass the cap" → cap expected. | `PICKUP` | `___` (or "no cap") | `test_midday_inventory_cap()` |
| M8 | First-hire spawn | First hand of the day spawns at (5,4) (locked NE quadrant)? | `HIRE` | `___` | `test_hire_spawn()` |
| M9a | Price function — below target (TICKET-11) | `price(inv) = base + amp·f(|inv−I0|)` reproduces P(I0−T) for every resource | `prices` | `___` | `test_price_function_below(resource)` — parametrized over all 9 resources |
| M9b | Price function — above target (TICKET-11) | `price(inv) = base − amp·f(|inv−I0|)` reproduces P(I0+T) and P(I0+2T) for every resource | `prices` | `___` | `test_price_function_above(resource)` — parametrized over all 9 resources |
| M10 | Sell at $1 floor | At floor, unit sold but not added to market inventory (floor stays responsive)? | `SELL` | `___` | `test_price_floor()` |

Add a row per new mechanic learned during development. **Policy must not rely on a mechanic whose row above is still blank — enforced by `eval/check_findings.py` (TICKET-10).**

### Price-function sub-status (M9a/M9b — TICKET-11)

Per-resource/per-side progress, so it isn't one opaque checkbox. Expected values are from the rules-doc price table. Rows must flip to ✅ against the installed engine **before any policy relies on price-curve behavior** (e.g., the §3.4 floor-price rules and the Quadrant-4 writeup in `docs/strategy.md`).

| Resource | M9a below — P(I0−T) | M9b above — P(I0+T) | M9b above — P(I0+2T) | Status |
|---|---|---|---|---|
| WHEAT | 45 | 20 | 19 | ⬜ |
| CARROT | 42 | 10 | 1 | ⬜ |
| TOMATO | 84 | 24 | 9 | ⬜ |
| STRAWBERRY | 204 | 1 | 1 | ⬜ |
| MELON | 300 | 1 | 1 | ⬜ |
| EGG | 70 | 40 | 39 | ⬜ |
| MILK | 256 | 1 | 1 | ⬜ |
| WOOL | 240 | 1 | 1 | ⬜ |
| FERTILIZER | 140 | 60 | 20 | ⬜ |

## 5. Promotion rule — CI worked example (TICKET-01)

Logged from real `eval/tournament.py` runs (2026-08-12, PASS-placeholder candidate, 40 paired games, seed 1, 720 steps):

| Opponent | W/L/T | Win rate | Wilson 95% CI | Decision |
|---|---|---|---|---|
| `random` | 80/0/0 | 1.000 | [0.954, 1.000] | PROMOTE (LB > 0.50) |
| `starter` | 0/80/0 | 0.000 | [0.000, 0.046] | REJECT (UB < 0.50) |

The runner discriminates correctly: the same weak placeholder is promoted vs `random` and rejected vs `starter` — exactly the two CI extremes (LB > 0.50 and UB < 0.50) the promotion rule keys on. Reruns with identical `--seed` reproduce W/L/T exactly (verified twice).

Caveat (verified 2026-08-12): the built-in `random` agent is *not* a weak baseline in the usual sense — it buys seeds/animals it can't use and ends with less banked coins than a PASS agent that just sits at $3,000, so PASS beats it 80/0. Treat `random` as a smoke target only; `starter` (deterministic carrot loop) is the real v1 gate. Also, `random` uses an unseeded per-step `random.Random()`, so it injects its own entropy on top of the seeded engine — `pass` and `starter` are fully seed-reproducible; `random` is reproducible only modulo its internal rolls.

Sequential-rule worked examples (planned for the tuning window): 22/40 → 55% LB≈0.40 not promotable; 30/40 → 75% LB≈0.60 promotable; 60/100 → 60% LB≈0.50 borderline. Target: a plot/table in `reports/` showing LB rising toward LB>0.50 as n grows.

## 6. Discrepancy policy — engine vs. rules doc (TICKET-14)

**When live engine behavior contradicts the public rules doc, engine behavior is authoritative.** Rationale: the ladder runs the engine; the rules doc is prose that can lag or simplify (e.g., if M1 finds FEED pulls from carried inventory rather than shed, the code must follow the engine).

Procedure:
1. Log the discrepancy as a note directly on the relevant §4 row (e.g. `M1: engine consumes from carried inventory, rules doc says shed — engine authoritative, policy adapted`), never silently.
2. The §4 answer column + `main.py`/`config.py` reflect engine behavior; the note preserves the rules-doc discrepancy for future reference.
3. If a discrepancy changes a policy assumption (e.g., M2's DROP-before-SELL flow), record the impact in `docs/plan.md`'s experiment log with the date.

Retroactive application: at the time of writing, no rows in §4 are answered yet (all `___`), so no discrepancies are known — when each row is filled, this policy applies from the moment of filling.

## 7. Open questions → resolve in env source before relying on them

- (grows as development proceeds; each becomes a row in §4 once answered)
