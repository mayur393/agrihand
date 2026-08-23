# RM-050 — Total structural rework (the coherent build, not fragment A/Bs)

## Objective

Raise Agrihand's economy from ~$32k to the leaderboard ~$90k+ by rebuilding the
core loop as ONE coherent change. Every prior fragment test rejected because the
levers are gated behind a base scale this agent does not have. This plan builds
the base scale and the levers together, then gates the result as a whole.

## Ground truth established this session (evidence, not guesses)

1. **Labor is the strongest lever** — full-34k rating-controlled regression:
   `total_hires` +$12,151/SD (multivariate), `peak_crew` +$5,596/SD. Leaders run
   6-16 hands; we run 4.
2. **Cow and sheep are positive** — `max_cows` +$3,193/SD, `max_sheep` +$3,032/SD,
   `max_geese` -$1,635/SD. Leaders deploy 7-15 cow/sheep; we run 1 goose.
3. **Land/tiles is NOT the lever** — `tiles_planted` -$4,304/SD, `first_land_day`
   -$1,271/SD (both under skill control). Do NOT buy land.
4. **Winning replay (causal, our bot's actual loss):** opponent buys COW on day 0,
   plants wheat+melon immediately, sells MILK from day 8, compounds to 15 cows and
   $48.6k with 12 hands. The cow is the compounding asset; labor is the engine.
5. **Our agent's blockers** (from profilers): hands spend ~52-68% of turns walking
   (movement-inefficient), seeds are stocked 1-at-a-time, and animals are gated
   behind a wheat buffer that delays the first purchase.

## The rework (coherent, not incremental)

Build these three together. Do not A/B them separately — they only work as a unit.

### 1. Aggressive early economy
- Buy cow on day 0 (not goose) with starting cash. Cow = $400, MILK from day 8,
  `max_held` 6, the compounding asset.
- Bulk-buy seeds up to a working stock (config `SEED_STOCK_TARGET=3`) instead of
  `BUY_SEED crop 1` only when empty. This lets the field re-plant immediately.
- Remove the wheat-buffer gate on the FIRST animal purchase (the buffer protects
  feed later; it must not block the initial capital deployment).

### 2. Labor efficiency (the engine)
- Closest-first assignment is already in (RM-042). Add **spatial zones**: each
  hand owns a quadrant/row band; cross only for urgent feed/wheat duties. This
  cuts the 52-68% movement share so hands actually produce.
- Raise labor scale tied to real work (not a blunt `MAX_HANDS_PER_DAY` bump):
  hire when the standing-task backlog exceeds capacity, and let the hand count
  grow with the production surface (animals + planted tiles). Target ~8-12 hands
  by mid-season, matching winners.

### 3. Cow/sheep scaling (the compounding asset)
- Structure-first, one-ahead: build pasture N+1 before buying animal N+1; never
  buy with no empty pasture (that was the cash-drain regression).
- Scale cows toward a target (start `TARGET_ANIMALS=8`), one per pasture tile.
- Feed from carried wheat (M1), harvest MILK/WOOL, sell steadily. Sheep are a
  secondary positive lever; cows first.

## Hard rules that MUST survive

- Zero animal escapes (the existing `--animals` gate).
- Wheat feed reserve scales with herd: `WHEAT_BUFFER_PER_ANIMAL × animals + BASE`.
- No land buying (`BUY_LAND=False` stays; land is not the lever).
- Stdlib-only submission, `agent` last callable, two-arg signature, no network.
- No `demo/` changes.

## Failure modes to guard (all observed this session)

- Buy-before-build → cash drain to $0. Guard: build structure before buy.
- Build-all-structures-upfront → dead capital. Guard: one-ahead only.
- Cow-first in isolation → early-economy starvation. Guard: it only ships WITH
  bulk seeds + labor scale, never alone.

## Acceptance criteria

- [ ] Absolute income > $45k mean vs `starter` (from $32.1k baseline), measured
      by `analysis/abs_income.py` — the real target, since self-play is saturated.
- [ ] Self-play win rate vs the committed $32.1k agent does NOT regress (CI LB
      stays > 0.50 as a floor).
- [ ] `eval/smoke.py --animals` 50 episodes, 0 escapes.
- [ ] `eval/smoke.py --full` 150 episodes, 0 failures.
- [ ] `scripts/precheck_submission.py` passes (last-callable, signature, stdlib,
      no-network, root-import).

## Do NOT do

- Do not test cows, labor, or bulk-seeds as separate A/Bs — they only work as a
  unit, and separate tests have all rejected for the same gating reason.
- Do not buy land, re-open strawberry/fertilizer, or chase leaderboard "tiles" —
  all are confounded or negative under skill control.

## Deliverable

One committed `main.py` (+ `config.py` additions) implementing all three parts
together, passing the gates above, archived as `agents/rm050_rework.py`. If it
regresses, revert and record the result — do not leave a broken agent committed.
