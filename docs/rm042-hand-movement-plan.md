# RM-042 — Hand movement & parallel-work efficiency

## The strategic frame (correct, and it changes what we optimize)

Turns are fixed at 720. A hand does its action in the *same* turn as the farmer,
in parallel — so hiring a hand does not cost turns, only coins (the daily
fibonacci hire fee). The real lever is therefore:

> **productive actions per turn** = (worker count) − (turns each worker wastes
> walking, idling, or contending for the same tile).

A hand that walks 8 tiles to a task produced 0 for 8 turns. A hand that chases
the same tile the farmer already claimed wasted the whole trip. So the job is
not "more hands" — it is "make every hand's walk short and its target
uncontested." That is a movement/assignment problem, not a hiring problem.

This is exactly why RM-016 found hands *neutral* at v1 scope (one farmer
cleared the small field; extra hands only added cost and idle) and why RM-036's
combo made them *decisive* (the premium mix + animals created enough standing
work that parallel hands finally paid). The bottleneck is now whether the
hands we already hire are used efficiently.

## Current code reality (where turns are wasted)

- **Farmer-first greedy, not closest-first.** `agent()` assigns the farmer first,
  then each hand in order, from a per-turn `claimed_targets` set. The farmer can
  claim a tile a hand is already standing next to; the hand then walks far for
  its own second choice. Waste = global matching should be closest-unit-first.
- **No persistence across turns.** `claimed_targets` is rebuilt empty every turn.
  A hand walking toward a far tile can lose it next turn to a unit that got
  closer, then re-target and walk again. Waste = repeated chasing.
- **Priority dominates distance.** `_assign_task` iterates priority classes high
  → low and BFSes the nearest tile *of that class*. A hand near a low-priority
  PLANT tile will abandon it and walk up to `BFS_MAX_STEPS` (16) to a WATER tile
  — even when the farmer is already closer to that WATER tile. Waste = long
  walks for a priority that another unit was going to clear anyway.
- **No spatial ownership.** Every unit BFSes the whole board each turn. Hands
  roam; nothing keeps a hand working its own neighborhood.
- **Shed shuttling is shared by everyone.** Every harvester does its own
  PICKUP/DROP walks. Waste = the same logistics trip repeated by many units.

## Step 0 — measure before changing (mandatory)

Add a dev-only turn-tally (NOT in the submission) that counts, per unit per
episode: `move` actions vs `act` actions (water/harvest/plant/feed/care/dig/
pickup/drop), plus how many turns a hand is idle (`PASS`). Run it on the
committed `main.py` vs a few opponents. This tells us the *actual* waste split
(walking vs idle vs contention) before we pick a lever. No A/B without the
number, because the levers below fix different waste kinds.

## Levers (smallest diff first; each is its own self-play A/B)

1. **Closest-unit-first assignment.** Replace "farmer first, then hands" with a
   single min-cost matching of all units ↔ all unclaimed task tiles (Hungarian
   or simple greedy closest-pair). Priority stays a *soft* tiebreak, distance the
   *hard* objective. Small, high-leverage — kills the "farmer steals a hand's
   nearby tile" waste directly.

2. **Persistent intent across turns.** Carry a unit → target claim across turns;
   release it only when the unit arrives, the target stops being actionable, or
   a cheaper target appears within a small radius. Kills repeated chasing.

3. **Distance-aware priority (walk budget).** Cap how far a unit will walk for a
   +1 priority bump — a near lower-priority task may beat a far higher-priority
   one. Kills "walk 16 tiles to water while the farmer is already on it."

4. **Spatial zones.** Partition the board (quadrants or row bands) and let each
   hand own its zone; a hand only leaves its zone for urgent feed/wheat-reserve
   duties. Kills cross-board roaming. This is the "hand specialization recipe"
   made concrete — but it is bigger than 1–3, so it runs last.

5. **Role specialization (runner).** One hand owns shed logistics (PICKUP/DROP);
   field hands stay planted/harvesting. Kills duplicate shed trips. Also larger;
   only pursue if 1–4 leave shed-walk as the dominant waste in the Step-0 tally.

Each lever is a config-gated or wrapper variant (same `agents/rm042_*.py`
pattern as RM-041). A/B each against committed `main.py` in self-play; promote
only when Wilson 95% CI lower bound > 0.50 on win rate (TICKET-01), never on
margin.

## Scope — hard lines

- No RL/imitation, no new runtime dependency (stdlib-only submission stays).
- No `demo/` changes (taste rule).
- Do not touch `MAX_HANDS_PER_DAY` until movement efficiency is measured —
  raising hands on top of wasted turns just buys more idle workers.
- Land expansion stays rejected (RM-015/016).
- Win rate decides; margin is diagnostic only (TICKET-08).

## Files

- `analysis/turn_tally.py` — Step-0 dev-only profiler (not shipped).
- `agents/rm042_closest_first.py`, `agents/rm042_persistent_intent.py`,
  `agents/rm042_walk_budget.py`, `agents/rm042_zones.py`, `agents/rm042_runner.py`
  — one wrapper per lever (archived pattern, `agent` last).
- `reports/rm042_ab.md` — W/L/T, CI, margins per lever.
- On a promotion: update `main.py` (and `config.py` if a tunable is added),
  then log the dated row in `docs/plan.md` and the result in `docs/findings.md`/
  `docs/roadmap.md`.

## Acceptance criteria

- [ ] Step-0 tally quantifies move/act/idle per unit before any lever.
- [ ] Each lever is A/B'd vs committed `main.py` in self-play (starter is
      saturated — it can only confirm "not broken").
- [ ] Promotion only when Wilson 95% CI **lower bound > 0.50** on win rate.
- [ ] Zero animal escapes (`eval/smoke.py --animals`) before any promotion;
      `eval/smoke.py --full` clean.
- [ ] A lever that raises margin but not win rate is **not** promoted.

## Deferred

- Animal-count lever (needs a parquet backfill; only the 593-row `summary.csv`
  has `max_animals`).
- Raising `MAX_HANDS_PER_DAY` — revisit only after movement waste is reduced and
  the Step-0 tally shows idle is no longer the binding constraint.
