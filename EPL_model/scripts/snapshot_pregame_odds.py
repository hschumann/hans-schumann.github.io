#!/usr/bin/env python3
"""Snapshot pregame EPL odds for the halftime MVP (Football-Data.co.uk)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from football_data.loader import load_epl_matches
from football_data.odds import add_fair_over_under, add_fair_probabilities
from football_data.team_names import normalize_team_name

DEFAULT_SITE_OUTPUT = PROJECT_ROOT.parent / "epl-halftime-bets" / "odds.json"
DEFAULT_DATA_OUTPUT = PROJECT_ROOT / "data" / "football_data" / "pregame_odds.json"


def fixture_row(match) -> dict:
    return {
        "date": match.date.strftime("%Y-%m-%d"),
        "home_team": normalize_team_name(match.home_team),
        "away_team": normalize_team_name(match.away_team),
        "avg_home": round(float(match.avg_home), 3),
        "avg_draw": round(float(match.avg_draw), 3),
        "avg_away": round(float(match.avg_away), 3),
        "avg_over_2_5": round(float(match.avg_over_2_5), 3),
        "avg_under_2_5": round(float(match.avg_under_2_5), 3),
        "fair_home": round(float(match.fair_home), 4),
        "fair_draw": round(float(match.fair_draw), 4),
        "fair_away": round(float(match.fair_away), 4),
        "fair_over_2_5": round(float(match.fair_over_2_5), 4),
    }


def build_snapshot(season: str | None) -> dict:
    matches = load_epl_matches()
    matches = add_fair_probabilities(matches, prefix="avg")
    matches = add_fair_over_under(matches)
    matches = matches.dropna(
        subset=["avg_home", "avg_over_2_5", "home_team", "away_team", "date"]
    )
    if season:
        matches = matches[matches["season"] == season].copy()

    rows = [fixture_row(row) for row in matches.itertuples(index=False)]
    rows.sort(key=lambda r: (r["date"], r["home_team"]))
    return {
        "updated": datetime.now(timezone.utc).isoformat(),
        "season": season or (matches["season"].iloc[-1] if len(matches) else None),
        "fixture_count": len(rows),
        "fixtures": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Snapshot pregame odds for EPL halftime MVP.")
    parser.add_argument("--season", default="2025/26")
    parser.add_argument("--site-output", type=Path, default=DEFAULT_SITE_OUTPUT)
    parser.add_argument("--data-output", type=Path, default=DEFAULT_DATA_OUTPUT)
    parser.add_argument("--refresh-data", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.refresh_data:
        load_epl_matches(refresh=True)

    payload = build_snapshot(args.season)
    for path in (args.site_output, args.data_output):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {payload['fixture_count']} fixtures -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
