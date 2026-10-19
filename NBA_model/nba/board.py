"""Build the public picks board JSON for the Betting Models site page."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nba.config import Settings
from nba.model import Pick, compute_picks
from nba.storage import Store

DEFAULT_SITE_BOARD = (
    Path(__file__).resolve().parents[2] / "betting-models" / "nba-ats" / "picks.json"
)


def grade_pick(store: Store, pick_row: dict) -> dict:
    """Attach W/L/P/pending result for a stored pick."""
    game = store.get_game(pick_row["game_id"])
    out = dict(pick_row)
    if not game or game.status != "final" or game.home_ats is None:
        out["result"] = "pending"
        out["final_score"] = None
        return out

    bet_ats = (
        game.home_ats if pick_row["bet_team"] == game.home_team else game.away_ats
    )
    if bet_ats is None:
        out["result"] = "pending"
        out["final_score"] = None
        return out
    if bet_ats > 0:
        result = "W"
    elif bet_ats < 0:
        result = "L"
    else:
        result = "P"
    out["result"] = result
    out["final_score"] = f"{game.away_team} {game.away_score}, {game.home_team} {game.home_score}"
    out["bet_ats"] = bet_ats
    return out


def load_all_picks(store: Store) -> list[dict]:
    rows = store._conn.execute(
        """
        SELECT pick_date, rank, game_id, bet_team, bet_spread, home_team, away_team,
               home_score_7d, away_score_7d, abs_diff, message, created_at
        FROM picks
        ORDER BY pick_date DESC, rank ASC
        """
    ).fetchall()
    picks = []
    for r in rows:
        bet = r["bet_team"]
        against = r["away_team"] if bet == r["home_team"] else r["home_team"]
        picks.append(
            {
                "pick_date": r["pick_date"],
                "rank": r["rank"],
                "game_id": r["game_id"],
                "bet_team": bet,
                "bet_spread": r["bet_spread"],
                "home_team": r["home_team"],
                "away_team": r["away_team"],
                "against_team": against,
                "home_score_7d": r["home_score_7d"],
                "away_score_7d": r["away_score_7d"],
                "abs_diff": r["abs_diff"],
                "message": r["message"],
                "created_at": r["created_at"],
            }
        )
    return picks


def next_slate_picks(
    store: Store,
    *,
    settings: Settings,
    after_date: str,
) -> dict | None:
    """If today has no games, preview the next day that has qualifying picks."""
    tz = ZoneInfo(settings.timezone)
    start = datetime.fromisoformat(after_date).replace(tzinfo=tz) + timedelta(days=1)
    for offset in range(0, 7):
        day = start + timedelta(days=offset)
        as_of = day.replace(hour=8, minute=0, second=0, microsecond=0)
        picks = compute_picks(
            store,
            as_of=as_of.astimezone(tz),
            lookback_days=settings.ats_lookback_days,
            top_n=settings.top_n_picks,
            timezone_name=settings.timezone,
        )
        if picks:
            return {
                "pick_date": day.date().isoformat(),
                "picks": [p.to_dict() for p in picks],
            }
    return None


def build_board(
    store: Store,
    *,
    today_picks: list[Pick],
    pick_date: str,
    settings: Settings,
) -> dict:
    history = [grade_pick(store, row) for row in load_all_picks(store)]
    graded = [h for h in history if h["result"] in {"W", "L", "P"}]
    wins = sum(1 for h in graded if h["result"] == "W")
    losses = sum(1 for h in graded if h["result"] == "L")
    pushes = sum(1 for h in graded if h["result"] == "P")
    tz = ZoneInfo(settings.timezone)
    upcoming = None
    if not today_picks:
        upcoming = next_slate_picks(store, settings=settings, after_date=pick_date)
    return {
        "updated": datetime.now(tz).isoformat(),
        "timezone": settings.timezone,
        "lookback_days": settings.ats_lookback_days,
        "today": {
            "pick_date": pick_date,
            "picks": [p.to_dict() for p in today_picks],
        },
        "upcoming": upcoming,
        "record": {
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "pending": sum(1 for h in history if h["result"] == "pending"),
        },
        "history": history,
    }


def write_board(board: dict, path: Path | None = None) -> Path:
    out = path or DEFAULT_SITE_BOARD
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(board, indent=2), encoding="utf-8")
    return out
