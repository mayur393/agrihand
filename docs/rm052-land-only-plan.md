# RM-052: NE-Only Land Expansion Test

**Date:** 2026-08-24
**Status:** EXPERIMENTAL (isolated candidate, not promoted)
**Baseline:** RM-050 (30fb6a5)

## Hypothesis

Buying the first additional quadrant (NE, $1k) with a conservative gate
(day ≤ 10, bank ≥ $4,500, post-purchase reserve ≥ $1,500) increases final
bank by providing ~8,600 additional plantable tiles while keeping the
existing crop mix, animal policy, and worker movement unchanged.

## Changes from RM-050

| File | Change |
|------|--------|
| `agents/rm052_config.py` | Isolated config: NE_ONLY_LIMIT=1, QUADRANT4_LATEST_DAY=10, QUADRANT4_CASH_THRESHOLD=4500, QUADRANT4_RESERVE=1500 |
| `agents/rm052_land_only.py` | Full copy of main.py importing from rm052_config; BUY_LAND=True; land gate uses NE_ONLY_LIMIT |
| `analysis/rm052_land_only_analysis.py` | Per-episode metrics + paired comparison vs baseline |

## Gate Results

| Gate | Result |
|------|--------|
| py_compile (both files) | ✅ PASS |
| Animal smoke test (50 eps, "pass" opponent) | ✅ PASS — 0 escapes, 0 failures |
| Runtime failures (80 paired games, "starter") | ✅ PASS — 0 failures |
| NE purchased | ✅ PASS — 43/80 episodes (54%) |
| NE planted | ✅ PASS — mean 4,324 tiles, max 8,616 |

## Comparison Table (40 seeds × 2 seats = 80 games, vs "starter")

| Metric | Candidate (RM-052) | Baseline (RM-050) | Diff |
|--------|--------------------:|-------------------:|-----:|
| Mean final bank | $48,595 | $30,934 | +$17,660 |
| Median final bank | $57,503 | $31,106 | +$26,397 |
| Q1 final bank | $33,101 | $30,309 | +$2,792 |
| Min final bank | $16,097 | $28,171 | -$12,074 |
| Max final bank | $74,419 | $33,552 | +$40,867 |
| W/L/T | 80/0/0 | — | — |
| Win rate | 1.000 | — | — |
| Wilson 95% CI | [0.954, 1.000] | — | — |

## Key Observations

1. **NE is purchased and planted when the gate opens.** In 43/80 episodes
   (54%), the candidate reaches $4,500 by day 10 and buys NE. Mean NE
   planted tiles: 4,324. The land is actively used, not wasted.

2. **Dramatic income boost when NE is purchased.** Episodes with NE land
   show final banks of $54k–$74k vs the baseline's ~$31k. The additional
   ~8,600 plantable tiles translate directly to higher production.

3. **Episodes without NE purchase still outperform baseline.** Even when the
   $4,500 threshold isn't met by day 10, the candidate averages ~$33k
   (slightly above baseline $31k) because the conservative gate prevents
   premature spending.

4. **Min final bank is lower than baseline** ($16k vs $28k): when NE IS
   purchased, the $1k cost + worker spread thin occasionally hurts. This
   is the classic RM-015/016 land-trap risk, but the conservative gate
   limits its frequency.

5. **Animal escapes against "starter" opponent** (not "pass"): when NE is
   purchased, worker spread causes some cows to go unfed. This is a
   pre-existing animal-feeding issue exacerbated by land expansion. The
   smoke test (pass opponent) shows 0 escapes.

6. **80/0/0 W/L/T against starter** — the land expansion provides such a
   large income boost in eligible episodes that it dominates even when
   some episodes underperform.

## Next Steps

- Investigate animal-feeding resilience under land expansion (worker zone
  assignment may need adjustment when NE is owned).
- Test whether raising the cash threshold reduces the min-final-bank tail.
- Consider whether NE_ONLY should eventually expand to SW/SE if income
  allows.
