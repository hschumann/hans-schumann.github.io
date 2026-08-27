#!/usr/bin/env python3
"""Explore shots, SOT, and corners vs pregame 1X2 odds."""

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
from football_data.odds import add_fair_probabilities, team_match_rows, win_probability_bin

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "odds_vs_stats"
STAT_COLUMNS = ("shots", "shots_on_target", "corners")
BIN_ORDER = [
    "0-25% (heavy underdog)",
    "25-40% (underdog)",
    "40-55% (balanced)",
    "55-70% (favorite)",
    "70%+ (heavy favorite)",
]


def analysis_frame(matches: pd.DataFrame) -> pd.DataFrame:
    """Completed matches with average-market odds and post-match volume stats."""
    with_odds = add_fair_probabilities(matches, prefix="avg")
    complete = with_odds.dropna(
        subset=[
            "home_goals",
            "home_shots",
            "home_shots_on_target",
            "home_corners",
            "away_shots",
            "away_shots_on_target",
            "away_corners",
        ]
    ).copy()
    complete["total_shots"] = complete["home_shots"] + complete["away_shots"]
    complete["total_shots_on_target"] = (
        complete["home_shots_on_target"] + complete["away_shots_on_target"]
    )
    complete["total_corners"] = complete["home_corners"] + complete["away_corners"]
    complete["home_win_prob_gap"] = complete["fair_home"] - complete["fair_away"]
    return complete


def summarize_by_win_probability(team_rows: pd.DataFrame) -> pd.DataFrame:
    grouped = team_rows.copy()
    grouped["win_prob_bin"] = grouped["fair_win"].map(win_probability_bin)

    summary = (
        grouped.groupby("win_prob_bin", as_index=False)
        .agg(
            team_matches=("fair_win", "size"),
            avg_fair_win=("fair_win", "mean"),
            avg_shots=("shots", "mean"),
            avg_shots_on_target=("shots_on_target", "mean"),
            avg_corners=("corners", "mean"),
            median_shots=("shots", "median"),
            median_shots_on_target=("shots_on_target", "median"),
            median_corners=("corners", "median"),
        )
        .assign(win_prob_bin=lambda frame: pd.Categorical(frame["win_prob_bin"], BIN_ORDER, ordered=True))
        .sort_values("win_prob_bin")
    )

    for column in ("avg_fair_win", "avg_shots", "avg_shots_on_target", "avg_corners"):
        summary[column] = summary[column].round(2)
    return summary


def summarize_match_totals(matches: pd.DataFrame) -> pd.DataFrame:
    frame = matches.copy()
    frame["home_prob_bin"] = frame["fair_home"].map(win_probability_bin)

    summary = (
        frame.groupby("home_prob_bin", as_index=False)
        .agg(
            matches=("fair_home", "size"),
            avg_fair_home=("fair_home", "mean"),
            avg_total_shots=("total_shots", "mean"),
            avg_total_shots_on_target=("total_shots_on_target", "mean"),
            avg_total_corners=("total_corners", "mean"),
            avg_home_shots=("home_shots", "mean"),
            avg_away_shots=("away_shots", "mean"),
            avg_home_corners=("home_corners", "mean"),
            avg_away_corners=("away_corners", "mean"),
        )
        .assign(home_prob_bin=lambda df: pd.Categorical(df["home_prob_bin"], BIN_ORDER, ordered=True))
        .sort_values("home_prob_bin")
    )
    for column in summary.columns:
        if column.startswith("avg_"):
            summary[column] = summary[column].round(2)
    return summary


def fit_regressions(team_rows: pd.DataFrame) -> pd.DataFrame:
    """Linear models: team stat counts ~ fair win probability + home indicator."""
    rows: list[dict] = []
    for stat in STAT_COLUMNS:
        model = smf.ols(
            f"{stat} ~ fair_win + C(is_home)",
            data=team_rows,
        ).fit()
        for name, coef in model.params.items():
            rows.append(
                {
                    "dependent": stat,
                    "term": name,
                    "coef": round(float(coef), 4),
                    "std_err": round(float(model.bse[name]), 4),
                    "p_value": round(float(model.pvalues[name]), 4),
                }
            )
        rows.append(
            {
                "dependent": stat,
                "term": "r_squared",
                "coef": round(float(model.rsquared), 4),
                "std_err": np.nan,
                "p_value": np.nan,
            }
        )
    return pd.DataFrame(rows)


