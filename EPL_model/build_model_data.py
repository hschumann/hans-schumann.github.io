#!/usr/bin/env python3
"""Build match-level model data for home win / draw / lose prediction."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fotmob_api import FotmobAPI
from fotmob_utils import (
    DEFAULT_MAX_GAMEWEEK,
    DEFAULT_SEASON,
    GW4_CUTOFF_DATE,
    PREMIER_LEAGUE_ID,
    extract_momentum_totals,
    extract_shot_possessions,
    expected_xg_from_start,
    fit_xg_from_start_position,
    parse_season_arg,
    split_shot_xg,
)

DEFAULT_OUTPUT = Path(__file__).with_name("epl_model_gw1_4.csv")
DEFAULT_POSSESSIONS_OUTPUT = Path(__file__).with_name("epl_possessions_gw1_4.csv")


@dataclass
class TeamMatchRecord:
    team_id: int
    team_name: str
    match_id: int
    date: str
    gameweek: int
    is_home: bool
    xg_for: float
    xg_against: float
    momentum: float
    possessions: list[dict[str, Any]]


@dataclass
class TeamFeatures:
    team_name: str
    games: int
    xg_margin_vs_avg: float
    momentum_margin_vs_avg: float
    avg_possession_start_x: float
    avg_possession_end_x: float
    xg_start_position_residual: float


def match_result(home_score: int | None, away_score: int | None) -> str:
    if home_score is None or away_score is None:
        return "unknown"
    if home_score > away_score:
        return "home_win"
    if home_score == away_score:
        return "draw"
    return "away_win"


def filter_fixtures_by_gameweek(
    fixtures: list[dict[str, Any]],
    max_gameweek: int,
    cutoff_date: str,
) -> list[dict[str, Any]]:
    filtered = [
        fixture
        for fixture in fixtures
        if fixture.get("status", {}).get("utcTime", "")[:10] <= cutoff_date
    ]
    # First four gameweeks in 2025/26 span 40 matches.
    return filtered[: max_gameweek * 10]


def load_match_records(
    client: FotmobAPI,
    fixtures: list[dict[str, Any]],
) -> list[TeamMatchRecord]:
    records: list[TeamMatchRecord] = []

    for index, fixture in enumerate(fixtures, start=1):
        match_id = int(fixture["id"])
        home_name = fixture["home"]["name"]
        away_name = fixture["away"]["name"]
        home_team_id = int(fixture["home"]["id"])
        away_team_id = int(fixture["away"]["id"])
        date = fixture.get("status", {}).get("utcTime", "")[:10]
        gameweek = ((index - 1) // 10) + 1

        print(f"[{index}/{len(fixtures)}] GW{gameweek} {home_name} vs {away_name}", flush=True)
        details = client.get_match_details(match_id=match_id)
        content = details.get("content", {})
        shots = content.get("shotmap", {}).get("shots", [])
        momentum = extract_momentum_totals(content.get("momentum"))
        if not shots or momentum is None:
            continue

        xg_by_team = split_shot_xg(shots)
        home_xg = xg_by_team.get(home_team_id, {}).get("xg_no_pen", 0.0)
        away_xg = xg_by_team.get(away_team_id, {}).get("xg_no_pen", 0.0)
        home_momentum, away_momentum = momentum
        possessions = extract_shot_possessions(shots, home_team_id, away_team_id)

        records.append(
            TeamMatchRecord(
                team_id=home_team_id,
                team_name=home_name,
                match_id=match_id,
                date=date,
                gameweek=gameweek,
                is_home=True,
                xg_for=home_xg,
                xg_against=away_xg,
                momentum=float(home_momentum),
                possessions=[p for p in possessions if p["team_id"] == home_team_id],
            )
        )
        records.append(
            TeamMatchRecord(
                team_id=away_team_id,
                team_name=away_name,
                match_id=match_id,
                date=date,
                gameweek=gameweek,
                is_home=False,
                xg_for=away_xg,
                xg_against=home_xg,
                momentum=float(away_momentum),
                possessions=[p for p in possessions if p["team_id"] == away_team_id],
            )
        )

    return records


def build_team_features(
    records: list[TeamMatchRecord],
    intercept: float,
    slope: float,
) -> dict[str, TeamFeatures]:
    grouped: dict[str, list[TeamMatchRecord]] = defaultdict(list)
    for record in records:
        grouped[record.team_name].append(record)

    league_net = [record.xg_for - record.xg_against for record in records]
    league_momentum = [record.momentum for record in records]
    league_avg_net = sum(league_net) / len(league_net)
    league_avg_momentum = sum(league_momentum) / len(league_momentum)

    team_features: dict[str, TeamFeatures] = {}
    for team_name, team_records in grouped.items():
        avg_xg_for = sum(record.xg_for for record in team_records) / len(team_records)
        avg_xg_against = sum(record.xg_against for record in team_records) / len(team_records)
        avg_momentum = sum(record.momentum for record in team_records) / len(team_records)

        possessions = [p for record in team_records for p in record.possessions]
        avg_start_x = sum(p["start_x"] for p in possessions) / len(possessions) if possessions else 50.0
        avg_end_x = sum(p["end_x"] for p in possessions) / len(possessions) if possessions else 50.0

        residuals = [
            p["xg"] - expected_xg_from_start(p["start_x"], intercept, slope)
            for p in possessions
        ]
        avg_residual = sum(residuals) / len(residuals) if residuals else 0.0

        team_features[team_name] = TeamFeatures(
            team_name=team_name,
            games=len(team_records),
            xg_margin_vs_avg=(avg_xg_for - avg_xg_against) - league_avg_net,
            momentum_margin_vs_avg=avg_momentum - league_avg_momentum,
            avg_possession_start_x=avg_start_x,
            avg_possession_end_x=avg_end_x,
            xg_start_position_residual=avg_residual,
        )

    return team_features


def build_match_rows(
    fixtures: list[dict[str, Any]],
    team_features: dict[str, TeamFeatures],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for index, fixture in enumerate(fixtures, start=1):
        home_name = fixture["home"]["name"]
        away_name = fixture["away"]["name"]
        home = team_features[home_name]
        away = team_features[away_name]
        result = match_result(fixture["home"].get("score"), fixture["away"].get("score"))

        rows.append(
            {
                "match_id": fixture["id"],
                "date": fixture.get("status", {}).get("utcTime", "")[:10],
                "gameweek": ((index - 1) // 10) + 1,
                "home_team": home_name,
                "away_team": away_name,
                "home_score": fixture["home"].get("score"),
                "away_score": fixture["away"].get("score"),
                "result": result,
                "home_xg_margin_vs_avg": home.xg_margin_vs_avg,
                "away_xg_margin_vs_avg": away.xg_margin_vs_avg,
                "xg_margin_diff": home.xg_margin_vs_avg - away.xg_margin_vs_avg,
                "home_momentum_margin_vs_avg": home.momentum_margin_vs_avg,
                "away_momentum_margin_vs_avg": away.momentum_margin_vs_avg,
                "momentum_margin_diff": home.momentum_margin_vs_avg - away.momentum_margin_vs_avg,
                "home_avg_possession_start_x": home.avg_possession_start_x,
                "away_avg_possession_start_x": away.avg_possession_start_x,
                "possession_start_x_diff": home.avg_possession_start_x - away.avg_possession_start_x,
                "home_avg_possession_end_x": home.avg_possession_end_x,
                "away_avg_possession_end_x": away.avg_possession_end_x,
                "possession_end_x_diff": home.avg_possession_end_x - away.avg_possession_end_x,
                "home_xg_start_position_residual": home.xg_start_position_residual,
                "away_xg_start_position_residual": away.xg_start_position_residual,
                "xg_start_position_residual_diff": home.xg_start_position_residual - away.xg_start_position_residual,
            }
        )

    return rows


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_possession_csv(records: list[TeamMatchRecord], output_path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for record in records:
        for possession in record.possessions:
            rows.append(
                {
                    "match_id": record.match_id,
                    "date": record.date,
                    "gameweek": record.gameweek,
                    "team": record.team_name,
                    "is_home": record.is_home,
                    "start_x": possession["start_x"],
                    "start_y": possession["start_y"],
                    "end_x": possession["end_x"],
                    "end_y": possession["end_y"],
                    "xg": possession["xg"],
                }
            )

    if not rows:
        return

    write_csv(rows, output_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build EPL model data for gameweeks 1-4.")
    parser.add_argument("--season", default=DEFAULT_SEASON)
    parser.add_argument("--max-gameweek", type=int, default=DEFAULT_MAX_GAMEWEEK)
    parser.add_argument("--cutoff-date", default=GW4_CUTOFF_DATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--possessions-output", type=Path, default=DEFAULT_POSSESSIONS_OUTPUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    season = parse_season_arg(args.season)
    client = FotmobAPI()

    fixtures = client.get_fixtures(id=PREMIER_LEAGUE_ID, season=season)
    fixtures = filter_fixtures_by_gameweek(fixtures, args.max_gameweek, args.cutoff_date)

    print(f"Building model data for GW1-{args.max_gameweek} ({len(fixtures)} matches)")
    started = time.time()
    records = load_match_records(client, fixtures)
    if not records:
        print("No records loaded.")
        return 1

    all_possessions = [p for record in records for p in record.possessions]
    intercept, slope = fit_xg_from_start_position(all_possessions)
    team_features = build_team_features(records, intercept, slope)
    match_rows = build_match_rows(fixtures, team_features)

    write_csv(match_rows, args.output)
    write_possession_csv(records, args.possessions_output)

    print()
    print(f"Saved {len(match_rows)} match rows -> {args.output}")
    print(f"Saved possession rows -> {args.possessions_output}")
    print(f"League xG-from-start model: xg = {intercept:.4f} + {slope:.4f} * start_x")
    print(f"Done in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
