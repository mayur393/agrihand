#!/usr/bin/env python3
"""RM-040 — rating-controlled predictors of final_bank (dev-only analysis).

Separates real strategic signal from skill confound in the Kaggriculture
leaderboard dataset. A raw winner-vs-loser mean ("winners plant more wheat")
confounds skill with the lever: better bots do many things more, so a naive
group mean can look like causation when it is only a side effect of being good.

This script controls for skill three ways, in increasing sharpness:
  Model A  raw OLS              final_bank ~ predictors (no control)
  Model B  rating-controlled    final_bank ~ predictors + rating (post-game)
  Model C  ladder_score control final_bank ~ predictors + ladder_score (team snapshot)
  Model D  paired within-episode delta (winner-loser), controlling for delta-rating

Plus a within-rating-band winner-vs-loser check for the key predictor, so the
answer is not a single confounded coefficient but "does the lever hold once
skill is fixed?"

NOT part of the submission. Uses pandas/numpy (dev-only); reads the small
pre-extracted CSVs, never the 4GB parquet. Writes a markdown report to
reports/rm040_regression.md and prints a summary.

DEV-ONLY ANALYSIS ARTIFACT: never bundled, no runtime dependency created.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
REPO = HERE.parent
REPORT = REPO / "reports" / "rm040_regression.md"

# Predictors available in episode_features.csv. Each is a config-tunable lever
# or a proxy for one. Interpretations kept explicit below.
PREDICTORS = {
    "plants_wheat": "WHEAT planting volume (PLANT WHEAT actions)",
    "plants_melon": "MELON planting volume",
    "plants_strawberry": "STRAWBERRY planting volume",
    "plants_tomato": "TOMATO planting volume",
    "plants_carrot": "CARROT planting volume",
    "peak_crew": "largest simultaneous hands+farmer count",
    "total_hires": "sum of daily hires_today (post-hire farm state)",
    "first_land_day_filled": "first land-buy day (30 = never bought)",
    "no_land": "binary: never bought land",
    "crop_diversity": "number of distinct crops planted",
}


def _rating_col(seat: int) -> str:
    return f"rating_{seat}"


def _team_col(seat: int) -> str:
    return f"team_{seat}"


def build_rows(dataset: Path):
    eps = pd.read_csv(
        dataset / "episodes.csv",
        usecols=["episode_id", "type", "bank_0", "bank_1",
                 "rating_0", "rating_1", "team_0", "team_1"],
    )
    feat = pd.read_csv(dataset / "episode_features.csv")

    teams = pd.read_csv(dataset / "teams.csv", usecols=["team_id", "ladder_score"])

    eps = eps[eps["type"] == "EPISODE_TYPE_PUBLIC"].copy()

    feat_cols = ["episode_id", "peak_crew", "total_hires", "first_land_day",
                 "plants_wheat", "plants_melon", "plants_strawberry",
                 "plants_tomato", "plants_carrot"]

    rows = []
    for seat in (0, 1):
        f = feat[feat["seat"] == seat][feat_cols].copy()
        f = f.merge(eps, on="episode_id", how="inner")
        f["seat"] = seat
        f["final_bank"] = f[f"bank_{seat}"]
        f["rating"] = f[f"rating_{seat}"]
        f["team_id"] = f[f"team_{seat}"].astype(str)
        f = f.merge(teams.assign(team_id=teams["team_id"].astype(str)),
                    on="team_id", how="left")
        rows.append(f)

    out = pd.concat(rows, ignore_index=True)
    out["first_land_day_filled"] = out["first_land_day"].fillna(30.0)
    out["no_land"] = out["first_land_day"].isna().astype(int)
    crop_cols = [c for c in out.columns if c.startswith("plants_")]
    out["crop_diversity"] = (out[crop_cols] > 0).sum(axis=1)
    return out


def _winsorize(s: pd.Series, p=0.99) -> pd.Series:
    """Clip extreme tails so a max of 2096 wheat doesn't dominate OLS."""
    lo = s.quantile(1 - p)
    hi = s.quantile(p)
    return s.clip(lo, hi)


def _ols(y, X, names):
    """OLS via normal equations on standardized X; returns coefficient frame.

    Coefficients are per-1-SD-of-predictor change in final_bank ($).
    """
    Xz = (X - X.mean(axis=0)) / X.std(axis=0, ddof=0)
    Xd = np.column_stack([np.ones(len(y)), Xz])
    beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
    y_sd = y.std(ddof=0)
    out = []
    for i, name in enumerate(names):
        out.append({"predictor": name, "coef_per_sd": beta[i + 1]})
    return pd.DataFrame(out)


