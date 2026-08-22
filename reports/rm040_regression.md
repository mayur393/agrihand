# RM-040 — Rating-controlled predictors of final_bank

Seats: 68278 | public episodes: 34139

Coefficients are **final_bank dollars per +1 SD** of the predictor (continuous) or per binary flip (no_land).

## Model comparison (does the lever survive skill control?)

| predictor | A raw | B rating | C ladder_score |
|---|---|---|---|
| plants_wheat | -3,536 | -4,093 | -4,205 |
| plants_melon | -1,656 | -1,455 | -1,413 |
| plants_strawberry | 6,171 | 4,914 | 5,761 |
| plants_tomato | -3,120 | -2,886 | -3,018 |
| plants_carrot | -2,374 | -2,162 | -2,268 |
| peak_crew | 1,078 | -998 | -122 |
| total_hires | 12,002 | 12,696 | 12,715 |
| first_land_day_filled | -1,019 | -1,226 | -665 |
| no_land | -153 | -147 | -530 |
| crop_diversity | 77 | 146 | -53 |
| rating (control) | — | 4,064 | — |
| ladder_score (control) | — | — | 3,008 |

## Within-rating-band winner-vs-loser wheat volume

| band | loser_wheat | winner_wheat | delta | n |
|---|---|---|---|---|
| Q1 | 58.8 | 68.7 | 9.8 | 16672 |
| Q2 | 106.3 | 121.3 | 15.0 | 16670 |
| Q3 | 106.9 | 120.3 | 13.5 | 16672 |
| Q4 | 102.6 | 109.9 | 7.3 | 16670 |

## Paired within-episode deltas (margin on delta, control d_rating)

| predictor delta | coef_per_sd |
|---|---|
| d_plants_wheat | 901 |
| d_plants_melon | -1,611 |
| d_plants_strawberry | 4,880 |
| d_peak_crew | 2,486 |
| d_total_hires | 3,359 |
| d_first_land_day_filled | -326 |
| d_rating (control) | 84 |

## Notes

- `first_land_day_filled` uses 30 for 'never bought land'; lower = earlier land = more season to use it.
- Model B controls for **post-game** rating, which the outcome itself updates — that is endogenous and can under-credit real levers. Model C (ladder_score, a team snapshot not tied to this game) is the cleaner skill control. Model D (paired delta) controls the environment but NOT the within-pair skill gap — the winner is systematically higher-skill, so its deltas trend positive on every lever. Read D as a robustness view of the confound, not clean evidence.
- Correlational from leaderboard data. None of this is a promotion; each surviving lever needs its own self-play A/B (RM-041).
