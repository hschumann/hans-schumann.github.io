#!/usr/bin/env python3
"""Train a Dixon-Coles baseline on Football-Data.co.uk EPL results."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from football_data.loader import load_epl_matches
from models.dixon_coles import evaluate_predictions, fit_dixon_coles, predict_matches

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "dixon_coles"


def split_train_test(
    matches: pd.DataFrame,
    test_season: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if test_season is None:
        test_season = matches["season"].dropna().iloc[-1]
    train = matches[matches["season"] != test_season].copy()
    test = matches[matches["season"] == test_season].copy()
    return train, test


def ratings_dataframe(model) -> pd.DataFrame:
    rows = []
    for team in model.teams:
        rows.append(
            {
                "team": team,
                "attack": round(model.attack[team], 4),
                "defense": round(model.defense[team], 4),
                "net": round(model.attack[team] - model.defense[team], 4),
            }
        )
    return pd.DataFrame(rows).sort_values("net", ascending=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train Dixon-Coles baseline on EPL goals.")
    parser.add_argument(
        "--test-season",
        default=None,
        help="Hold-out season label, e.g. 2024/25 (default: most recent season)",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    matches = load_epl_matches()
    completed = matches.dropna(subset=["home_goals", "away_goals"]).copy()

    train, test = split_train_test(completed, test_season=args.test_season)
    if train.empty or test.empty:
        print("Not enough seasons for train/test split.")
        return 1

    print(f"Training on {len(train)} matches ({train['season'].min()} – {train['season'].max()})")
    print(f"Evaluating on {len(test)} matches ({test['season'].iloc[0]})")

    model = fit_dixon_coles(train)
    metrics = evaluate_predictions(model, test)
    predictions = predict_matches(model, test)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ratings_dataframe(model).to_csv(args.output_dir / "team_ratings.csv", index=False)
    predictions.to_csv(args.output_dir / "test_predictions.csv", index=False)

    print()
    print("Model parameters")
    print(f"  intercept (log baseline rate): {model.intercept:.4f}")
    print(f"  home advantage (log):          {model.home_advantage:.4f}")
    print(f"  rho (low-score correction):    {model.rho:.4f}")
    print()
    print("Hold-out metrics")
    print(f"  log loss:    {metrics['log_loss']:.4f}")
    print(f"  Brier score: {metrics['brier_score']:.4f}")
    print()
    print(f"Saved team ratings -> {args.output_dir / 'team_ratings.csv'}")
    print(f"Saved predictions  -> {args.output_dir / 'test_predictions.csv'}")
    print()
    print("Top 5 teams by attack - defense:")
    print(ratings_dataframe(model).head().to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
