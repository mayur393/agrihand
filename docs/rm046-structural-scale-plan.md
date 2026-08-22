# RM-046 — Structural rework: scale production area (the 3x lever)

## Why this is the design, not another knob

Three improvement attempts rejected this session, all for the same underlying
reason:

| Attempt | Result | Root cause |
|---|---|---|
| Strawberry mix (RM-041) | 0–4/80 | confounded regression signal |
| Land ON / hands=14 (RM-044) | 0/80, income crashes | dilution + walkers |
| Fertilize melon (RM-045) | 0/80, −$6.7k | micro-opt on a 25-tile budget |

The measured gap is **~$31.5k (us) vs ~$92k (leaderboard winners)**, and the
single biggest structural difference is **production area**: winners plant
**~174 tiles** to our **~25 tiles** (leaderboard `tiles_planted` median). Tuning
a 25-tile farm cannot reach 174-tile income; the lever is **scale**.

**Strategic frame (from the hand-movement discussion):** turns are fixed at 720;
a hand acts in parallel with the farmer for a coin cost, not a turn cost. So
scale is achieved by *productive actions per turn across a large field*, not by
raw worker count. RM-042 already proved this: closest-first assignment cut
movement 68.4%→52.2% and made 4 hands pay. The remaining step is to make a
**100-tile field** productive, which land alone does not do — it currently
spreads units thin and starves planting.

## Diagnosis (what actually breaks land ON, from the code)

`main.py` today:
- **Seed stocking is 1-at-a-time** (`_market_orders`: `BUY_SEED crop 1` only when
  `seeds[crop] == 0`). This caps planting rate to ~1 tile/turn/crop, so 75 extra
  land tiles never fill.
- **No spatial ownership**: every unit BFSes the whole board each turn. On a
  100-tile field this means long cross-board walks (movement is still ~52%).
- **PLANT priority (2) is starved** below WATER/HARVEST/DIG, so empty land tiles
  wait behind daily care and never reach standing production.
- **Land gate** (`QUADRANT4_*`) buys NE→SW→SE ($7k total) but there is no
  mechanism to work the new tiles, so the $7k spend is pure dilution.

**The fix is not "buy land" — it is "buy land + fill it fast + keep units zoned
so each tile gets tended without cross-board walking."** That is a coherent
structural change, split into three independently A/B-able phases.

## Design (phased; each phase gated before the next)

### Phase 1 — Fast seed stocking (prerequisite, zero risk)
Change the seed-buy loop from "buy 1 when empty" to "buy up to a working stock
target per crop." This alone lets the 25-tile field re-plant immediately after
harvest instead of waiting a turn for the next seed. It is also the prerequisite
for filling a large field.

- New config: `SEED_STOCK_TARGET = 3` (working stock per crop; no literal in
  decision logic).
- `_market_orders`: for each crop, `BUY_SEED crop (target - seeds[crop])` when
  below target and affordable, capped by the 10-order/turn limit.
- **A/B alone** vs committed (expect neutral-to-positive; this unblocks Phase 3,
  it does not itself close the gap).

### Phase 2 — Spatial zones (the anti-dilution mechanism)
Assign each unit a home zone (quadrant or row band) derived from a stable
unit-id hash. A unit prefers tasks inside its zone; it crosses zones only for
urgent feed / wheat-reserve duties (the RM-036 guards must keep working).

- `_closest_first_assign` and `_assign_task` gain a `zone_of(pos)` filter: when
  non-urgent tasks exist in the unit's zone, restrict the target scan to that
  zone; fall back to the full board only when the zone is clean.
- Zones must respect the **pinned land order** (NE→SW→SE) and the shed-access
  tiles, so a unit's zone is always the quadrant it can reach cheaply.
- **A/B alone** vs committed on the *current* 25-tile field (expect neutral — the
  field is too small for zones to matter). This is a no-regression gate, not a
  promotion.

### Phase 3 — Land + fast stocking + zones (the actual rework)
Combine `buy_land=True` with Phases 1–2 so the new land is both affordable and
workable. This is the promotion candidate.

- **A/B** vs committed on **absolute income** (not self-play win rate, which is
  saturated): target is a *real* income lift toward the $92k ladder norm, with
  self-play win rate as a no-regression floor (must not lose to committed).

## Files to change

- `config.py` — add `SEED_STOCK_TARGET`, `ZONE_ENABLED`, zone dimensions
  (e.g. `ZONE_ROWS=5` for 2 horizontal bands, or quadrant keys), with comments
  linking to this plan. All tunables live here (TICKET-06).
- `main.py` — `_market_orders` (bulk seed buy), `_closest_first_assign` +
  `_assign_task` (zone filter), `agent` (new `zone_enabled` flag). Reuse
  `_bfs_distances` (already added in RM-042) for zoned BFS; do not add a second
  BFS implementation.
- `agents/rm046_*.py` — one wrapper per phase (stock-only, zones-only,
  full-rework), same archived pattern (`agent` last, two-arg signature).
- `analysis/` — a scale profiler that reports `tiles_planted`, `peak_crew`,
  movement share, and final bank, so the A/B measures the *mechanism* (did land
  actually fill?) not just the outcome.

## Step 0 — close the one evidence gap before building

Run the controlled regression that includes `tiles_planted` as a predictor
(final_bank ~ tiles_planted + first_land_day + peak_crew + total_hires, control
`ladder_score`) on the 34k public episodes. Expected (from the raw distributions)
is a large positive `tiles_planted` coefficient — but this must be *confirmed
with rating control*, exactly like RM-040, before committing to a land-based
rework. If `tiles_planted` does **not** survive ladder_score control, stop and
re-plan: scale was a symptom, not a lever, and the rework is wrong.

## Verification / acceptance criteria

- [ ] Step 0 regression confirms `tiles_planted` survives rating control.
- [ ] Phase 1 A/B: income not regressed (neutral-to-positive) vs committed.
- [ ] Phase 2 A/B: no regression vs committed on the 25-tile field.
- [ ] Phase 3 A/B: **absolute income rises** toward the ladder norm, AND
      self-play win rate vs committed does not drop below the CI no-regression
      floor.
- [ ] `eval/smoke.py --animals` 0 escapes, `--full` 0 failures before any
      promotion (animals stay enabled; the wheat feed reserve guards must survive
      zones — a zone change that starves the goose is an automatic reject).
- [ ] No `demo/` changes, no new dependency, stdlib-only submission unchanged.

## Deferred / out of scope

- Opponent-aware sell timing (TICKET-05) — remains flag-OFF, not needed for scale.
- Imitation/RL — already ruled out (stdlib-only, no runtime artifact).
- Animal scaling — closed by RM-043 (per-type negative under control).
- Cow/sheep multi-animal support — closed by RM-043.

## Why phased, not one big rewrite

A monolithic "scale rewrite" is un-A/B-able — if it fails we can't attribute
why. Phases 1–2 are individually neutral-safe and isolate the two prerequisites
(fast stocking, zoned movement) so Phase 3 is a *clean* test of "land pays when
the farm can work it." Each phase passes the existing Wilson-CI / smoke / escape
gates before the next.
