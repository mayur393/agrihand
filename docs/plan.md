# Experiment Log — Agrihand

Dated record of every promotion/rejection decision. Append rows; never rewrite history. One row per decision (TICKET-01).

Format: `YYYY-MM-DD | candidate (hash) | opponent | games | win rate | Wilson 95% CI | decision`

---

## 2026-08-10

| Date | Candidate | Opponent | Games | Win rate | CI (LB, UB) | Decision |
|---|---|---|---|---|---|---|
| 2026-08-10 | — (repo scaffold, no main.py yet) | — | — | — | — | No candidates yet. Gates built; v1 pending. See PLAN.md §9. |

### Notes
- No promotion decisions made yet — `main.py`/`config.py` don't exist (repo skeleton + demo/visualizer work only so far).
- `eval/check_findings.py` passes vacuously ("nothing to scan") until `main.py` exists — first real enforcement happens at v1 (TICKET-10).
- Competition rules captured in `docs/rules-notes.md` (gap #1).

## 2026-08-12 — RM-009 mechanic verification (M1–M10 from engine source)

| Date | Candidate | Opponent | Games | Win rate | CI (LB, UB) | Decision |
|---|---|---|---|---|---|---|
| 2026-08-12 | — (no candidate; mechanics only) | — | — | — | — | All M1–M10 rows answered + micro-tests green. |

### Notes — mechanics with strategy impact (discrepancy policy, findings §6)
- **M7 (TICKET-07 overturned):** rules-doc assumption "stockpiling on farmer/hand inventories does not bypass the cap" is **wrong**. Engine: units carry unlimited items mid-day; only shed capacity (100) binds, enforced at DROP/PLACE/end-of-day. Implication for v1 (RM-012): heavy harvesters can carry a lot mid-day, but overflow beyond shed capacity is discarded at day end — so the binding constraint is shed capacity, and the "never overfill carried inventory" concern is really a shed-capacity concern. No code depends on M7 yet; RM-012 acceptance criteria updated accordingly.
- **M1:** FEED consumes from carried inventory, not shed — v1 feeding logic must carry wheat to animals.
- **M8:** first-hand spawn is first FREE shed-access tile (NWSE), (5,4) only when free — NE-first land expansion still unlocks it, but the "always (5,4)" claim was a simplification.

## 2026-08-12 — RM-012 v1 wheat/carrot loop PROMOTED vs starter

| Date | Candidate | Opponent | Games | Win rate | CI (LB, UB) | Decision |
|---|---|---|---|---|---|---|
| 2026-08-12 | main.py v1 (wheat/carrot NW field) | starter | 80 paired (160 eps) | 1.000 | (0.977, 1.000) | **PROMOTE** |

### Notes
- **RM-012 exit gate passed:** smoke --full 150 ep / 0 fail; tournament 160/0 vs starter, LB 0.977 > 0.50 → PROMOTE. Cross-seed check (1,2,3,5,7,11) all wins by ~$700–900 margin (diagnostic only, not criterion).
- **Design decisions (RM-012):** v1 farms a small 3×3 NW field near the shed in deterministic scan order; does NOT buy land (RM-015's job — expansion is a net cash drain until the field scales); harvest is shed-room-aware (M7: never harvest more than shed can absorb); sell only above floor price, keep wheat buffer.
- **Engine-contract bug found:** kaggle_environments loads the LAST callable in main.py as the agent (`get_last_callable` returns `[...][-1]`). Helpers after `agent` silently replace it. Fixed by ordering helpers first + docstring warning. Logged for RM-014 (same contract applies).
- **tournament.py fix:** resolve_agent now adds the file's dir to sys.path so `from config import ...` works (matches engine's exec loader).

## 2026-08-13 — RM-014 BFS task assignment PROMOTED (no regression)

| Date | Candidate | Opponent | Games | Win rate | CI (LB, UB) | Decision |
|---|---|---|---|---|---|---|
| 2026-08-13 | main.py v1.2 (BFS task assignment) | starter | 80 paired (160 eps) | 1.000 | (0.977, 1.000) | **PROMOTE** |

### Notes
- **RM-014 exit gate passed:** smoke --full 150/0; tournament 160/0 vs starter, LB 0.977 (unchanged from RM-012 — no regression). Cross-seed 1,3,7 all WIN (margin ~$650–900).
- **Two bugs found during the refactor:**
  1. `_bfs_nearest` excluded the start tile from target consideration — the farmer ping-ponged between two empty PLANT tiles, never planting. Fixed: start tile is a distance-0 candidate.
  2. PLANT targets on ANY empty tile made the farmer wander the whole board. Fixed: PLANT restricted to the near-shed field (`_in_field`, PLANT_RADIUS).
- **M7 refinement:** DROP now fires when it unblocks a harvest (yield > shed room) OR carry ≥ threshold — not just carry ≥ threshold (old v1 behavior let a full shed strand a harvestable crop).
- **Benchmark:** 0.088 ms/call worst-ish single-farmer turn (20 scattered unwatered plants, corner start, BFS_MAX_STEPS=16) — logged findings §3, far under 100 ms budget. Re-benchmark at RM-016 when hands arrive.
- **Per-unit structure:** `_assign_task(unit_pos, farm, private, day, board_size)` is position-parameterized — RM-016 (hired hands) reuses it per unit without rewrite.

## 2026-08-13 — RM-015 land expansion A/B: REJECTED (single farmer)

| Variant | Opponent | Games | Win rate | CI (LB, UB) | Decision |
|---|---|---|---|---|---|
| land-OFF (committed main.py, BUY_LAND=False) | starter | 80 paired (160 eps) | 1.000 | (0.977, 1.000) | **PROMOTE** |
| land-ON (BUY_LAND=True) | starter | 80 paired (160 eps) | 0.000 | (0.000, 0.023) | **REJECT** |

### Notes
- **Decision: land expansion is NOT promoted.** For a single farmer, buying land (NE→SW→SE, reserve-buffer rule) is a catastrophic regression: the farmer spreads across 3 quadrants, walks instead of farming, and ends with less cash than a land-OFF agent. Land-OFF wins ~$4.5–4.9k vs starter's ~$3.5k; land-ON makes ~$1.6k.
- **This is a scope decision, not a strategic conclusion** (per RM-012's note): a single farmer can't work more land than the NW field — the extra tiles just sit empty while the farmer wastes turns walking. **Revisit at RM-016 (hired hands) when there's labor to actually work the extra tiles.** The A/B harness + variants (`agents/v1_land_on.py`, `agents/v1_land_off.py`) stay for that re-test.
- **CRITICAL engine-contract bug found during A/B:** the runner calls `agent(observation, configuration)` — TWO positional args. My RM-015 change made `agent(obs, buy_land=BUY_LAND)` — the engine's configuration dict landed in `buy_land`, and since a non-empty dict is truthy, land-buying was silently ENABLED in both "land-ON" and (initially) "land-OFF" runs. Fixed: `agent(obs, configuration=None, buy_land=BUY_LAND)`. **This is the second engine-contract failure (after last-callable) — both are silent, both caught by tournament results, neither caught by smoke (which only checks no-exception).** Worth adding a signature check to the precheck.
- **Margin improvement:** committed land-OFF now makes ~$4.5–4.9k vs RM-014's ~$4.3k — the fix (configuration not landing in buy_land) also means the earlier RM-014 runs were accidentally land-ON-ish, so RM-014's true baseline was slightly lower. No regression; smoke --full 150/0.

## 2026-08-13 — RM-016 farm hands 2×2 A/B: land resolved, hands neutral

**2×2 A/B (all vs starter, 80 paired games each, seed 1):**

| Land | Hands | W/L/T | Win rate | CI (LB, UB) | Decision |
|---|---|---|---|---|---|
| OFF | OFF | 160/0 | 1.000 | (0.977, 1.000) | **PROMOTE** |
| OFF | ON | 160/0 | 1.000 | (0.977, 1.000) | PROMOTE |
| ON | OFF | 0/160 | 0.000 | (0.000, 0.023) | REJECT |
| ON | ON | 0/160 | 0.000 | (0.000, 0.023) | REJECT |

### Notes
- **Land is the dominant factor and is decisively bad with OR without hands** — the "land+labor pays off" hypothesis is **FALSIFIED** at this scope. Buying land (NE→SW→SE) loses 0/160 regardless of hiring. The replay's top-bracket full-coverage observation (findings §7) remains a soft prior for a much larger farm economy (animals, many units), not reachable by v1's wheat/carrot loop.
- **Hands are neutral at v1 scope**: both no-land arms win 160/0 with identical CI. Margin diagnostic (6 seeds): 1114 with hands vs 1196 without — within noise, slightly favoring no-hands. Hired hands plant/water/harvest fine (shared `_unit_action`), but the labor surplus isn't worth the fibonacci cost (~$2-4/day) when one farmer already clears the field.
- **Promoted combination: (land OFF, hands OFF).** Committed `BUY_LAND=False, HIRE_HANDS=False`. Simpler, marginally better margin, no regression (160/0, CI [0.977, 1.000]).
- **`_assign_task` generality claim CONFIRMED:** no hand-specific special-casing was needed. `_unit_action(pos, farm, private, day, board_size, idx)` serves farmer and hands identically; `idx` threads the per-unit inventory slot (M7 carry check). M8 handled by reading each hand's ACTUAL position from `me["hands"]` each turn — no assumed (5,4) spawn.
- **M1 (FEED carry wheat) is structurally moot until RM-019** — no animals means no FEED task is generated, so there's no carry-wheat precondition to enforce yet. Noted, not coded as dead logic.
- **Backlog fix during dev:** `_count_backlog` initially counted every empty tile as a PLANT task → backlog always > threshold → hired hands every day, planting everywhere, bleeding money. Fixed to count only URGENT tasks (WATER/HARVEST/DIG, priority ≥ DIG). This is why the first hands-ON run lost ($3163) before the fix ($4545).
- smoke --full 150/0; micro_tests ALL PASS.

## 2026-08-13 — RM-017 crop diversification A/Bs: NEGATIVE (no benefit at v1 scope)

**Two separate A/Bs (80 paired games each vs starter, seed 1):**

| Variant | W/L/T | Win rate | CI (LB, UB) | Avg margin (8 seeds) |
|---|---|---|---|---|
| baseline (wheat/carrot) | 160/0 | 1.000 | (0.977, 1.000) | 1238 |
| +tomato | 160/0 | 1.000 | (0.977, 1.000) | 1188 |
| +melon | 160/0 | 1.000 | (0.977, 1.000) | 1158 |

### Notes
- **Neither tomato nor melon improves win rate OR margin.** All three variants win 160/0 (CI identical); margins are within seed noise (1238 vs 1188 vs 1158). The crop mix is NOT the bottleneck at v1's small single-farmer field.
- **Why likely no help:** premium crops have higher seed cost (tomato $50, melon $80 vs wheat $10) and long lead times (8–10 days to first yield vs wheat/carrot 2 days). On a tiny field farmed by one farmer within a 30-day season, the delayed payoff doesn't beat the fast wheat/carrot cycle.
- **Step 3 NOT run** (per RM-017 acceptance criterion): neither crop showed individual improvement, so no three-way crop+land+hands test. The "land+labor+crop" hypothesis has no individual signal to justify it; the prior two land rejections (RM-015/016) stand.
- **Framing preserved for later:** a 0/160 land rejection twice means the next land attempt needs a genuinely different input mix. The replay's top-bracket crop/animal density remains the soft prior — but that scale likely needs animals (RM-019) + premium crop timing (RM-018), not just adding TOMATO/MELON to the existing loop.
- Committed main.py stays baseline crop_mix=("WHEAT","CARROT"), BUY_LAND=False, HIRE_HANDS=False. smoke --full 150/0; no regression.
