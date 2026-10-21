#!/usr/bin/env python3
"""Train multinomial logistic regression for home win / draw / loss."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict, deque
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.metrics import classification_report
from sklearn.preprocessing import StandardScaler
from statsmodels.discrete.discrete_model import MNLogit

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from statsbomb.config import DEFAULT_COMPETITION_ID, DEFAULT_SEASON_ID
from statsbomb.loader import extract_possessions, load_events, load_matches

ROLLING_GAMES = 6
FEATURE_COLUMNS = [
    "xg_margin_diff",
    "start_yards_diff",
    "opp_start_allowed_diff",
]
DEFAULT_TRAINING_OUTPUT = PROJECT_ROOT / "model_training_data.csv"
DEFAULT_PREDICTIONS_OUTPUT = PROJECT_ROOT / "model_predictions.csv"
DEFAULT_CURVE_PLOT = PROJECT_ROOT / "xg_vs_start_distance.png"
DEFAULT_COEFFICIENTS_OUTPUT = PROJECT_ROOT / "model_coefficients.csv"
RESULT_CATEGORIES = ["draw", "home_loss", "home_win"]


def match_result(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home_win"
    if home_score == away_score:
        return "draw"
    return "home_loss"


def compute_team_match_stats(
    possessions: list[dict],
    home_team: str,
    away_team: str,
) -> dict[str, dict[str, float]]:
    home_possessions = [p for p in possessions if p["possession_team"] == home_team]
    away_possessions = [p for p in possessions if p["possession_team"] == away_team]

    def average_yards(items: list[dict]) -> float:
        if not items:
            return np.nan
        return float(np.mean([item["yards_from_goal"] for item in items]))

    return {
        home_team: {
            "xg_for": float(sum(p["shot_xg"] for p in home_possessions)),
            "xg_against": float(sum(p["shot_xg"] for p in away_possessions)),
            "avg_start_yards": average_yards(home_possessions),
            "opp_start_allowed_yards": average_yards(away_possessions),
        },
        away_team: {
            "xg_for": float(sum(p["shot_xg"] for p in away_possessions)),
            "xg_against": float(sum(p["shot_xg"] for p in home_possessions)),
            "avg_start_yards": average_yards(away_possessions),
            "opp_start_allowed_yards": average_yards(home_possessions),
        },
    }


def fit_xg_curve(possessions_frame: pd.DataFrame) -> tuple[np.poly1d, pd.DataFrame]:
    """Fit xG vs start distance, excluding goal kicks and penalties."""
    curve_frame = possessions_frame.copy()
    curve_frame["zone_yards"] = (curve_frame["yards_from_goal"] // 5) * 5
    binned = (
        curve_frame.groupby("zone_yards", as_index=False)
        .agg(
            possessions=("match_id", "count"),
            avg_xg=("shot_xg", "mean"),
        )
        .sort_values("zone_yards")
    )

    coefficients = np.polyfit(binned["zone_yards"], binned["avg_xg"], deg=2)
    polynomial = np.poly1d(coefficients)
    binned["expected_xg"] = polynomial(binned["zone_yards"])
    return polynomial, binned


def rolling_average(values: deque[float]) -> float:
    clean = [value for value in values if not np.isnan(value)]
    if not clean:
        return np.nan
    return float(np.mean(clean))


def build_match_dataset(
    matches: list[dict],
    possessions_frame: pd.DataFrame,
    rolling_games: int,
) -> pd.DataFrame:
    league_avg_xg = possessions_frame.groupby("match_id")["shot_xg"].sum().mean() / 2

    team_history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=rolling_games))
    team_start_history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=rolling_games))
    team_allowed_history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=rolling_games))

    rows: list[dict] = []
    ordered_matches = sorted(matches, key=lambda match: match["match_date"])

    for match in ordered_matches:
        match_id = int(match["match_id"])
        home_team = match["home_team"]["home_team_name"]
        away_team = match["away_team"]["away_team_name"]
        home_score = int(match["home_score"])
        away_score = int(match["away_score"])

        home_roll_xg = rolling_average(team_history[home_team])
        away_roll_xg = rolling_average(team_history[away_team])
        home_roll_start = rolling_average(team_start_history[home_team])
        away_roll_start = rolling_average(team_start_history[away_team])
        home_roll_allowed = rolling_average(team_allowed_history[home_team])
        away_roll_allowed = rolling_average(team_allowed_history[away_team])

        if len(team_history[home_team]) >= rolling_games and len(team_history[away_team]) >= rolling_games:
            home_xg_vs_avg = home_roll_xg - league_avg_xg
            away_xg_vs_avg = away_roll_xg - league_avg_xg
            rows.append(
                {
                    "match_id": match_id,
                    "match_date": match["match_date"],
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_score": home_score,
                    "away_score": away_score,
                    "result": match_result(home_score, away_score),
                    "xg_margin_diff": home_xg_vs_avg - away_xg_vs_avg,
                    "start_yards_diff": home_roll_start - away_roll_start,
                    "opp_start_allowed_diff": home_roll_allowed - away_roll_allowed,
                }
            )

        match_possessions = possessions_frame[possessions_frame["match_id"] == match_id]
        if match_possessions.empty:
            continue

        possessions = match_possessions.to_dict("records")
        team_stats = compute_team_match_stats(possessions, home_team, away_team)

        for team_name, stats in team_stats.items():
            team_history[team_name].append(stats["xg_for"])
            team_start_history[team_name].append(stats["avg_start_yards"])
            team_allowed_history[team_name].append(stats["opp_start_allowed_yards"])

    return pd.DataFrame(rows)


def plot_xg_curve(binned: pd.DataFrame, polynomial: np.poly1d, output_path: Path) -> None:
    yards = np.linspace(0, 105, 200)
    expected = polynomial(yards)

    plt.figure(figsize=(10, 6))
    plt.scatter(
        binned["zone_yards"],
        binned["avg_xg"],
        s=binned["possessions"] / 10,
        alpha=0.7,
        label="Observed avg xG per possession (5-yard bins)",
    )
    plt.plot(yards, expected, color="crimson", linewidth=2, label="Fitted xG curve")
    plt.xlabel("Starting distance from opponent goal (yards)")
    plt.ylabel("Average xG per possession")
    plt.title("Possession xG vs starting field position (excludes goal kicks & penalties)")
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def train_model(
    frame: pd.DataFrame,
) -> tuple[object, StandardScaler, pd.DataFrame, pd.DataFrame]:
    model_frame = frame.dropna(subset=FEATURE_COLUMNS).copy()
    features = model_frame[FEATURE_COLUMNS]
    target = pd.Categorical(
        model_frame["result"],
        categories=RESULT_CATEGORIES,
        ordered=True,
    )

    scaler = StandardScaler()
    scaled = scaler.fit_transform(features)
    scaled_frame = pd.DataFrame(scaled, columns=FEATURE_COLUMNS, index=model_frame.index)
    design_matrix = sm.add_constant(scaled_frame, has_constant="add")

    logit_model = MNLogit(target.codes, design_matrix)
    result = logit_model.fit(method="lbfgs", maxiter=2000, disp=False)

    probabilities = np.asarray(result.predict(design_matrix))
    prediction_frame = model_frame.copy()
    prediction_frame["prob_draw"] = probabilities[:, 0]
    prediction_frame["prob_home_loss"] = probabilities[:, 1]
    prediction_frame["prob_home_win"] = probabilities[:, 2]
    prediction_frame["predicted_result"] = pd.Series(
        np.asarray(RESULT_CATEGORIES)[np.argmax(probabilities, axis=1)],
        index=model_frame.index,
    )
    probability_columns = ["prob_home_win", "prob_draw", "prob_home_loss"]
    other_columns = [column for column in prediction_frame.columns if column not in probability_columns]
    prediction_frame = prediction_frame[other_columns + probability_columns]

    params = np.asarray(result.params)
    bse = np.asarray(result.bse)
    tvalues = np.asarray(result.tvalues)
    pvalues = np.asarray(result.pvalues)

    coefficient_rows: list[dict[str, float | str]] = []
    parameter_names = ["const", *FEATURE_COLUMNS]
    for outcome_index, outcome_name in enumerate(RESULT_CATEGORIES[1:]):
        for parameter_index, parameter_name in enumerate(parameter_names):
            coefficient_rows.append(
                {
                    "outcome": outcome_name,
                    "reference": RESULT_CATEGORIES[0],
                    "variable": parameter_name,
                    "coef": params[parameter_index, outcome_index],
                    "std_err": bse[parameter_index, outcome_index],
                    "z": tvalues[parameter_index, outcome_index],
                    "p_value": pvalues[parameter_index, outcome_index],
                }
            )

    coefficients_frame = pd.DataFrame(coefficient_rows)
    return result, scaler, prediction_frame, coefficients_frame


def print_model_summary(result: object, coefficients_frame: pd.DataFrame) -> None:
    print("\nModel C — multinomial logistic regression (reference outcome: draw)")
    print("Features: xg_margin_diff, start_yards_diff, opp_start_allowed_diff (standardized).\n")
    print(result.summary())

    print("\nCoefficient table:")
    printable = coefficients_frame.copy()
    printable["coef"] = printable["coef"].map(lambda value: f"{value:+.4f}")
    printable["std_err"] = printable["std_err"].map(lambda value: f"{value:.4f}")
    printable["z"] = printable["z"].map(lambda value: f"{value:+.3f}")
    printable["p_value"] = printable["p_value"].map(lambda value: f"{value:.4f}")
    print(printable.to_string(index=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train home result logistic regression model.")
    parser.add_argument("--competition-id", type=int, default=DEFAULT_COMPETITION_ID)
    parser.add_argument("--season-id", type=int, default=DEFAULT_SEASON_ID)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--rolling-games", type=int, default=ROLLING_GAMES)
    parser.add_argument("--training-output", type=Path, default=DEFAULT_TRAINING_OUTPUT)
    parser.add_argument("--predictions-output", type=Path, default=DEFAULT_PREDICTIONS_OUTPUT)
    parser.add_argument("--curve-plot", type=Path, default=DEFAULT_CURVE_PLOT)
    parser.add_argument("--coefficients-output", type=Path, default=DEFAULT_COEFFICIENTS_OUTPUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    matches = load_matches(args.competition_id, args.season_id)
    matches = sorted(matches, key=lambda match: match["match_date"])
    if args.limit is not None:
        matches = matches[: args.limit]

    print(f"Processing {len(matches)} matches...")
    all_possessions: list[dict] = []
    for index, match in enumerate(matches, start=1):
        match_id = int(match["match_id"])
        print(f"[{index}/{len(matches)}] match {match_id}", flush=True)
        events = load_events(match_id)
        all_possessions.extend(extract_possessions(events, match_id))

    possessions_frame = pd.DataFrame(all_possessions)
    polynomial, binned_curve = fit_xg_curve(possessions_frame)

    training_frame = build_match_dataset(
        matches=matches,
        possessions_frame=possessions_frame,
        rolling_games=args.rolling_games,
    )

    if training_frame.empty:
        print("Not enough rolling-window history to build a training set.")
        return 1

    result, scaler, prediction_frame, coefficients_frame = train_model(training_frame)
    plot_xg_curve(binned_curve, polynomial, args.curve_plot)

    training_frame.to_csv(args.training_output, index=False)
    prediction_frame.to_csv(args.predictions_output, index=False)
    coefficients_frame.to_csv(args.coefficients_output, index=False)

    print(f"\nTraining rows: {len(training_frame)}")
    print(f"Saved training data -> {args.training_output}")
    print(f"Saved predictions -> {args.predictions_output}")
    print(f"Saved coefficients -> {args.coefficients_output}")
    print(f"Saved xG curve plot -> {args.curve_plot}")
    print_model_summary(result, coefficients_frame)
    print(classification_report(prediction_frame["result"], prediction_frame["predicted_result"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
