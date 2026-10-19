#!/usr/bin/env python3
"""Print trailing ATS team scores and recent games for manual verification."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nba.config import get_settings
from nba.model import team_ats_scores
from nba.storage import Store


def main() -> int:
    parser = argparse.ArgumentParser(description="Show 7-day ATS team scores")
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--team", default=None, help="Filter recent games to one abbrev")
    parser.add_argument("--recent", type=int, default=12, help="Recent games to print")
    args = parser.parse_args()

    settings = get_settings()
    lookback = args.days or settings.ats_lookback_days
    tz = ZoneInfo(settings.timezone)
    as_of = datetime.now(tz).astimezone(timezone.utc)
    window_start = as_of - timedelta(days=lookback)

    with Store(settings.db_path) as store:
        completed = store.completed_with_ats(
            window_start.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            as_of.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        scores = team_ats_scores(completed)

        print(f"DB: {settings.db_path}")
        print(f"Window: last {lookback} days ({len(completed)} team-games worth of results)\n")
        print(f"{'Team':<6} {'G':>3} {'AvgATS':>8} {'SumATS':>8}")
        for row in sorted(scores.values(), key=lambda x: x.avg_ats):
            print(f"{row.team:<6} {row.games:>3} {row.avg_ats:>8.1f} {row.total_ats:>8.1f}")

        games = sorted(completed, key=lambda g: g.tipoff_utc, reverse=True)
        if args.team:
            abbr = args.team.upper()
            games = [
                g
                for g in games
                if g.home_team == abbr or g.away_team == abbr
            ]
        print(f"\nRecent games (ATS = score margin + home spread):")
        print(f"{'Date':<12} {'Away':<5} {'Home':<5} {'Score':<9} {'Hspr':>6} {'H_ATS':>7} {'A_ATS':>7}")
        for g in games[: args.recent]:
            print(
                f"{g.tipoff_utc[:10]:<12} {g.away_team:<5} {g.home_team:<5} "
                f"{g.away_score}-{g.home_score:<3} {g.home_spread:>6} "
                f"{g.home_ats:>7.1f} {g.away_ats:>7.1f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
