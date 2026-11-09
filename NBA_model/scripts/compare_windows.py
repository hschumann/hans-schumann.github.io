#!/usr/bin/env python3
"""Compare ATS lookback windows on top-25% |Δ| accuracy from GRADE_START onward."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nba.board import GRADE_START, _bet_result
from nba.config import get_settings
from nba.model import rank_slate, top_percentile_accuracy
from nba.storage import Store

WINDOWS: list[dict] = [
    {"label": "7 days", "lookback_days": 7, "lookback_games": None},
    {"label": "10 days", "lookback_days": 10, "lookback_games": None},
    {"label": "14 days", "lookback_days": 14, "lookback_games": None},
    {"label": "prior 1 game", "lookback_days": None, "lookback_games": 1},
    {"label": "prior 2 games", "lookback_days": None, "lookback_games": 2},
    {"label": "prior 3 games", "lookback_days": None, "lookback_games": 3},
    {"label": "prior 5 games", "lookback_days": None, "lookback_games": 5},
]


def graded_samples(
    store: Store,
    *,
    timezone_name: str,
    lookback_days: int | None,
    lookback_games: int | None,
) -> list[tuple[float, str]]:
    tz = ZoneInfo(timezone_name)
    games = store.list_games()
    if not games:
        return []
    first = min(
        datetime.fromisoformat(g.tipoff_utc.replace("Z", "+00:00")) for g in games
    )
    day = max(first.astimezone(tz).date(), GRADE_START)
    last = datetime.now(tz).date()
    samples: list[tuple[float, str]] = []
    while day <= last:
        as_of = datetime(day.year, day.month, day.day, 8, tzinfo=tz)
        for pick in rank_slate(
            store,
            as_of=as_of,
            lookback_days=lookback_days,
            lookback_games=lookback_games,
            timezone_name=timezone_name,
        ):
            game = store.get_game(pick.game_id)
            if game is None:
                continue
            result = _bet_result(game, pick.bet_team)
            if result is None:
                continue
            samples.append((pick.abs_diff, result))
        day += timedelta(days=1)
    return samples


def main() -> int:
    settings = get_settings()
    rows: list[dict] = []
    with Store(settings.db_path) as store:
        for window in WINDOWS:
            samples = graded_samples(
                store,
                timezone_name=settings.timezone,
                lookback_days=window["lookback_days"],
                lookback_games=window["lookback_games"],
            )
            all_wins = sum(1 for _, r in samples if r == "W")
            all_losses = sum(1 for _, r in samples if r == "L")
            all_pushes = sum(1 for _, r in samples if r == "P")
            all_decided = all_wins + all_losses
            top = top_percentile_accuracy(samples, percentile=75.0)
            rows.append(
                {
                    "label": window["label"],
                    "lookback_days": window["lookback_days"],
                    "lookback_games": window["lookback_games"],
                    "all_games": len(samples),
                    "all_record": f"{all_wins}-{all_losses}-{all_pushes}",
                    "all_accuracy": (all_wins / all_decided) if all_decided else None,
                    "top25_games": top["games"],
                    "top25_record": f"{top['wins']}-{top['losses']}-{top['pushes']}",
                    "top25_accuracy": top["accuracy"],
                    "top25_cutoff": top["cutoff"],
                }
            )

    ranked = sorted(
        rows,
        key=lambda r: (
            r["top25_accuracy"] is not None,
            r["top25_accuracy"] or -1,
            r["top25_games"],
        ),
        reverse=True,
    )
    out = {
        "grade_start": GRADE_START.isoformat(),
        "evaluated_through": datetime.now(ZoneInfo(settings.timezone)).date().isoformat(),
        "metric": "top 25% of graded games by |Δ| (75th percentile cutoff)",
        "windows": ranked,
        "winner": ranked[0]["label"] if ranked else None,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
