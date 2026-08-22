# Kaggriculture Baseline v1

## Commit

```
2816112 RM-019: coop/pasture + placement pipeline (dormant-safe, no promotion)
```

## Strategy

- Wheat + carrot
- Small near-shed field
- BFS task assignment
- WATER > HARVEST > DIG > PLANT
- Immediate selling
- Wheat buffer enabled
- M7 shed-room-aware harvesting
- DROP_CARRY_THRESHOLD=20

## Disabled Features

- BUY_LAND = False
- HIRE_HANDS = False
- ANIMALS_ENABLED = False
- timed_sell = False
- OPPONENT_AWARE_SELL_TIMING = False

## Smoke Test

Command:

    .venv/bin/python eval/smoke.py --full

Result:

    PASS

Result observed:

    150/0

## Tournament Baseline

Record the existing paired tournament result here.

Expected existing result:

    vs starter: 160/0
    CI: [0.977, 1.000]

Command (from PLAN.md §8.3 and eval/tournament.py):

    .venv/bin/python eval/tournament.py --candidate main.py --opponent starter --games 80 --seed 1 --episode-steps 720

## Notes

This is the frozen baseline for all future strategy experiments.

No strategy changes are part of Ticket 01.
