#!/usr/bin/env python3
"""Fetch xG and momentum totals for every EPL match in a season."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fotmob_api import FotmobAPI
from fotmob_utils import extract_momentum_totals, parse_season_arg, split_shot_xg

PREMIER_LEAGUE_ID = 47
DEFAULT_SEASON = "2025/2026"
DEFAULT_OUTPUT = Path(__file__).with_name("epl_2025_26_xg_momentum.csv")


@dataclass
class MatchStats:
    match_id: int
    date: str
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    home_xg: float | None
    away_xg: float | None
    home_xg_no_pen: float | None
    home_xg_pen: float | None
    away_xg_no_pen: float | None
    away_xg_pen: float | None
    home_momentum_total: float | None
    away_momentum_total: float | None


def fixture_to_match_stats(client: FotmobAPI, fixture: dict[str, Any]) -> MatchStats | None:
    match_id = int(fixture["id"])
    details = client.get_match_details(match_id=match_id)
    content = details.get("content", {})

    shots = content.get("shotmap", {}).get("shots", [])
    momentum = extract_momentum_totals(content.get("momentum"))
    if not shots or momentum is None:
        return None

    home_team_id = int(fixture["home"]["id"])
    away_team_id = int(fixture["away"]["id"])
    xg_by_team = split_shot_xg(shots)

    home_totals = xg_by_team.get(
        home_team_id,
        {"xg_total": 0.0, "xg_pen": 0.0, "xg_no_pen": 0.0},
    )
    away_totals = xg_by_team.get(
        away_team_id,
        {"xg_total": 0.0, "xg_pen": 0.0, "xg_no_pen": 0.0},
    )
    home_momentum, away_momentum = momentum
    status = fixture.get("status", {})

    return MatchStats(
        match_id=match_id,
        date=status.get("utcTime", "")[:10],
        home_team=fixture["home"]["name"],
        away_team=fixture["away"]["name"],
        home_score=fixture["home"].get("score"),
        away_score=fixture["away"].get("score"),
        home_xg=home_totals["xg_total"],
        away_xg=away_totals["xg_total"],
        home_xg_no_pen=home_totals["xg_no_pen"],
        home_xg_pen=home_totals["xg_pen"],
        away_xg_no_pen=away_totals["xg_no_pen"],
        away_xg_pen=away_totals["xg_pen"],
        home_momentum_total=home_momentum,
        away_momentum_total=away_momentum,
    )


def write_csv(rows: list[MatchStats], output_path: Path) -> None:
    fieldnames = [
        "match_id",
        "date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "home_xg",
        "away_xg",
        "home_xg_no_pen",
        "home_xg_pen",
        "away_xg_no_pen",
        "away_xg_pen",
        "home_momentum_total",
        "away_momentum_total",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def fetch_season_stats(
    client: FotmobAPI,
    season: str,
    limit: int | None = None,
) -> tuple[list[MatchStats], list[dict[str, Any]]]:
    fixtures = client.get_fixtures(id=PREMIER_LEAGUE_ID, season=season)
    if limit is not None:
        fixtures = fixtures[:limit]

    rows: list[MatchStats] = []
    skipped: list[dict[str, Any]] = []

    for index, fixture in enumerate(fixtures, start=1):
        home = fixture["home"]["name"]
        away = fixture["away"]["name"]
        print(f"[{index}/{len(fixtures)}] {home} vs {away}", flush=True)

        try:
            row = fixture_to_match_stats(client, fixture)
        except Exception as error:
            skipped.append(
                {
                    "match_id": fixture["id"],
                    "home_team": home,
                    "away_team": away,
                    "reason": str(error),
                }
            )
            continue

        if row is None:
            skipped.append(
                {
                    "match_id": fixture["id"],
                    "home_team": home,
                    "away_team": away,
                    "reason": "missing shotmap or momentum data",
                }
            )
            continue

        rows.append(row)

    return rows, skipped


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download EPL xG and momentum totals for every match in a season."
    )
    parser.add_argument(
        "--season",
        default=DEFAULT_SEASON,
        help='Season label, e.g. "2025/2026" or "2025-26" (default: 2025/2026)',
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"CSV output path (default: {DEFAULT_OUTPUT.name})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only fetch the first N fixtures (useful for testing)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    season = parse_season_arg(args.season)
    client = FotmobAPI()

    print(f"Fetching EPL match stats for {season}")
    started = time.time()
    rows, skipped = fetch_season_stats(client, season=season, limit=args.limit)
    write_csv(rows, args.output)

    elapsed = time.time() - started
    print()
    print(f"Saved {len(rows)} matches to {args.output}")
    if skipped:
        print(f"Skipped {len(skipped)} matches without complete data")
    print(f"Done in {elapsed:.1f}s")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
