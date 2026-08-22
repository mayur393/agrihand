# RM-043 — Animal count vs final_bank (rating-controlled)

Seats: 2978 | episodes: 1489

Coefficients are final_bank dollars per +1 SD (or +1 animal).

## Model comparison

| predictor | A raw | C ladder_score |
|---|---|---|
| max_animals | 7,402 | 6,196 |
| max_geese | -3,457 | -2,811 |
| max_cows | -2,466 | -1,905 |
| max_sheep | -4,301 | -3,212 |
| ladder_score (control) | — | 3,858 |

## Notes

- Correlational leaderboard data; A/B before trusting. This is the animal lever RM-040 could not test (feature column was missing).
- The existing committed agent runs exactly ONE goose; top ladder bots are animal-saturated (median 14, max 35 in the 592-row summary sample).
