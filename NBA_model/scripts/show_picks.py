#!/usr/bin/env python3
"""Compute and print today's picks without syncing or texting."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nba.config import get_settings
from nba.model import compute_picks, format_alert
from nba.storage import Store


def main() -> int:
    settings = get_settings()
    with Store(settings.db_path) as store:
        picks = compute_picks(
            store,
            lookback_days=settings.ats_lookback_days,
            top_n=settings.top_n_picks,
            timezone_name=settings.timezone,
        )
        pick_date = datetime.now(ZoneInfo(settings.timezone)).date().isoformat()
        print(format_alert(picks, pick_date=pick_date))
        print(json.dumps([p.to_dict() for p in picks], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