def run_models(rows):
    """Fit the four models; return a dict of name -> coefficient frame."""
    y = rows["final_bank"].to_numpy(dtype=float)
    base_preds = [p for p in PREDICTORS]
    # Winsorize the heavy-tailed count predictors before standardizing.
    X = np.column_stack([
        _winsorize(rows[p]).to_numpy(dtype=float) if p != "no_land" and p != "crop_diversity"
        else rows[p].to_numpy(dtype=float)
        for p in base_preds
    ])
    # no_land is already binary; crop_diversity small integer, leave raw.
    names = base_preds

    models = {"A_raw": _ols(y, X, names)}

    # B: control for post-game rating (endogeneity caveat: rating is updated BY
    # the outcome, so this may under-credit predictors; ladder_score in C is the
    # cleaner skill proxy).
    Xb = np.column_stack([X, rows["rating"].to_numpy(dtype=float)])
    models["B_rating_controlled"] = _ols(y, Xb, names + ["rating"])

    # C: control for team ladder_score (leaderboard snapshot; ~97% coverage).
    sub = rows[rows["ladder_score"].notna()].copy()
    Xc = np.column_stack([np.column_stack([
        _winsorize(sub[p]).to_numpy(dtype=float) if p != "no_land" and p != "crop_diversity"
        else sub[p].to_numpy(dtype=float) for p in base_preds
    ]), sub["ladder_score"].to_numpy(dtype=float)])
    models["C_ladder_score_controlled"] = _ols(
        sub["final_bank"].to_numpy(dtype=float), Xc, names + ["ladder_score"])

    return models


def within_band_check(rows):
    """Winner-vs-loser wheat volume within matched-rating quartiles.

    Bins each episode by its mean rating (both seats share it), then compares
    winner vs loser wheat within that band. If wheat volume is a real lever,
    the winner's advantage should persist (stay positive) across bands; if it
    collapses at the top band where skill is most matched, it was confound.
    """
    r = rows.copy()
    r["winner"] = r.groupby("episode_id")["final_bank"].transform("max") == r["final_bank"]
    # drop ties (both seats equal)
    tie = r.groupby("episode_id")["final_bank"].transform("nunique") < 2
    r = r[~tie].copy()
    r["band"] = pd.qcut(r.groupby("episode_id")["rating"].transform("mean"),
                        q=4, labels=["Q1", "Q2", "Q3", "Q4"])
    tab = r.pivot_table(index="band", columns="winner",
                        values="plants_wheat", aggfunc="mean")
    tab.columns = ["loser_wheat", "winner_wheat"]
    tab["delta"] = tab["winner_wheat"] - tab["loser_wheat"]
    tab["n"] = r.groupby("band").size()
    return tab


