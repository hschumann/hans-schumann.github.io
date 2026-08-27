#!/usr/bin/env python3
"""Halftime-updated final-score mock from pregame odds + HT score."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from football_data.loader import load_epl_matches
from football_data.odds import add_fair_over_under, add_fair_probabilities
from models.odds_half_goals import (
    DEFAULT_FIRST_HALF_SHARE,
    expected_goals_from_odds,
    predicted_final_from_halftime,
)

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "ht_score_predictions"

FORMULA_TEXT = """
Formulas (independent Poisson; no Dixon–Coles ρ)

1. Fair odds (remove overround / vig)
   p_H = (1/AvgH) / (1/AvgH + 1/AvgD + 1/AvgA)
   p_over = (1/Avg>2.5) / (1/Avg>2.5 + 1/Avg<2.5)

2. Expected total goals λ from the O/U
   If total goals ~ Poisson(λ):
     P(over 2.5) = 1 − e^{−λ} (1 + λ + λ²/2)
   Invert that equation for λ.

3. Split λ into team full-time rates
   μ_home + μ_away = λ
   Choose s so μ_home = sλ, μ_away = (1−s)λ
   and Poisson P(home win) ≈ p_H.

4. Split each team’s rate into halves (not 50/50)
   Historical EPL 2015/16–2025/26: {share_1h:.1%} of goals in 1H,
   so {share_2h:.1%} in 2H.
   E[1H home] = μ_home × {share_1h:.4f}
   E[2H home] = μ_home × {share_2h:.4f}
   (same for away)

5. Mock final at halftime
   Because Poisson halves are independent, the 1H score does not
   change the remaining 2H mean. It only shifts the final by what
   already happened:
   pred_FT_home = HT_home + E[2H home]
   pred_FT_away = HT_away + E[2H away]
""".strip()


def predict_matches(
    matches: pd.DataFrame,
    first_half_share: float,
) -> pd.DataFrame:
    rows: list[dict] = []
    for match in matches.itertuples(index=False):
        expected = expected_goals_from_odds(
            fair_home=match.fair_home,
            fair_over_2_5=match.fair_over_2_5,
            first_half_share=first_half_share,
        )
        pred_home, pred_away = predicted_final_from_halftime(
            match.ht_home_goals,
            match.ht_away_goals,
            expected["expected_2h_home"],
            expected["expected_2h_away"],
        )
        rows.append(
            {
                "date": match.date,
                "season": match.season,
                "home_team": match.home_team,
                "away_team": match.away_team,
                "fair_home": round(float(match.fair_home), 3),
                "fair_draw": round(float(match.fair_draw), 3),
                "fair_away": round(float(match.fair_away), 3),
                "fair_over_2_5": round(float(match.fair_over_2_5), 3),
                "lambda_total": round(expected["expected_total_goals"], 3),
                "mu_home": round(expected["expected_home_goals"], 3),
                "mu_away": round(expected["expected_away_goals"], 3),
                "expected_1h_home": round(expected["expected_1h_home"], 3),
                "expected_1h_away": round(expected["expected_1h_away"], 3),
                "expected_2h_home": round(expected["expected_2h_home"], 3),
                "expected_2h_away": round(expected["expected_2h_away"], 3),
                "ht_home": int(match.ht_home_goals),
                "ht_away": int(match.ht_away_goals),
                "pred_ft_home": round(pred_home, 3),
                "pred_ft_away": round(pred_away, 3),
                "actual_ft_home": int(match.home_goals),
                "actual_ft_away": int(match.away_goals),
            }
        )
    return pd.DataFrame(rows)


def print_preview(predictions: pd.DataFrame, n: int = 12) -> None:
    preview = predictions.head(n)
    print("First matches (HT score → predicted FT vs actual FT):")
    print()
    for row in preview.itertuples(index=False):
        print(
            f"{pd.Timestamp(row.date).date()}  "
            f"{row.home_team} {row.ht_home}-{row.ht_away} {row.away_team}  HT  |  "
            f"pred FT {row.pred_ft_home:.2f}-{row.pred_ft_away:.2f}  |  "
            f"actual {row.actual_ft_home}-{row.actual_ft_away}  |  "
            f"E[1H] {row.expected_1h_home:.2f}-{row.expected_1h_away:.2f}  "
            f"E[2H] {row.expected_2h_home:.2f}-{row.expected_2h_away:.2f}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Predict FT score from HT score + pregame 1X2 and O/U odds."
    )
    parser.add_argument("--season", default="2025/26")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--first-half-share",
        type=float,
        default=DEFAULT_FIRST_HALF_SHARE,
        help="Share of expected goals assigned to the first half (default: 0.4452)",
    )
    parser.add_argument("--refresh-data", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    matches = load_epl_matches(refresh=args.refresh_data)
    matches = add_fair_probabilities(matches, prefix="avg")
    matches = add_fair_over_under(matches)
    matches = matches.dropna(
        subset=["home_goals", "away_goals", "ht_home_goals", "ht_away_goals"]
    )
    if args.season:
        matches = matches[matches["season"] == args.season].copy()
    if matches.empty:
        print(f"No matches for season {args.season} with odds and HT scores.")
        return 1

    predictions = predict_matches(matches, first_half_share=args.first_half_share)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "ht_updated_score_predictions.csv"
    predictions.to_csv(output_path, index=False)

    home_err = (predictions["pred_ft_home"] - predictions["actual_ft_home"]).abs().mean()
    away_err = (predictions["pred_ft_away"] - predictions["actual_ft_away"]).abs().mean()

    print(
        FORMULA_TEXT.replace("{share_1h:.1%}", f"{args.first_half_share:.1%}")
        .replace("{share_2h:.1%}", f"{1.0 - args.first_half_share:.1%}")
        .replace("{share_1h:.4f}", f"{args.first_half_share:.4f}")
        .replace("{share_2h:.4f}", f"{1.0 - args.first_half_share:.4f}")
    )
    print()
    print(f"Season {args.season}: {len(predictions)} matches")
    print(f"Mean |pred − actual| home goals: {home_err:.3f}")
    print(f"Mean |pred − actual| away goals: {away_err:.3f}")
    print()
    print_preview(predictions)
    print()
    print(f"Saved all rows -> {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
