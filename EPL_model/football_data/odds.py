"""Helpers for converting bookmaker odds to probabilities."""

from __future__ import annotations

import pandas as pd


def add_fair_probabilities(frame: pd.DataFrame, prefix: str = "avg") -> pd.DataFrame:
    """Add vig-stripped implied probabilities from decimal odds columns."""
    home_col = f"{prefix}_home"
    draw_col = f"{prefix}_draw"
    away_col = f"{prefix}_away"

    required = {home_col, draw_col, away_col}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing odds columns: {sorted(missing)}")

    result = frame.dropna(subset=[home_col, draw_col, away_col]).copy()
    for side in ("home", "draw", "away"):
        result[f"implied_{side}"] = 1.0 / result[f"{prefix}_{side}"]
    total = result[["implied_home", "implied_draw", "implied_away"]].sum(axis=1)
    for side in ("home", "draw", "away"):
        result[f"fair_{side}"] = result[f"implied_{side}"] / total
    return result


def add_fair_over_under(
    frame: pd.DataFrame,
    over_col: str = "avg_over_2_5",
    under_col: str = "avg_under_2_5",
    fallback_over: str | None = "b365_over_2_5",
    fallback_under: str | None = "b365_under_2_5",
) -> pd.DataFrame:
    """Add vig-stripped fair probability of over 2.5 goals."""
    result = frame.copy()
    if over_col not in result.columns and fallback_over:
        result[over_col] = result.get(fallback_over)
    if under_col not in result.columns and fallback_under:
        result[under_col] = result.get(fallback_under)

    result = result.dropna(subset=[over_col, under_col]).copy()
    result["implied_over_2_5"] = 1.0 / result[over_col]
    result["implied_under_2_5"] = 1.0 / result[under_col]
    total = result["implied_over_2_5"] + result["implied_under_2_5"]
    result["fair_over_2_5"] = result["implied_over_2_5"] / total
    return result


def team_match_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """
    One row per team per match with that team's pregame win probability
    and in-match shooting/corner counts.
    """
    rows: list[dict] = []
    stat_pairs = (
        ("home_shots", "away_shots", "shots"),
        ("home_shots_on_target", "away_shots_on_target", "shots_on_target"),
        ("home_corners", "away_corners", "corners"),
    )

    for match in frame.itertuples(index=False):
        for is_home, win_prob, draw_prob in (
            (True, match.fair_home, match.fair_draw),
            (False, match.fair_away, match.fair_draw),
        ):
            team = match.home_team if is_home else match.away_team
            opponent = match.away_team if is_home else match.home_team
            row = {
                "season": match.season,
                "date": match.date,
                "team": team,
                "opponent": opponent,
                "is_home": is_home,
                "fair_win": win_prob,
                "fair_draw": draw_prob,
                "fair_loss": match.fair_home if not is_home else match.fair_away,
                "avg_home": match.avg_home,
                "avg_draw": match.avg_draw,
                "avg_away": match.avg_away,
            }
            for home_col, away_col, label in stat_pairs:
                value = getattr(match, home_col if is_home else away_col)
                row[label] = value
            rows.append(row)

    return pd.DataFrame(rows)


def win_probability_bin(probability: float) -> str:
    if probability < 0.25:
        return "0-25% (heavy underdog)"
    if probability < 0.40:
        return "25-40% (underdog)"
    if probability < 0.55:
        return "40-55% (balanced)"
    if probability < 0.70:
        return "55-70% (favorite)"
    return "70%+ (heavy favorite)"
