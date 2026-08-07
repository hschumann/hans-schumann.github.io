"""Shared helpers for FotMob match and shot extraction."""

from __future__ import annotations

from typing import Any


PREMIER_LEAGUE_ID = 47
DEFAULT_SEASON = "2025/2026"
DEFAULT_MAX_GAMEWEEK = 4
GW4_CUTOFF_DATE = "2025-09-14"


def parse_season_arg(season: str) -> str:
    """Convert '2025-26' or '2025/2026' to FotMob's season format."""
    season = season.strip()
    if "/" in season:
        return season
    if "-" in season:
        start, end = season.split("-", 1)
        if len(end) == 2:
            return f"{start}/20{end}"
    return season


def extract_momentum_totals(momentum: dict[str, Any] | None) -> tuple[float, float] | None:
    """
    FotMob momentum is minute-by-minute and relative to the home team:
    positive values favor the home team, negative values favor the away team.
    """
    points = (momentum or {}).get("main", {}).get("data", [])
    if not points:
        return None

    home_total = sum(point["value"] for point in points if point["value"] > 0)
    away_total = sum(-point["value"] for point in points if point["value"] < 0)
    return home_total, away_total


def is_penalty_shot(shot: dict[str, Any]) -> bool:
    situation = str(shot.get("situation", "")).lower()
    if situation == "penalty":
        return True

    event_type = str(shot.get("eventType", "")).lower()
    return event_type == "penalty"


def split_shot_xg(shots: list[dict[str, Any]]) -> dict[int, dict[str, float]]:
    """Return per-team xG totals split into penalty and non-penalty buckets."""
    totals: dict[int, dict[str, float]] = {}

    for shot in shots:
        team_id = int(shot["teamId"])
        xg = float(shot.get("expectedGoals") or 0.0)
        team_totals = totals.setdefault(team_id, {"xg_total": 0.0, "xg_pen": 0.0, "xg_no_pen": 0.0})

        team_totals["xg_total"] += xg
        if is_penalty_shot(shot):
            team_totals["xg_pen"] += xg
        else:
            team_totals["xg_no_pen"] += xg

    return totals


def shot_to_row(
    shot: dict[str, Any],
    match_id: int,
    date: str,
    home_team: str,
    away_team: str,
    home_team_id: int,
    away_team_id: int,
) -> dict[str, Any]:
    team_id = int(shot["teamId"])
    is_home = team_id == home_team_id

    return {
        "match_id": match_id,
        "date": date,
        "home_team": home_team,
        "away_team": away_team,
        "team": home_team if is_home else away_team,
        "is_home": is_home,
        "shot_id": shot.get("id"),
        "minute": shot.get("min"),
        "minute_added": shot.get("minAdded"),
        "period": shot.get("period"),
        "player_id": shot.get("playerId"),
        "player_name": shot.get("playerName"),
        "event_type": shot.get("eventType"),
        "situation": shot.get("situation"),
        "shot_type": shot.get("shotType"),
        "is_penalty": is_penalty_shot(shot),
        "x": shot.get("x"),
        "y": shot.get("y"),
        "expected_goals": shot.get("expectedGoals"),
        "expected_goals_on_target": shot.get("expectedGoalsOnTarget"),
        "is_on_target": shot.get("isOnTarget"),
        "is_from_inside_box": shot.get("isFromInsideBox"),
        "is_blocked": shot.get("isBlocked"),
    }


def shot_sort_key(shot: dict[str, Any]) -> tuple[int, int]:
    minute = int(shot.get("min") or 0)
    added = int(shot.get("minAdded") or 0)
    return minute, added


def home_attacks_high_x(shots: list[dict[str, Any]], home_team_id: int) -> bool:
    home_x = [float(s["x"]) for s in shots if int(s["teamId"]) == home_team_id and s.get("x") is not None]
    away_x = [float(s["x"]) for s in shots if int(s["teamId"]) != home_team_id and s.get("x") is not None]
    if not home_x or not away_x:
        return True

    home_median = sorted(home_x)[len(home_x) // 2]
    away_median = sorted(away_x)[len(away_x) // 2]
    return home_median >= away_median


def team_attacking_x(
    shot_x: float,
    team_id: int,
    home_team_id: int,
    home_attacks_high: bool,
) -> float:
    team_attacks_high = home_attacks_high if team_id == home_team_id else not home_attacks_high
    return shot_x if team_attacks_high else 100.0 - shot_x


def extract_shot_possessions(
    shots: list[dict[str, Any]],
    home_team_id: int,
    away_team_id: int,
) -> list[dict[str, Any]]:
    """
    Approximate possessions using shot sequences.

    FotMob does not expose full event chains, so each shot is treated as the
    end of a possession. The start location is inferred from the previous shot.
    """
    if not shots:
        return []

    home_attacks_high = home_attacks_high_x(shots, home_team_id)
    ordered = sorted(shots, key=shot_sort_key)
    possessions: list[dict[str, Any]] = []

    for index, shot in enumerate(ordered):
        if is_penalty_shot(shot):
            continue

        team_id = int(shot["teamId"])
        end_x = team_attacking_x(float(shot["x"]), team_id, home_team_id, home_attacks_high)
        end_y = float(shot.get("y") or 50.0)

        if index == 0:
            start_x = 50.0
            start_y = 50.0
        else:
            previous = ordered[index - 1]
            previous_team_id = int(previous["teamId"])
            previous_end_x = team_attacking_x(
                float(previous["x"]),
                previous_team_id,
                home_team_id,
                home_attacks_high,
            )
            previous_end_y = float(previous.get("y") or 50.0)

            if previous_team_id == team_id:
                start_x = previous_end_x
                start_y = previous_end_y
            else:
                start_x = max(0.0, min(100.0, 100.0 - previous_end_x))
                start_y = previous_end_y

        xg = float(shot.get("expectedGoals") or 0.0)
        possessions.append(
            {
                "team_id": team_id,
                "start_x": start_x,
                "start_y": start_y,
                "end_x": end_x,
                "end_y": end_y,
                "xg": xg,
            }
        )

    return possessions


def fit_xg_from_start_position(
    possessions: list[dict[str, Any]],
) -> tuple[float, float]:
    """Simple league-wide linear model: xG ~ start_x."""
    if not possessions:
        return 0.0, 0.0

    start_values = [p["start_x"] for p in possessions]
    xg_values = [p["xg"] for p in possessions]
    mean_x = sum(start_values) / len(start_values)
    mean_y = sum(xg_values) / len(xg_values)

    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(start_values, xg_values))
    denominator = sum((x - mean_x) ** 2 for x in start_values)
    if denominator == 0:
        return mean_y, 0.0

    slope = numerator / denominator
    intercept = mean_y - slope * mean_x
    return intercept, slope


def expected_xg_from_start(start_x: float, intercept: float, slope: float) -> float:
    return intercept + slope * start_x

