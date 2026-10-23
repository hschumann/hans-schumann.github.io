#!/usr/bin/env python3
"""Daily pipeline: sync ESPN data, compute top ATS picks, and write the site board."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nba.board import build_board, write_board
from nba.config import get_settings
from nba.model import compute_picks, format_alert
from nba.storage import Store
from nba.sync import sync_from_espn, sync_odds_api_spreads


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NBA ATS daily sync + morning picks")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="Days of ESPN history to refresh (default: lookback+3)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = get_settings()
    lookback = args.lookback_days or (settings.ats_lookback_days + 3)

    with Store(settings.db_path) as store:
        stats = sync_from_espn(
            store,
            lookback_days=lookback,
            lookahead_days=2,
            tz_name=settings.timezone,
        )
        odds_updates = sync_odds_api_spreads(store, settings)
        picks = compute_picks(
            store,
            lookback_days=settings.ats_lookback_days,
            top_n=settings.top_n_picks,
            timezone_name=settings.timezone,
        )

        tz = ZoneInfo(settings.timezone)
        pick_date = datetime.now(tz).date().isoformat()
        payload = {
            "generated_at": datetime.now(tz).isoformat(),
            "pick_date": pick_date,
            "lookback_days": settings.ats_lookback_days,
            "sync": {**stats, "odds_api_updates": odds_updates},
            "picks": [p.to_dict() for p in picks],
        }
        settings.picks_json.parent.mkdir(parents=True, exist_ok=True)
        settings.picks_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        n_csv = store.export_games_csv(settings.games_csv)
        store.save_picks(pick_date, [p.to_dict() for p in picks])

        board = build_board(
            store, today_picks=picks, pick_date=pick_date, settings=settings
        )
        board_path = write_board(board)

        print(format_alert(picks, pick_date=pick_date))
        print(
            f"\nSynced ESPN games={stats['espn_games']} "
            f"spreads~{stats['spreads_touched']} results~{stats['results_touched']} "
            f"odds_api={odds_updates}; exported {n_csv} games -> {settings.games_csv}"
        )
        print(f"Wrote picks -> {settings.picks_json}")
        print(f"Wrote site board -> {board_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
