#!/usr/bin/env python3
"""
Error rates for the HT-updated Predicted FT total.

Residual = actual full-time total − predicted FT total.
Over 2.5 = actual total goals >= 3.

Question: when the residual is positive (we under-predicted goals),
how often did the match go over 2.5? When negative, how often under?
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_PREDICTIONS = (
    PROJECT_ROOT / "outputs" / "ht_score_predictions" / "ht_updated_score_predictions.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "ht_score_predictions"


def residual_bin(residual: float) -> str:
    if residual < -1.5:
        return "residual < -1.5 (well under pred)"
    if residual < -0.5:
        return "-1.5 to -0.5"
    if residual <= 0.5:
        return "-0.5 to +0.5 (near pred)"
    if residual <= 1.5:
        return "+0.5 to +1.5"
    return "residual > +1.5 (well over pred)"


BIN_ORDER = [
    "residual < -1.5 (well under pred)",
    "-1.5 to -0.5",
    "-0.5 to +0.5 (near pred)",
    "+0.5 to +1.5",
    "residual > +1.5 (well over pred)",
]


def scored_frame(predictions: pd.DataFrame) -> pd.DataFrame:
    frame = predictions.copy()
    frame["pred_total"] = frame["pred_ft_home"] + frame["pred_ft_away"]
    frame["actual_total"] = frame["actual_ft_home"] + frame["actual_ft_away"]
    frame["residual"] = frame["actual_total"] - frame["pred_total"]
    frame["went_over_2_5"] = frame["actual_total"] >= 3
    frame["went_under_2_5"] = frame["actual_total"] <= 2
    frame["pred_over_2_5"] = frame["pred_total"] > 2.5
    frame["residual_sign"] = pd.cut(
        frame["residual"],
        bins=[-float("inf"), -1e-9, 1e-9, float("inf")],
        labels=["negative", "zero", "positive"],
    )
    frame["residual_bin"] = frame["residual"].map(residual_bin)
    return frame


def sign_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for label, subset in (
        ("positive (actual > pred)", frame[frame["residual"] > 0]),
        ("negative (actual < pred)", frame[frame["residual"] < 0]),
        ("near zero (|resid| < 0.01)", frame[frame["residual"].abs() < 0.01]),
        ("all matches", frame),
    ):
        n = len(subset)
        if n == 0:
            continue
        over = int(subset["went_over_2_5"].sum())
        under = int(subset["went_under_2_5"].sum())
        rows.append(
            {
                "residual": label,
                "matches": n,
                "over_2_5": over,
                "under_2_5": under,
                "over_rate": round(over / n, 3),
                "under_rate": round(under / n, 3),
                "mean_actual_total": round(float(subset["actual_total"].mean()), 2),
                "mean_pred_total": round(float(subset["pred_total"].mean()), 2),
                "mean_residual": round(float(subset["residual"].mean()), 2),
            }
        )
    return pd.DataFrame(rows)


def bin_table(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        frame.groupby("residual_bin", as_index=False)
        .agg(
            matches=("residual", "size"),
            over_rate=("went_over_2_5", "mean"),
            under_rate=("went_under_2_5", "mean"),
            mean_actual_total=("actual_total", "mean"),
            mean_pred_total=("pred_total", "mean"),
        )
        .assign(residual_bin=lambda df: pd.Categorical(df["residual_bin"], BIN_ORDER, ordered=True))
        .sort_values("residual_bin")
    )
    grouped["over_rate"] = grouped["over_rate"].round(3)
    grouped["under_rate"] = grouped["under_rate"].round(3)
    grouped["mean_actual_total"] = grouped["mean_actual_total"].round(2)
    grouped["mean_pred_total"] = grouped["mean_pred_total"].round(2)
    return grouped


def predicted_line_table(frame: pd.DataFrame) -> pd.DataFrame:
    """If Predicted FT total is itself used as an over/under 2.5 call."""
    rows: list[dict] = []
    for label, subset, success_col in (
        ("pred total > 2.5 (call over)", frame[frame["pred_over_2_5"]], "went_over_2_5"),
        ("pred total <= 2.5 (call under)", frame[~frame["pred_over_2_5"]], "went_under_2_5"),
    ):
        n = len(subset)
        if n == 0:
            continue
        hits = int(subset[success_col].sum())
        rows.append(
            {
                "call": label,
                "matches": n,
                "hits": hits,
                "hit_rate": round(hits / n, 3),
                "mean_pred_total": round(float(subset["pred_total"].mean()), 2),
                "mean_actual_total": round(float(subset["actual_total"].mean()), 2),
            }
        )

    n = len(frame)
    correct = int(
        ((frame["pred_over_2_5"] & frame["went_over_2_5"])
         | (~frame["pred_over_2_5"] & frame["went_under_2_5"])).sum()
    )
    rows.append(
        {
            "call": "overall O/U 2.5 accuracy",
            "matches": n,
            "hits": correct,
            "hit_rate": round(correct / n, 3),
            "mean_pred_total": round(float(frame["pred_total"].mean()), 2),
            "mean_actual_total": round(float(frame["actual_total"].mean()), 2),
        }
    )
    return pd.DataFrame(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Over/under error rates from Predicted FT residual."
    )
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.predictions.exists():
        print(
            f"Missing {args.predictions}. Run: python3 scripts/ht_score_prediction.py"
        )
        return 1

    predictions = pd.read_csv(args.predictions, parse_dates=["date"])
    frame = scored_frame(predictions)
    by_sign = sign_table(frame)
    by_bin = bin_table(frame)
    by_call = predicted_line_table(frame)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output_dir / "prediction_residuals.csv", index=False)
    by_sign.to_csv(args.output_dir / "over_under_by_residual_sign.csv", index=False)
    by_bin.to_csv(args.output_dir / "over_under_by_residual_bin.csv", index=False)
    by_call.to_csv(args.output_dir / "over_under_call_accuracy.csv", index=False)

    mae = float(frame["residual"].abs().mean())
    bias = float(frame["residual"].mean())
    print("Residual = actual FT total − predicted FT total")
    print("Over 2.5 = actual total >= 3; under = actual total <= 2")
    print()
    print(f"Matches: {len(frame)}")
    print(f"Mean predicted total: {frame['pred_total'].mean():.2f}")
    print(f"Mean actual total:    {frame['actual_total'].mean():.2f}")
    print(f"Mean residual (bias): {bias:+.3f}")
    print(f"MAE of total goals:   {mae:.3f}")
    print()
    print("If residual is positive / negative, did the game go over 2.5?")
    print(by_sign.to_string(index=False))
    print()
    print("Same question by residual size:")
    print(by_bin.to_string(index=False))
    print()
    print("Using Predicted FT total as an over/under 2.5 call:")
    print(by_call.to_string(index=False))
    print()
    print(f"Saved tables -> {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
