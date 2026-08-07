#!/usr/bin/env python3
"""Export FotMob shot-level xG data for an EPL season."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Any

from fotmob_api import FotmobAPI
from fotmob_utils import parse_season_arg, shot_to_row

PREMIER_LEAGUE_ID = 47
DEFAULT_SEASON = "2025/2026"
DEFAULT_OUTPUT = Path(__file__).with_name("epl_2025_26_shots.csv")


def fetch_shots(
    client: FotmobAPI,
    season: str,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fixtures = client.get_fixtures(id=PREMIER_LEAGUE_ID, season=season)
    if limit is not None:
        fixtures = fixtures[:limit]

    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for index, fixture in enumerate(fixtures, start=1):
        match_id = int(fixture["id"])
        home = fixture["home"]["name"]
        away = fixture["away"]["name"]
        print(f"[{index}/{len(fixtures)}] {home} vs {away}", flush=True)

        try:
            details = client.get_match_details(match_id=match_id)
            shots = details.get("content", {}).get("shotmap", {}).get("shots", [])
        except Exception as error:
            skipped.append({"match_id": match_id, "reason": str(error)})
            continue

        if not shots:
            skipped.append({"match_id": match_id, "reason": "missing shotmap"})
            continue

        date = fixture.get("status", {}).get("utcTime", "")[:10]
        home_team_id = int(fixture["home"]["id"])
        away_team_id = int(fixture["away"]["id"])

        for shot in shots:
            rows.append(
                shot_to_row(
                    shot=shot,
                    match_id=match_id,
                    date=date,
                    home_team=home,
                    away_team=away,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                )
            )

    return rows, skipped


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    if not rows:
        raise ValueError("No shot rows to write.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export EPL shot-level xG from FotMob.")
    parser.add_argument("--season", default=DEFAULT_SEASON)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    season = parse_season_arg(args.season)
    client = FotmobAPI()

    print(f"Fetching EPL shots for {season}")
    started = time.time()
    rows, skipped = fetch_shots(client, season=season, limit=args.limit)
    write_csv(rows, args.output)

    print()
    print(f"Saved {len(rows)} shots to {args.output}")
    if skipped:
        print(f"Skipped {len(skipped)} matches")
    print(f"Done in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