def paired_delta(rows):
    """Within-episode winner-loser deltas (STILL confounded — see note).

    Each episode is a matched pair (same opponent, shared market, same prices),
    so this controls the environment. But it does NOT control the within-pair
    skill gap: the winner is systematically higher-skill and therefore does
    MORE of everything (wheat, strawberry, crew, hires), so all deltas trend
    positive. Model C (ladder_score) is the cleaner control for the specific
    confound "good bots do more of everything"; this model is reported only as
    a robustness view of that same confound, not as clean evidence.
    """
    r = rows.copy()
    r["winner"] = r.groupby("episode_id")["final_bank"].transform("max") == r["final_bank"]
    tie = r.groupby("episode_id")["final_bank"].transform("nunique") < 2
    r = r[~tie].copy()

    w = r[r["winner"]][["episode_id", "final_bank", "rating", "plants_wheat",
                        "plants_melon", "plants_strawberry", "peak_crew",
                        "total_hires", "first_land_day_filled"]].copy()
    l = r[~r["winner"]][["episode_id", "final_bank", "rating", "plants_wheat",
                         "plants_melon", "plants_strawberry", "peak_crew",
                         "total_hires", "first_land_day_filled"]].copy()
    d = w.merge(l, on="episode_id", suffixes=("_w", "_l"))
    d["margin"] = d["final_bank_w"] - d["final_bank_l"]
    d["d_rating"] = d["rating_w"] - d["rating_l"]
    for p in ("plants_wheat", "plants_melon", "plants_strawberry",
              "peak_crew", "total_hires", "first_land_day_filled"):
        d[f"d_{p}"] = d[f"{p}_w"] - d[f"{p}_l"]

    y = d["margin"].to_numpy(dtype=float)
    dnames = ["d_plants_wheat", "d_plants_melon", "d_plants_strawberry",
              "d_peak_crew", "d_total_hires", "d_first_land_day_filled"]
    X = np.column_stack([_winsorize(d[n]).to_numpy(dtype=float) for n in dnames])
    # unstandardized but per-1-SD for comparability
    Xz = (X - X.mean(axis=0)) / X.std(axis=0, ddof=0)
    Xd = np.column_stack([np.ones(len(y)), Xz, d["d_rating"].to_numpy(dtype=float)])
    beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
    return d, dnames, beta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="/home/mayur/Projects/Dataset",
                    help="path to the dataset dir with episodes.csv + episode_features.csv")
    args = ap.parse_args()

    rows = build_rows(Path(args.dataset))
    print(f"rows: {len(rows)} seats, {rows.episode_id.nunique()} public episodes")

    # animal-count gap: honest note, not silently dropped
    print("NOTE: episode_features.csv has no animal-count column; animals are "
          "excluded from the full regression (only the 593-row summary.csv has "
          "max_animals). Flagged for a later parquet pass if needed.")

    models = run_models(rows)
    band = within_band_check(rows)
    d, dnames, beta = paired_delta(rows)

    lines = []
    lines.append("# RM-040 — Rating-controlled predictors of final_bank\n")
    lines.append(f"Seats: {len(rows)} | public episodes: {rows.episode_id.nunique()}\n")
    lines.append("Coefficients are **final_bank dollars per +1 SD** of the "
                 "predictor (continuous) or per binary flip (no_land).\n")
    lines.append("## Model comparison (does the lever survive skill control?)\n")
    lines.append("| predictor | A raw | B rating | C ladder_score |")
    lines.append("|---|---|---|---|")
    a = dict(zip(models["A_raw"].predictor, models["A_raw"].coef_per_sd))
    b = dict(zip(models["B_rating_controlled"].predictor, models["B_rating_controlled"].coef_per_sd))
    c = dict(zip(models["C_ladder_score_controlled"].predictor, models["C_ladder_score_controlled"].coef_per_sd))
    for p in PREDICTORS:
        lines.append(f"| {p} | {a.get(p, float('nan')):,.0f} | "
                     f"{b.get(p, float('nan')):,.0f} | {c.get(p, float('nan')):,.0f} |")
    lines.append(f"| rating (control) | — | {b.get('rating', float('nan')):,.0f} | — |")
    lines.append(f"| ladder_score (control) | — | — | {c.get('ladder_score', float('nan')):,.0f} |")
    lines.append("")
    lines.append("## Within-rating-band winner-vs-loser wheat volume\n")
    lines.append("| band | loser_wheat | winner_wheat | delta | n |")
    lines.append("|---|---|---|---|---|")
    for band_name, row in band.iterrows():
        lines.append(f"| {band_name} | {row.loser_wheat:,.1f} | {row.winner_wheat:,.1f} | "
                     f"{row.delta:,.1f} | {int(row.n)} |")
    lines.append("")
    lines.append("## Paired within-episode deltas (margin on delta, control d_rating)\n")
    lines.append("| predictor delta | coef_per_sd |")
    lines.append("|---|---|")
    for i, name in enumerate(dnames):
        lines.append(f"| {name} | {beta[i + 1]:,.0f} |")
    lines.append(f"| d_rating (control) | {beta[-1]:,.0f} |")
    lines.append("")
    lines.append("## Notes\n")
    lines.append("- `first_land_day_filled` uses 30 for 'never bought land'; "
                 "lower = earlier land = more season to use it.")
    lines.append("- Model B controls for **post-game** rating, which the outcome "
                 "itself updates — that is endogenous and can under-credit real "
                 "levers. Model C (ladder_score, a team snapshot not tied to this "
                 "game) is the cleaner skill control. Model D (paired delta) controls "
                 "the environment but NOT the within-pair skill gap — the winner is "
                 "systematically higher-skill, so its deltas trend positive on every "
                 "lever. Read D as a robustness view of the confound, not clean evidence.")
    lines.append("- Correlational from leaderboard data. None of this is a promotion; "
                 "each surviving lever needs its own self-play A/B (RM-041).")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")

    print(f"\nwrote {REPORT}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
