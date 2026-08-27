#!/usr/bin/env python3
"""
HT volume residuals vs second-half goal over-performance.

1. Fit empirical regressions (train set): pregame odds -> expected HT shots/SOT/corners
2. Compute HT residuals = actual HT stat - expected HT stat
3. Fit pregame odds (+ HT score) -> expected 2H goals per team
4. Compute 2H goal residual = actual 2H goals - expected 2H goals
5. Correlate HT volume residuals with 2H goal residuals (test set)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from football_data.loader import load_epl_matches
from football_data.odds import add_fair_over_under, add_fair_probabilities
from football_data.team_names import normalize_team_name
from fotmob.period_stats import period_stats_dataframe

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "ht_residuals"
VOLUME_METRICS = ("shots", "shots_on_target", "corners")
HT_FORMULAS = {
    "shots": "ht_shots ~ fair_win + fair_over_2_5 + C(is_home)",
    "shots_on_target": "ht_shots_on_target ~ fair_win + fair_over_2_5 + C(is_home)",
    "corners": "ht_corners ~ fair_win + fair_over_2_5 + C(is_home)",
}
H2_GOALS_FORMULA = (
    "h2_goals ~ fair_win + fair_over_2_5 + ht_goals_for + ht_goals_against + C(is_home)"
)


def normalize_match_teams(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["home_team"] = result["home_team"].map(normalize_team_name)
    result["away_team"] = result["away_team"].map(normalize_team_name)
    return result


def join_fotmob_and_odds(
    fotmob: pd.DataFrame,
    odds: pd.DataFrame,
) -> pd.DataFrame:
    fotmob = normalize_match_teams(fotmob)
    odds = normalize_match_teams(odds)

    with_odds = add_fair_probabilities(odds, prefix="avg")
    with_odds = add_fair_over_under(with_odds)

    merged = fotmob.merge(
        with_odds,
        on=["date", "home_team", "away_team"],
        how="inner",
        suffixes=("", "_fd"),
    )
    return merged


def team_long_rows(matches: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for match in matches.itertuples(index=False):
        for is_home in (True, False):
            team = match.home_team if is_home else match.away_team
            opponent = match.away_team if is_home else match.home_team
            fair_win = match.fair_home if is_home else match.fair_away
            ht_goals_for = match.ht_home_goals if is_home else match.ht_away_goals
            ht_goals_against = match.ht_away_goals if is_home else match.ht_home_goals
            ft_goals_for = match.home_goals if is_home else match.away_goals
            ft_goals_against = match.away_goals if is_home else match.home_goals

            row = {
                "match_id": match.match_id,
                "date": match.date,
                "season": getattr(match, "season", None),
                "team": team,
                "opponent": opponent,
                "is_home": is_home,
                "fair_win": fair_win,
                "fair_draw": match.fair_draw,
                "fair_over_2_5": match.fair_over_2_5,
                "ht_goals_for": ht_goals_for,
                "ht_goals_against": ht_goals_against,
                "h2_goals": ft_goals_for - ht_goals_for,
                "ht_shots": match.ht_home_shots if is_home else match.ht_away_shots,
                "ht_shots_on_target": (
                    match.ht_home_shots_on_target if is_home else match.ht_away_shots_on_target
                ),
                "ht_corners": match.ht_home_corners if is_home else match.ht_away_corners,
            }
            rows.append(row)
    return pd.DataFrame(rows)


def fit_models(train: pd.DataFrame) -> dict[str, object]:
    models: dict[str, object] = {}
    for metric, formula in HT_FORMULAS.items():
        models[f"ht_{metric}"] = smf.ols(formula, data=train).fit()
    models["h2_goals"] = smf.ols(H2_GOALS_FORMULA, data=train).fit()
    return models


def add_residuals(frame: pd.DataFrame, models: dict[str, object]) -> pd.DataFrame:
    result = frame.copy()
    for metric in VOLUME_METRICS:
        model = models[f"ht_{metric}"]
        expected_col = f"expected_ht_{metric}"
        residual_col = f"ht_{metric}_residual"
        result[expected_col] = model.predict(result)
        result[residual_col] = result[f"ht_{metric}"] - result[expected_col]

    h2_model = models["h2_goals"]
    result["expected_h2_goals"] = h2_model.predict(result)
    result["h2_goals_residual"] = result["h2_goals"] - result["expected_h2_goals"]
    return result


def correlation_table(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    residual_cols = [f"ht_{metric}_residual" for metric in VOLUME_METRICS]
    target = "h2_goals_residual"
    rows: list[dict] = []
    for col in residual_cols:
        subset = frame[[col, target]].dropna()
        if len(subset) < 10:
            continue
        pearson = subset[col].corr(subset[target])
        spearman = subset[col].corr(subset[target], method="spearman")
        rows.append(
            {
                "subset": label,
                "ht_metric": col.replace("_residual", "").replace("ht_", ""),
                "n": len(subset),
                "pearson_r": round(float(pearson), 4),
                "spearman_r": round(float(spearman), 4),
            }
        )
    return pd.DataFrame(rows)


def model_summary_table(models: dict[str, object]) -> pd.DataFrame:
    rows: list[dict] = []
    for name, model in models.items():
        for term, coef in model.params.items():
            rows.append(
                {
                    "model": name,
                    "term": term,
                    "coef": round(float(coef), 4),
                    "std_err": round(float(model.bse[term]), 4),
                    "p_value": round(float(model.pvalues[term]), 4),
                }
            )
        rows.append(
            {
                "model": name,
                "term": "r_squared",
                "coef": round(float(model.rsquared), 4),
                "std_err": np.nan,
                "p_value": np.nan,
            }
        )
    return pd.DataFrame(rows)


def incremental_regression(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    """Does each HT volume residual predict 2H goal residual beyond HT goals?"""
    rows: list[dict] = []
    base_formula = "h2_goals_residual ~ ht_goals_for + ht_goals_against + C(is_home)"
    base_model = smf.ols(base_formula, data=frame).fit()

    for metric in VOLUME_METRICS:
        residual_col = f"ht_{metric}_residual"
        formula = f"{base_formula} + {residual_col}"
        model = smf.ols(formula, data=frame).fit()
        coef = model.params[residual_col]
        pval = model.pvalues[residual_col]
        rows.append(
            {
                "subset": label,
                "ht_metric": metric,
                "n": len(frame),
                "coef_on_h2_residual": round(float(coef), 4),
                "p_value": round(float(pval), 4),
                "r2_baseline": round(float(base_model.rsquared), 4),
                "r2_with_residual": round(float(model.rsquared), 4),
            }
        )
    return pd.DataFrame(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="HT volume residuals vs 2H goal over-performance."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--split-date",
        default="2026-01-01",
        help="Train on matches before this date; evaluate on/after (default: 2026-01-01)",
    )
    parser.add_argument("--refresh-data", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    split_date = pd.Timestamp(args.split_date)

    fotmob = period_stats_dataframe()
    if fotmob.empty:
        print("No FotMob cached matches found. Cache match JSON under data/fotmob/matches/.")
        return 1

    odds = load_epl_matches(refresh=args.refresh_data)
    matches = join_fotmob_and_odds(fotmob, odds)
    if matches.empty:
        print("No matches joined between FotMob and Football-Data odds.")
        return 1

    required = [
        "ht_home_shots",
        "ht_home_shots_on_target",
        "ht_home_corners",
        "ht_home_goals",
        "home_goals",
    ]
    matches = matches.dropna(subset=required).copy()
    team_rows = team_long_rows(matches)
    team_rows = team_rows.dropna(
        subset=["ht_shots", "ht_shots_on_target", "ht_corners", "h2_goals"]
    )

    train = team_rows[team_rows["date"] < split_date].copy()
    test = team_rows[team_rows["date"] >= split_date].copy()
    if len(train) < 50 or len(test) < 20:
        print(
            f"Insufficient train/test split (train={len(train)}, test={len(test)}). "
            "Adjust --split-date."
        )
        return 1

    models = fit_models(train)
    train_scored = add_residuals(train, models)
    test_scored = add_residuals(test, models)
    all_scored = add_residuals(team_rows, models)

    correlations_train = correlation_table(train_scored, "train")
    correlations_test = correlation_table(test_scored, "test")
    correlations_all = correlation_table(all_scored, "all")
    correlations = pd.concat(
        [correlations_train, correlations_test, correlations_all],
        ignore_index=True,
    )

    incremental_train = incremental_regression(train_scored, "train")
    incremental_test = incremental_regression(test_scored, "test")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    team_rows.to_csv(args.output_dir / "team_match_base.csv", index=False)
    train_scored.to_csv(args.output_dir / "train_with_residuals.csv", index=False)
    test_scored.to_csv(args.output_dir / "test_with_residuals.csv", index=False)
    all_scored.to_csv(args.output_dir / "all_with_residuals.csv", index=False)
    correlations.to_csv(args.output_dir / "correlations.csv", index=False)
    incremental_train.to_csv(args.output_dir / "incremental_regression_train.csv", index=False)
    incremental_test.to_csv(args.output_dir / "incremental_regression_test.csv", index=False)
    model_summary_table(models).to_csv(args.output_dir / "regression_models.csv", index=False)

    print(f"Joined matches: {len(matches)}")
    print(f"Team-match rows: {len(team_rows)} (train={len(train)}, test={len(test)})")
    print(f"Train dates: {train['date'].min().date()} – {train['date'].max().date()}")
    print(f"Test dates:  {test['date'].min().date()} – {test['date'].max().date()}")
    print()
    print("HT volume residual vs 2H goal residual correlations (TEST set):")
    test_corr = correlations[correlations["subset"] == "test"]
    if test_corr.empty:
        print("  (no test correlations)")
    else:
        print(test_corr.to_string(index=False))
    print()
    print("Incremental: 2H goal residual ~ HT goals + volume residual (TEST set):")
    print(incremental_test.to_string(index=False))
    print()
    print("Regression models (train fit):")
    summary = model_summary_table(models)
    print(summary[summary["term"] != "r_squared"].to_string(index=False))
    print()
    print(f"Saved outputs -> {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
