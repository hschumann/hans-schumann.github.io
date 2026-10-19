#!/usr/bin/env python3
"""Backfill recent ESPN scoreboards into the local DB.

Note: ESPN drops odds from completed scoreboards, so historical ATS margins
only appear for games whose spreads were captured while still scheduled.
Run the daily job during the season to accumulate closing lines.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nba.config import get_settings
from nba.storage import Store
from nba.sync import bootstrap_history


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill ESPN NBA scoreboards")
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()
    settings = get_settings()
    with Store(settings.db_path) as store:
        n = bootstrap_history(store, days=args.days, tz_name=settings.timezone)
        exported = store.export_games_csv(settings.games_csv)
        print(f"Processed {n} ESPN games; DB has {exported} rows -> {settings.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