def expected_stat_curve(
    team_rows: pd.DataFrame,
    regression: pd.DataFrame,
    stat: str,
) -> pd.DataFrame:
    """Predicted stat for home/away teams across the win-probability grid."""
    params = regression[(regression["dependent"] == stat) & (regression["term"] != "r_squared")]
    intercept = float(params.loc[params["term"] == "Intercept", "coef"].iloc[0])
    win_coef = float(params.loc[params["term"] == "fair_win", "coef"].iloc[0])
    home_coef = float(params.loc[params["term"] == "C(is_home)[T.True]", "coef"].iloc[0])

    grid = np.linspace(0.10, 0.85, 16)
    rows: list[dict] = []
    for probability in grid:
        for is_home, label in ((True, "home"), (False, "away")):
            expected = intercept + win_coef * probability + (home_coef if is_home else 0.0)
            rows.append(
                {
                    "stat": stat,
                    "side": label,
                    "fair_win": round(float(probability), 3),
                    "expected_count": round(float(expected), 2),
                }
            )
    return pd.DataFrame(rows)


def plot_expected_curves(curves: pd.DataFrame, output_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), sharex=True)
    titles = {
        "shots": "Shots",
        "shots_on_target": "Shots on target",
        "corners": "Corners",
    }

    for axis, stat in zip(axes, STAT_COLUMNS):
        subset = curves[curves["stat"] == stat]
        for side, color in (("home", "#1f77b4"), ("away", "#ff7f0e")):
            line = subset[subset["side"] == side]
            axis.plot(line["fair_win"], line["expected_count"], marker="o", label=side.title(), color=color)
        axis.set_title(titles[stat])
        axis.set_xlabel("Pregame fair win probability")
        axis.set_ylabel("Expected count")
        axis.grid(alpha=0.3)
        axis.legend()

    fig.suptitle("Expected volume stats vs pregame win probability (2019/20–2025/26)", y=1.02)
    fig.tight_layout()
    fig.savefig(output_dir / "expected_stats_vs_win_prob.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_bin_summary(summary: pd.DataFrame, output_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = np.arange(len(summary))
    width = 0.25
    fig, axis = plt.subplots(figsize=(10, 5))
    axis.bar(x - width, summary["avg_shots"], width, label="Shots")
    axis.bar(x, summary["avg_shots_on_target"], width, label="Shots on target")
    axis.bar(x + width, summary["avg_corners"], width, label="Corners")
    axis.set_xticks(x)
    axis.set_xticklabels(summary["win_prob_bin"], rotation=20, ha="right")
    axis.set_ylabel("Average per team-match")
    axis.set_title("Volume stats by pregame win-probability bin")
    axis.legend()
    axis.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_dir / "stats_by_win_prob_bin.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def print_summary(
    matches: pd.DataFrame,
    team_rows: pd.DataFrame,
    bin_summary: pd.DataFrame,
    regression: pd.DataFrame,
) -> None:
    print(f"Matches with odds + volume stats: {len(matches):,}")
    print(f"Team-match rows: {len(team_rows):,}")
    print(f"Seasons: {matches['season'].min()} – {matches['season'].max()}")
    print()
    print("Average stats by pregame win-probability bin (team perspective):")
    print(bin_summary.to_string(index=False))
    print()
    print("Regression: stat ~ fair_win + home indicator")
    printable = regression[regression["term"] != "r_squared"].copy()
    print(printable.to_string(index=False))
    print()
    for stat in STAT_COLUMNS:
        r2 = regression[(regression["dependent"] == stat) & (regression["term"] == "r_squared")]["coef"].iloc[0]
        win_coef = regression[
            (regression["dependent"] == stat) & (regression["term"] == "fair_win")
        ]["coef"].iloc[0]
        print(
            f"  {stat}: +{win_coef * 10:.2f} per 10pp win prob "
            f"(+{win_coef:.1f} from 0% to 100%, R²={r2:.3f})"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Explore shots, SOT, and corners vs pregame average-market 1X2 odds."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--refresh-data", action="store_true", help="Rebuild epl_matches.csv first")
    parser.add_argument("--no-plots", action="store_true", help="Skip chart generation")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    matches = load_epl_matches(refresh=args.refresh_data)
    frame = analysis_frame(matches)
    team_rows = team_match_rows(frame)

    bin_summary = summarize_by_win_probability(team_rows)
    match_summary = summarize_match_totals(frame)
    regression = fit_regressions(team_rows)

    curves = pd.concat(
        [expected_stat_curve(team_rows, regression, stat) for stat in STAT_COLUMNS],
        ignore_index=True,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    bin_summary.to_csv(args.output_dir / "stats_by_win_prob_bin.csv", index=False)
    match_summary.to_csv(args.output_dir / "match_totals_by_home_win_prob.csv", index=False)
    regression.to_csv(args.output_dir / "regression_coefficients.csv", index=False)
    curves.to_csv(args.output_dir / "expected_stat_curves.csv", index=False)
    team_rows.to_csv(args.output_dir / "team_match_rows.csv", index=False)

    if not args.no_plots:
        plot_expected_curves(curves, args.output_dir)
        plot_bin_summary(bin_summary, args.output_dir)

    print_summary(frame, team_rows, bin_summary, regression)
    print()
    suffix = "CSVs and plots" if not args.no_plots else "CSVs"
    print(f"Saved {suffix} -> {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
