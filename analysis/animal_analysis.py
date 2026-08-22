#!/usr/bin/env python3
"""RM-043 — rating-controlled analysis of animal count on final_bank.

Reads the animal backfill (`animal_backfill.csv`) plus episodes + teams CSVs and
runs the same skill-control treatment as RM-040: raw OLS, then ladder_score
control (the cleanest — a team snapshot not tied to this episode). The animal
lever could not enter RM-040 because `episode_features.csv` had no animal
column; this closes that gap.

DEV-ONLY. Not shipped. Writes reports/rm043_animals.md.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

DATASET = Path("/home/mayur/Projects/Dataset")
REPORT = Path("/home/mayur/Projects/agrihand/reports/rm043_animals.md")

PREDICTORS = ["max_animals", "max_geese", "max_cows", "max_sheep"]


def _ols(y, X, names):
    Xz = (X - X.mean(axis=0)) / X.std(axis=0, ddof=0)
    Xd = np.column_stack([np.ones(len(y)), Xz])
    beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
    return pd.DataFrame({"predictor": names, "coef_per_sd": beta[1:]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", default=str(DATASET / "animal_backfill.csv"))
    args = ap.parse_args()

    animals = pd.read_csv(args.backfill, dtype={"episode_id": "int64",
                                                "seat": "int64"})
    eps = pd.read_csv(DATASET / "episodes.csv",
                      usecols=["episode_id", "type", "bank_0", "bank_1",
                               "rating_0", "rating_1", "team_0", "team_1"])
    teams = pd.read_csv(DATASET / "teams.csv", usecols=["team_id", "ladder_score"])
    eps = eps[eps["type"] == "EPISODE_TYPE_PUBLIC"]

    rows = []
    for seat in (0, 1):
        a = animals[animals["seat"] == seat].copy()
        a = a.merge(eps, on="episode_id", how="inner")
        a["final_bank"] = a[f"bank_{seat}"]
        a["rating"] = a[f"rating_{seat}"]
        a["team_id"] = a[f"team_{seat}"].astype(str)
        a = a.merge(teams.assign(team_id=teams["team_id"].astype(str)),
                    on="team_id", how="left")
        rows.append(a)
    d = pd.concat(rows, ignore_index=True)

    print(f"seats: {len(d)} | episodes: {d.episode_id.nunique()}")
    print(d[PREDICTORS].describe().round(1).to_string())

    y = d["final_bank"].to_numpy(dtype=float)
    X = d[PREDICTORS].to_numpy(dtype=float)
    raw = _ols(y, X, PREDICTORS)

    sub = d[d["ladder_score"].notna()].copy()
    Xc = np.column_stack([sub[PREDICTORS].to_numpy(dtype=float),
                          sub["ladder_score"].to_numpy(dtype=float)])
    ctrl = _ols(sub["final_bank"].to_numpy(dtype=float), Xc,
                PREDICTORS + ["ladder_score"])

    lines = []
    lines.append("# RM-043 — Animal count vs final_bank (rating-controlled)\n")
    lines.append(f"Seats: {len(d)} | episodes: {d.episode_id.nunique()}\n")
    lines.append("Coefficients are final_bank dollars per +1 SD (or +1 animal).\n")
    lines.append("## Model comparison\n")
    lines.append("| predictor | A raw | C ladder_score |")
    lines.append("|---|---|---|")
    a = dict(zip(raw.predictor, raw.coef_per_sd))
    c = dict(zip(ctrl.predictor, ctrl.coef_per_sd))
    for p in PREDICTORS:
        lines.append(f"| {p} | {a.get(p, float('nan')):,.0f} | {c.get(p, float('nan')):,.0f} |")
    lines.append(f"| ladder_score (control) | — | {c.get('ladder_score', float('nan')):,.0f} |")
    lines.append("")
    lines.append("## Notes\n")
    lines.append("- Correlational leaderboard data; A/B before trusting. This is the animal "
                 "lever RM-040 could not test (feature column was missing).")
    lines.append("- The existing committed agent runs exactly ONE goose; top ladder bots are "
                 "animal-saturated (median 14, max 35 in the 592-row summary sample).")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
