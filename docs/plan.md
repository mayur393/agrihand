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
