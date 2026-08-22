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
- [x] **Worst-case BFS turn benchmark:** single-farmer worst-ish case (20 scattered unwatered plants, farmer at corner, BFS_MAX_STEPS=16): `0.088 ms`/call (measured 2026-08-13, n=2000) — far under the <100 ms budget. Multi-hand worst case (RM-016) re-benchmarked then.
- [ ] Mitigations if close to a limit: `BFS_MAX_STEPS` radius cap (default 16), shed-path caching, task-queue truncation. See PLAN.md §3.5.

## 4. Mechanic verifications (assert-based tests in `eval/micro_tests.py`)

**Hard gate (TICKET-10):** `eval/check_findings.py` — invoked from **both** smoke tiers (`smoke.py --fast` and `--full`) before any episodes run — scans `main.py`/`config.py` for the keywords below and **fails loudly** (mechanic ID + open question) if a match is found on a row whose Answer is still `___`. **This is enforced, not just stated.**

⚠️ **Heuristic caveat (TICKET-10):** keyword matching is a heuristic — it can false-positive (a keyword appears but the mechanic isn't actually relied on) and false-negative (a mechanic is relied on through a name not listed in the keyword column). A pass means "no known-unresolved dependency", not "provably safe". Keep the keyword column honest as mechanics and code evolve.

| # | Mechanic | Question | Keyword(s) in main.py/config.py | Answer (from env source) | Test |
|---|---|---|---|---|---|
| M1 | FEED wheat source | Does FEED consume from shed or carried inventory? | `FEED` | Carried inventory only (`_inv_take(inv, "WHEAT", 1)`); shed NOT consulted. **Rules-doc says shed — engine authoritative.** | `test_feed_source()` |
| M2 | HARVEST → SELL flow | Harvest goes to inventory; DROP to shed required before SELL (SELL reads shed)? | `HARVEST, DROP, SELL` | Yes. HARVEST adds to unit carried inventory; DROP (shed-adjacent only) deposits to shed; SELL reads `private["shed"]`. | `test_harvest_drop_sell()` |
| M3 | BUY_ANIMAL | Animal lands in shed? | `BUY_ANIMAL` | Yes — lands in `private["shed"]` (obeys shedCapacity); PLACE takes from carried inventory onto a matching structure. | `test_buy_animal()` |
| M4 | PLANT simultaneous consumption | All-or-nothing seed consumption when multiple units plant same turn? | `PLANT` | Yes — per-crop atomic gate: if total PLANT requests for a crop exceed available seeds, ALL are dropped (→ PASS), none partially consumed. | `test_plant_consumption()` |
| M5 | Decay/weed timing | Exact turn plant becomes WEED (2 consecutive unwatered; seed day counts as first) | `consecutive_unwatered` | Planting day counts as unwatered (init `consecutive_unwatered: 1`); each unwatered daily refresh increments; `>= 2` → WEED. Watering resets to 0. | `test_weed_timing()` |
| M6 | End-of-day auto-drop | Unit inventory auto-drops to shed at day end; overflow discarded? | `inventories` | Yes — `_drop_inventories_to_shed` moves ALL carried items to shed up to `shedCapacity` (default 100); overflow discarded. Seeds never in shed. | `test_end_of_day_drop()` |
| M7 | **Mid-day carried-inventory cap (TICKET-07)** | Is there a cap on farmer/hand carried items *before* end-of-day auto-drop? Spec: "stockpiling on farmer/hand inventories does not bypass the cap" → cap expected. | `PICKUP` | **No cap.** Units can carry unlimited items mid-day; the only inventory limit is shed capacity (100), enforced at DROP/PLACE-deposit/end-of-day. **Rules-doc assumption wrong — stockpiling on units DOES bypass any cap until day end.** | `test_midday_inventory_cap()` |
| M8 | First-hire spawn | First hand of the day spawns at (5,4) (locked NE quadrant)? | `HIRE` | Mostly — first hand spawns at first FREE shed-access tile in NWSE order: (4,4) NW → (5,4) NE → (4,5) SW → (5,5) SE, ties by min occupancy. Farmer occupies (4,4) at spawn, so first hand lands (5,4) — but only if free; a hand standing there pushes spawn to (4,5) etc. **Plan's "(5,4) always" is a simplification.** | `test_hire_spawn()` |
| M9a | Price function — below target (TICKET-11) | `price(inv) = base + amp·f(|inv−I0|)` reproduces P(I0−T) for every resource | `prices` | `market_price()` implements exactly the rules-doc formula; below-target values match the documented P(I0−T) table (all 9 resources). | `test_price_function_below(resource)` — parametrized over all 9 resources |
| M9b | Price function — above target (TICKET-11) | `price(inv) = base − amp·f(|inv−I0|)` reproduces P(I0+T) and P(I0+2T) for every resource | `prices` | `market_price()` above-target matches the documented P(I0+T)/P(I0+2T) table (all 9 resources). | `test_price_function_above(resource)` — parametrized over all 9 resources |
| M10 | Sell at $1 floor | At floor, unit sold but not added to market inventory (floor stays responsive)? | `SELL` | Yes — `_commit_unit`: SELL at price > 1 adds 1 to market inventory; **at price == 1 (`PRICE_FLOOR`), sold unit does NOT add to market inventory** (prevents self-glut floor trap). | `test_price_floor()` |

Add a row per new mechanic learned during development. **Policy must not rely on a mechanic whose row above is still blank — enforced by `eval/check_findings.py` (TICKET-10).**

### Price-function sub-status (M9a/M9b — TICKET-11)

Per-resource/per-side progress, so it isn't one opaque checkbox. Expected values are from the rules-doc price table. Rows must flip to ✅ against the installed engine **before any policy relies on price-curve behavior** (e.g., the §3.4 floor-price rules and the Quadrant-4 writeup in `docs/strategy.md`).

| Resource | M9a below — P(I0−T) | M9b above — P(I0+T) | M9b above — P(I0+2T) | Status |
|---|---|---|---|---|
| WHEAT | 45 | 20 | 19 | ✅ |
| CARROT | 42 | 10 | 1 | ✅ |
| TOMATO | 84 | 24 | 9 | ✅ |
| STRAWBERRY | 204 | 1 | 1 | ✅ |
| MELON | 300 | 1 | 1 | ✅ |
| EGG | 70 | 40 | 39 | ✅ |
| MILK | 256 | 1 | 1 | ✅ |
| WOOL | 240 | 1 | 1 | ✅ |
| FERTILIZER | 140 | 60 | 20 | ✅ |

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

Retroactive application: rows in §4 are now answered (2026-08-12, RM-009). Discrepancies logged per procedure step 1 directly on the rows:
- **M1**: rules doc says FEED pulls from shed; engine consumes from carried inventory. **Engine authoritative — policy adapted.**
- **M7**: rules-doc assumption "stockpiling on farmer/hand inventories does not bypass the cap" is **wrong** — units carry unlimited items mid-day; only shed capacity (100) binds. TICKET-07's premise overturned; recorded in docs/plan.md.
- **M8**: plan's "(5,4) always" is a simplification — first hand spawns at first FREE shed-access tile in NWSE order. Not a contradiction, but a precision fix.

## 7. Real-match observations (replays / ladder data — soft priors, not distributions)

Single-match snapshots from actual leaderboard play. **One match is a prior, not a distribution** — do not override a tournament A/B with a single replay. Use to sanity-check strategy direction, never to decide promotions.

### 2026-08-13 — top-bracket replay (winner カワシギ 3198 vs Filip Strzałka 3157)

- Winner ~115,872 coins vs loser ~109,988 — both ~$110k, a full season's economy. v1's ~$4.7k is the floor, not a comparison.
- **Margin was tiny relative to wealth** (~$5.9k on ~$110k, ~5%) — consistent with win/loss-first: at high skill the winner just needs to exist, not dominate. Low-variance defensive play is correct.
- **Both farms animal-saturated** (dozens of sheep/cows/geese visible, few crops). Loser looked more animal-dense than winner → raw animal count isn't the differentiator; execution/timing (feed/care/harvest rhythm) likely is.
- **Both bought all 3 quadrants** — full board coverage by day 30 is standard among top bots. This is a soft prior *for* land expansion at scale — but it does NOT contradict RM-015's A/B (land-ON loses for a SINGLE farmer with no labor to work extra tiles). Reconciliation: land pays off only when the farm has the units to work it (RM-016 hands + RM-019 animals). Re-test land ON-vs-OFF at RM-016.
- **Weeds visible even at top tier** — no bot achieves zero weeds; DIG stays a real task.
- Per-tile numbered badges = UI sugar over the same tile data we read from obs (yield/fertilizer counts) — no new mechanics.

### 2026-08-16 — RM-036: causal evidence (our bot) vs leaderboard correlation

**Motivation was correlational leaderboard data with a known skill confound** (good bots do many things well; r(animals, bank)=0.468 does not prove animals cause bank). This ticket tested causation on our own bot: one combined candidate (goose + MELON/STRAWBERRY/WHEAT spread + day-0 hiring) vs the committed baseline in seeded self-play.

**Result — causal evidence from our own bot:** combined candidate wins **80/0** (40 paired games, CI [0.954, 1.000]) against the animals-ON wheat/carrot/no-hands baseline, with **zero animal escapes** across all 80 episodes. The combination creates value none of the individual levers showed alone (RM-014–018 all tested one variable at a time and came back negative/neutral). The mechanism: premium crops fund the farm, early labor covers the bigger task surface, the goose adds eggs/fertilizer, and the wheat feed reserve holds under the RM-036 production-side guards.

**Why individual tests missed it:** the wheat monoculture bug (CROP_SPREAD was OFF; any mix planted only the first crop with seeds) silently invalidated RM-017's mix A/Bs. RM-016 tested hands on a wheat/carrot farm where one farmer already cleared all tasks — the labor was redundant. The pieces only pay off together.

**New mechanic facts confirmed during RM-036 (engine-verified):**
- End-of-day auto-drop fills the shed in inventory order and discards overflow (M7) — a shed flooded with premium goods silently deletes carried wheat, which is how the animal starves even when the sell-side buffer is intact.
- At the $1 price floor, SELL clears shed space without adding to market inventory (M10) — safe rescue-sell for premium goods.
- `hires_today` resets to 0 at day end; hands must be re-hired daily. The market-order cap (10/turn) used to truncate HIRE out of the queue — HIRE now goes first.

### 2026-08-16 — RM-035: the `first_hire_day ≈ 0` pattern is REAL, not an extraction bug

Investigated after the 296-episode leaderboard summary showed `first_hire_day = 0` for 583/592 seats (98.5%). Verified against the raw replays:
- Fresh 50-episode (100-seat) random sample from the full 34,581-episode parquet reproduces 98% day-0 independently.
- Action-stream cross-check (60 episodes / 120 seats): extraction's `hires_today > 0` first-day **agrees with explicit HIRE orders on the same day in 100% of cases** (0 mismatches).
- `hires_today` is post-hire count, read directly from `farms[seat]["hires_today"]` each step — the extraction logic is correct.
- Top-bracket seats genuinely hire on day 0 (e.g. seat 0 of ep 90095306 hires at step 1, `hires_today=6` by day 0's end).

Conclusion: `first_hire_day = 0` for 98% of seats is a **real leaderboard behavior** (immediate labor scaling), not a column to distrust. The `None` rows (6/592) are no-hire seats. RM-036's analysis may use `first_hire_day` as-is — but with the corrected reading: it is not a bug artifact.

### 2026-08-16 — RM-037: RM-017 RETRACTED (invalid evidence) + RM-016 HIRE-truncation audit CONFIRMED CLEAN

**RM-017 is formally RETRACTED — the original negative result was invalid evidence, not a real finding.** The crop_mix parameter was non-functional due to the wheat-monoculture bug (fixed at RM-036 via CROP_SPREAD): the PLANT branch always picked the first crop in the mix that had seeds, so every "diversified" variant silently planted ~100% WHEAT — the +tomato and +melon A/Bs never actually planted tomato or melon. The premise of the experiment was false, so "RM-017 showed premium crops don't help" must **not** be cited as settled fact. The corrected, valid test is RM-036: MELON/STRAWBERRY/WHEAT combo beats the animals-on baseline 80/0, CI [0.954, 1.000]. Full record: docs/plan.md RM-037 row.

**RM-016 audit for the sibling bug class (HIRE-truncation) — CONFIRMED CLEAN.** RM-036's bug list named the market-order cap (10/turn) dropping HIRE from full queues; RM-016's "hands neutral" result lives in the same code family, so it was audited rather than assumed fine:
- **Structural max market orders/turn at RM-016's commit (02afc31) = 6** (2 seed buys + 2 shed sells (WHEAT/CARROT only — no animals, no BUY_PRODUCT) + 1 land + 1 hire), under the engine's `maxMarketOrdersPerTurn=10` cap.
- **Empirical replay** of the hands-ON arms (RM-016-era code from git, seeds 1–8 & 37–48, 80 episodes / 57,520 agent-turns vs starter, engine 1.32.6): max pre-truncation orders per turn = **3**, zero turns at the cap, HIRE requested 2,913 times with **zero** truncations.
- **Fidelity check:** the replay reproduces the original 2×2 pattern (land-ON 0/40/0, land-OFF 40/0/0), so the hands-ON arms genuinely had hired hands at work — "hands neutral" reflects real labor, not silently-unhired hands.
- **Triggerability timeline:** the `orders[:10]` truncation (HIRE last) existed from RM-016 but was inert through RM-021 (max 6–9 orders); it first became reachable in the RM-036-era combo config (~12–13 orders/turn with premium crops + fertilizer + animal products in the shed), where RM-036 observed it biting and fixed it by moving HIRE first.

### 2026-08-17 — RM-038: RM-036 margin-vs-robustness check — ACCEPTED AS-IS

**Paper-trail correction check:** `docs/findings.md` and `docs/plan.md` contain no `RM-816`, `RM-817`, “18 cap”, or “8 truncations” text. The canonical identifiers are RM-016/RM-017 and the engine cap is 10.

**Original-run data limitation, handled explicitly:** RM-036 retained its aggregate 80/0 result but not the per-seed money stream. The table below is therefore a deterministic reconstruction, not a falsely-labelled recovered artifact: current `agents/rm036_combo.py` versus frozen `agents/v3_animals_on_baseline.py`, engine 1.32.6, full 720-turn paired games, seeds 1–40 and both seats. It reproduces the recorded 80/0 result exactly.

| Seed | Mean paired margin | Seed | Mean paired margin | Seed | Mean paired margin | Seed | Mean paired margin |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | +4,998.0 | 11 | +5,498.5 | 21 | +5,037.5 | 31 | +4,144.0 |
| 2 | +4,201.0 | 12 | +4,327.5 | 22 | +4,479.0 | 32 | +5,671.0 |
| 3 | +5,029.5 | 13 | +3,599.5 | 23 | +5,077.0 | 33 | +5,082.5 |
| 4 | +4,013.5 | 14 | +5,291.0 | 24 | +4,988.5 | 34 | +6,137.0 |
| 5 | +5,042.0 | 15 | +4,716.0 | 25 | +4,915.0 | 35 | +4,801.5 |
| 6 | +5,280.0 | 16 | +5,351.5 | 26 | +5,213.0 | 36 | +4,698.5 |
| 7 | +3,879.5 | 17 | +5,220.0 | 27 | +5,398.0 | 37 | +3,558.0 |
| 8 | +5,812.5 | 18 | +5,570.5 | 28 | +6,629.0 | 38 | +5,319.5 |
| 9 | +3,975.5 | 19 | +4,944.0 | 29 | +3,891.5 | 39 | +5,286.0 |
| 10 | +3,977.0 | 20 | +5,192.5 | 30 | +4,009.5 | 40 | +5,570.5 |

There is **no margin regression against the RM-036 comparator** in any reconstructed seed: all 80 slot-swapped episodes win. Paired mean margins range from +$3,558.0 (seed 37) to +$6,629.0 (seed 28), mean +$4,895.7; the closest individual episode is seed 29 / seat 0 at +$2,826.

**Why the close cases are still safe:** action/price traces of the two closest original cases (seed 7 / seat 0, +$2,897; seed 29 / seat 0, +$2,826) show 60 HIRE orders in each, so fixed hiring/animal overhead does not explain the cross-seed variation. Their MELON prices were $260 and STRAWBERRY prices stayed $159–$226 — nowhere near the $1 glut floor. The observable difference is output volume: seed 29’s close seat sold 10 melons and 12 strawberries, while high-margin seed 43 / seat 0 sold 25 melons and 17 strawberries. This supports ordinary production/turn-path variance, not the proposed premium-price-collapse mechanism. It is not evidence to change sell timing.

**Wider robustness sweep:** seeds 1–62, 62 paired / 124 slot-swapped full episodes, yielded **124/0/0**, win rate 1.000, Wilson 95% CI **[0.970, 1.000]**. The closest episode in the wider sweep was seed 57 / seat 1 at +$2,575; there were no ties, losses, or near-zero outcomes.

**Decision — ACCEPTED AS-IS; no follow-up tuning ticket.** Per `docs/strategy.md`’s win/loss-first rule, a stable 124/124 win record with a 0.970 Wilson lower bound outweighs variation in a diagnostic margin. The observed low cases do not show a premium glut, a feed failure, an escape, or a fixed-cost failure mode that a narrowly-scoped sell-timing change could safely fix. A premium-timing ticket would add variance without evidence of a win-rate defect, so RM-038 closes with no `main.py` or `config.py` change.

## 7b. RM-040 — rating-controlled predictors of final_bank (leaderboard distributions)

**Correlational, from leaderboard data — requires a self-play A/B before trusting.** Same caveat as the animal-count finding: this separates skill confound but does not prove causation. Analysis script: `analysis/rating_controlled_regression.py` (dev-only, NOT in the submission). Data: `episode_features.csv` + `episodes.csv` + `teams.csv` (34,139 public episodes / 68,278 seats). Report: `reports/rm040_regression.md`.

**Method (confound control, the whole point):** a raw winner-vs-loser mean is contaminated — good bots do *more of everything*, so "winners plant more X" can be a side effect of skill. Three controls applied:
- Model B: OLS controlling for **post-game `rating`** (endogenous — the outcome updates rating, so it under-credits levers).
- **Model C (cleanest):** OLS controlling for **`ladder_score`** — a team snapshot *not* tied to this episode, so it isolates within-skill variation.
- Model D: paired within-episode deltas — controls the environment but **not** the within-pair skill gap (the winner is systematically higher-skill, so every delta trends positive). Read as a robustness view of the confound, not clean evidence.

**Result — the wheat story flips under control (the raw mean was confounded):**

| Predictor | Model A (raw) | Model C (ladder_score) | Per-unit (Model C) |
|---|---|---|---|
| `plants_wheat` | −3,536 | **−4,205** | −$78/wheat |
| `plants_strawberry` | +6,171 | **+5,761** | **+$144/strawberry** |
| `plants_melon` | −1,656 | −1,413 | −$106/melon |
| `total_hires` | +12,002 | +12,715 | +$262/hire |
| `peak_crew` | +1,078 | −122 | (noise) |
| `ladder_score` (control) | — | +3,008 | — |

The earlier naive split ("winners plant more wheat") was **confounded** — within rating quartiles, the winner's wheat advantage is tiny (+7–15 tiles, and *shrinks* at the top band Q4 +7.3), and wheat's sign is *negative* once skill is held fixed. Real signal that survives the clean control:

1. **Strawberry volume is the strongest *positive* lever (+$144/unit, ~+$5.8k/SD), robust across all models.** Q1→Q4 bank quartiles plant 28→40 strawberries. This is *not* a raw mean artifact — the coefficient grows in the clean control.
2. **`total_hires` is the largest effect (+$262/hire, ~+$12.7k/SD)** but is confounded with `peak_crew` (r=0.80) and is a *proxy for scale*, not a lever we can blindly raise — our agent's `MAX_HANDS_PER_DAY=2` is a deliberate choice, and RM-016 already found hands neutral at v1 scope. Flag, don't act yet.
3. **Wheat volume is a *negative* lever (−$78/unit) once skill is fixed.** Wheat is the feed buffer + staple, not a money crop — over-planting it crowds out strawberry. The `WHEAT_MIN_TILES` floor already treats wheat as a *reserve*, which this data supports.

**Concrete, config-tunable hypotheses (feed into RM-041 A/B, do NOT change main.py/config.py here):**
1. **Strawberry mix share up:** the current `V1_CROPS=("WHEAT","MELON","STRAWBERRY")` spreads via `CROP_SPREAD` (tile hash), so strawberry is ~1/3 of plantings. Test a mix weighted toward strawberry (e.g. `("STRAWBERRY","STRAWBERRY","WHEAT","MELON")` or a `CROP_SPREAD` bias) and A/B it vs the committed combo.

**RM-041 RESULT (2026-08-21) — REJECTED: the strawberry hypothesis did NOT survive self-play.** All three weighted mixes lost decisively to the committed mix (strawberry-heavy 4/76, drop-melon 0/80, strawberry-dominant 0/80, CI upper bounds ≤ 0.122). The positive regression coefficient was a **survivor-bias confound**: rich, high-skill bots scale strawberry *after* establishing an economy (strawberry costs $100 seed, first yields day 10), so the ladder_score control left "scale from success" entangled with "strawberry causes success." Correlational leaderboard data is hypothesis-generation only; self-play is the truth gate, and here they disagreed — self-play wins. Committed mix unchanged.
2. **Wheat cap at the reserve, not a third of the field:** `WHEAT_MIN_TILES=6` is already a *floor*; test whether *capping* wheat plantings (e.g. stop planting wheat above some tile count) frees tiles for strawberry without starving the goose.
3. **Land/crew timing:** `first_land_day` has a mild negative effect (−$665/SD ≈ −$144/day later) but `peak_crew` is noise — defer. Land expansion was already decisively rejected (RM-015/016); this data does NOT reopen it.

**Animal-count gap (honest note):** `episode_features.csv` has **no animal-count column** — only the 593-row `summary.csv` sample does. The animal lever cannot enter this 34k regression without a parquet pass; left as a flagged follow-up, not silently dropped.

## 7c. RM-042 — movement profiling + closest-first assignment (PROMOTED)

**Profiler result (dev-only `analysis/turn_tally.py`, NOT shipped):** the committed RM-036 combo spends **68.4% of all unit-turns MOVING** (farmer 61.7%, hands 71.9%) and **0.0% idle (PASS)**. The waste is walking, not idleness — so the correct lever is assignment efficiency, not more hands. This is the measured answer to the strategic question in the RM-042 plan: each hand does its action in parallel with the farmer for no turn cost, so the win is *productive actions per turn*, and the thing to shrink is the movement between actions.

**Fix (lever #1, closest-unit-first):** the committed `agent()` assigned the farmer first, then each hand in order, from a per-turn `claimed_targets` set. The farmer could therefore claim a tile a hand was already standing next to, forcing the hand to walk far for a second choice. `_closest_first_assign()` replaces that greedy order with one global matching: every unit is assigned its nearest *unclaimed* task tile (distance is the hard objective, priority a tiebreak). Implemented flag-gated (`closest_first`, default OFF at dev time) behind `_unit_action(..., assigned_override=...)`, so the committed path was byte-for-byte unchanged when OFF.

**Measured effect:** move share **68.4% → 52.2%**, productive act share **31.6% → 47.7%** vs `starter` (3 episodes). Self-play vs committed `main.py`: seeds 1, 42, 123 → **240/0/0**, CI [0.954, 1.000] each. `eval/smoke.py --animals` 50 episodes **0 escapes**, 0 failures.

**Promotion:** `agent(..., closest_first=True)` is now the committed default. `_bfs_distances()` added (all-reachable BFS matching `_bfs_nearest` reachability). Variant archived `agents/rm042_closest_first.py`. Logged in `docs/plan.md` (RM-042).

**Deferred (plan intact):** persistent intent (lever #2), walk budget (#3), spatial zones (#4), role specialization (#5), and any `MAX_HANDS_PER_DAY` change remain untested until the post-fix Step-0 tally shows movement is still the binding constraint.

## 8. Open questions → resolve in env source before relying on them

- (grows as development proceeds; each becomes a row in §4 once answered)

### 2026-08-21 — RM-042 follow-up: labor ceiling search (MAX_HANDS_PER_DAY 2→4 PROMOTED)

After closest-first cut movement 68.4%→52.2%, the remaining 52% was still movement (idle ~0%), so the next lever tested was **more parallel hands** — a hand costs coins, not turns. Result, measured by a dev-only margin probe (`analysis/margin_probe.py`, not shipped) because win rate saturates above 3 hands:

- **3 vs 2:** 73/80, 80/80, 77/80 across seeds (CI LB ≥ 0.830) — PROMOTE.
- **4 vs 3:** +$4,012 mean paired margin, 0/40 negative — PROMOTE.
- **5 vs 4:** −$103 mean, 36/40 negative — REJECT (the 5th hire, fibonacci $5, exceeds marginal production).
- **6 vs 5:** +$1,438 but non-monotonic (5 already lost to 4) — REJECT as unreliable.

**Committed `MAX_HANDS_PER_DAY=4`** (the last monotonic improvement). This also explains why RM-016's "hands neutral" does not conflict: RM-016 tested hands on a small wheat/carrot field where one farmer already cleared all tasks; with closest-first assignment, extra hands now land on real work. The labor lever only pays once movement is efficient — consistent with the RM-042 strategic frame (productive actions per turn).

**Movement composition snapshot (why levers #2-#5 stay deferred):** move-empty 61.8%, move-loaded 38.2%, direction reversals only 1.05% of moves. Persistent intent (#2) has little left to give; the remaining movement is mostly geometric between-task walking plus shed logistics (#5, not yet pursued).


### 2026-08-21 — RM-043: animal-count lever — NOT a real signal (confounded, closed)

**Backfill:** the animal column missing from `episode_features.csv` was backfilled from `replays.parquet` via `analysis/animal_backfill_parallel.py` (dev-only). A contiguous 1,489-episode slice (2,978 seats) completed before the parallel pass was capped; that is ample for a rating-controlled regression, and the coverage caveat (contiguous, not random) is noted.

**Result (ladder_score-controlled, same treatment as RM-040):**

| predictor | A raw | C ladder_score |
|---|---|---|
| `max_animals` (total) | +$7,402/SD | **+$6,196/SD** |
| `max_geese` | −$3,457 | −$2,811 |
| `max_cows` | −$2,466 | −$1,905 |
| `max_sheep` | −$4,301 | −$3,212 |
| `ladder_score` (control) | — | +$3,858 |

**Interpretation — composition paradox, a skill confound, not a lever.** Total animals correlate strongly with winning, but *every individual animal type is negative* once skill is held fixed. The "winning bots are animal-saturated" observation (findings §7) is therefore survivor bias: winning bots can *afford* many animals; the animals do not *cause* the winning. This is the same confound class that rejected the strawberry mix in RM-041, and the correct move is the same — do not promote.

**Decision: close the animal lever. No cow/sheep ticket.** Adding multi-animal support would be a multi-file code change (`BUILD_PASTURE`, COW/SHEEP buy+place+feed paths, wheat-buffer scaling for 3 animal types) chasing a signal that is negative per-type under control. The committed single-goose pipeline stays. The goose is a cheap, early, egg+fertilizer source with a feed cost the wheat reserve already covers; scaling to cow/sheep has no controlled-evidence upside.

**Coverage caveat (honest):** 1,489 episodes of 34,139 public episodes (4.4%), a contiguous parquet slice not a random sample. The effect sizes are large enough and the per-type signs consistent enough that a fuller sample is unlikely to flip the conclusion, but this is a prior, not a distribution. If a future ticket re-opens animals, run the full 34k backfill first (fix the parallel I/O bottleneck, not the semantics).


## 8b. Absolute-income benchmark (RM-044 foundation) — the real gap

Self-play A/B is now saturated: every movement/labor variant beats the committed baseline 80/0, and `starter` is beaten 160/0, so **win rate no longer distinguishes improvements in absolute terms**. Measured the committed agent's own final bank instead (`analysis/abs_income.py`, 20 seat-episodes vs `starter`, seed 1):

- **Committed agent mean final bank: $31,518** (median $31,797, range $29.5k–$33.4k).
- **Leaderboard winner mean: ~$92,033** (RM-040, 34,139 public episodes).

**The gap is ~3x.** Our self-play record (240/0, 80/0, etc.) measures *consistency against ourselves*, not *economic scale against the ladder*. The two structural wins this session (closest-first assignment + 4 hands) cut movement and raised parallel work, but the economy is still one-third of a top bot's. This is the new optimization target: **absolute final bank**, gated by self-play win rate only to ensure a change doesn't regress against the committed agent.


### 2026-08-22 — RM-044 probes: land and labor at scale both FAIL (root cause identified)

Three probes against the current committed agent (4 hands + closest-first, income ~$31.5k):

| Probe | Change | Income vs committed | Self-play vs committed |
|---|---|---|---|
| Land ON | buy_land=True | $20.8k (−$11k) | 0/80 REJECT |
| Hands 14 | max_hands_per_day=14 | $9.4k (−$22k) | — |

**Finding — the gap is NOT land or raw labor; it's per-hand productivity and production area.** Leaderboard winners run peak_crew 14, plant 174 tiles, and bank ~$92k. We run 5 units, plant ~25 tiles, and bank ~$31.5k. But raising hands to 14 *crashes* our income, and buying land *loses* income — because our hands mostly walk (movement still 52% post-closest-first), and our assignment has no mechanism to profitably farm a large field. More workers on our current structure just means more walkers burning hire fees.

**Root cause:** production area is the binding constraint, but land only pays if the assignment/scaling structure can actually work it. The leaderboard's 174 tiles and 14 hands are the *symptom* of a farm that already scales; naively adding our versions of those knobs reproduces the symptom without the underlying mechanism.

**Implication:** the next lever must be *per-tile production efficiency*, not more inputs. Candidates (unmeasured): fertilizer application (we collect it but never BUY/apply it), tomato/ongoing-crop management, or reducing shed-logistics trips (38% of moves). None of these is a single config flip; each is a proper code ticket. This closes the "just add land/hands" hypothesis for good.

