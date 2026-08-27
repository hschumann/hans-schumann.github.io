#!/usr/bin/env python3
"""Exploratory summary of Football-Data.co.uk Premier League data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from football_data.columns import COLUMN_GROUPS, PREMATCH_COLUMNS, POSTMATCH_COLUMNS
from football_data.loader import load_epl_matches

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "eda"


def implied_probabilities(frame: pd.DataFrame) -> pd.DataFrame:
    odds = frame.dropna(subset=["avg_home", "avg_draw", "avg_away"]).copy()
    for side in ("home", "draw", "away"):
        odds[f"implied_{side}"] = 1.0 / odds[f"avg_{side}"]
    total = odds[["implied_home", "implied_draw", "implied_away"]].sum(axis=1)
    for side in ("home", "draw", "away"):
        odds[f"fair_{side}"] = odds[f"implied_{side}"] / total
    return odds


def season_summary(matches: pd.DataFrame) -> pd.DataFrame:
    completed = matches.dropna(subset=["home_goals", "away_goals"]).copy()
    completed["total_goals"] = completed["home_goals"] + completed["away_goals"]
    completed["home_win"] = completed["result"] == "H"
    completed["draw"] = completed["result"] == "D"
    completed["away_win"] = completed["result"] == "A"

    summary = (
        completed.groupby("season", as_index=False)
        .agg(
            matches=("home_goals", "size"),
            avg_total_goals=("total_goals", "mean"),
            home_win_rate=("home_win", "mean"),
            draw_rate=("draw", "mean"),
            away_win_rate=("away_win", "mean"),
            avg_home_goals=("home_goals", "mean"),
            avg_away_goals=("away_goals", "mean"),
        )
        .sort_values("season")
    )
    for column in ("home_win_rate", "draw_rate", "away_win_rate"):
        summary[column] = (summary[column] * 100).round(1)
    for column in ("avg_total_goals", "avg_home_goals", "avg_away_goals"):
        summary[column] = summary[column].round(2)
    return summary


def goal_distribution(matches: pd.DataFrame) -> pd.DataFrame:
    completed = matches.dropna(subset=["home_goals", "away_goals"]).copy()
    counts = completed.groupby(["home_goals", "away_goals"]).size().reset_index(name="matches")
    total = counts["matches"].sum()
    counts["share_pct"] = (counts["matches"] / total * 100).round(2)
    return counts.sort_values(["home_goals", "away_goals"])


def missingness_report(matches: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in matches.columns:
        missing = matches[column].isna().sum()
        rows.append(
            {
                "column": column,
                "missing": int(missing),
                "missing_pct": round(missing / len(matches) * 100, 1),
            }
        )
    return pd.DataFrame(rows).sort_values("missing_pct", ascending=False)


def print_column_guide() -> None:
    print("Football-Data.co.uk variable availability\n")
    print("PRE-MATCH (usable before kickoff for prediction / fixtures.csv):")
    for name in PREMATCH_COLUMNS:
        print(f"  - {name}")
    print("  - All bookmaker odds columns (1X2, over/under, Asian handicap)")
    print("  - Closing odds use the same names with a trailing C (e.g. B365CH)\n")

    print("POST-MATCH ONLY (historical results file after full time):")
    for name in POSTMATCH_COLUMNS:
        print(f"  - {name}")
    print()

    print("Column groups documented in football_data/columns.py:")
    for group_name in COLUMN_GROUPS:
        print(f"  - {group_name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EDA summary for EPL Football-Data.co.uk data.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--columns", action="store_true", help="Print pre/post-match column guide")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.columns:
        print_column_guide()
        return 0

    matches = load_epl_matches()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    season = season_summary(matches)
    goals = goal_distribution(matches)
    missing = missingness_report(matches)
    odds = implied_probabilities(matches)

    season.to_csv(args.output_dir / "season_summary.csv", index=False)
    goals.to_csv(args.output_dir / "goal_distribution.csv", index=False)
    missing.to_csv(args.output_dir / "missingness.csv", index=False)
    odds[
        [
            "season",
            "date",
            "home_team",
            "away_team",
            "result",
            "avg_home",
            "avg_draw",
            "avg_away",
            "fair_home",
            "fair_draw",
            "fair_away",
        ]
    ].to_csv(args.output_dir / "market_probabilities.csv", index=False)

    print(f"Loaded {len(matches)} EPL matches across {matches['season'].nunique()} seasons")
    print(f"Date range: {matches['date'].min().date()} to {matches['date'].max().date()}")
    print()
    print("Season summary:")
    print(season.to_string(index=False))
    print()
    print("Most common scorelines:")
    print(goals.sort_values("matches", ascending=False).head(10).to_string(index=False))
    print()
    print(f"Saved EDA outputs -> {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
