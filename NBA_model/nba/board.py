"""Build the public picks board JSON for the Betting Models site page."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from nba.config import Settings
from nba.model import Pick, accuracy_by_percentile, rank_slate
from nba.storage import Store

DEFAULT_SITE_BOARD = (
    Path(__file__).resolve().parents[2] / "betting-models" / "nba-ats" / "picks.json"
)

# Regular-season start. Earlier games still feed the 7-day averages, but they
# are not wins, losses, or part of the percentile record.
GRADE_START = date(2026, 10, 27)


def counts_toward_grade(pick_date: str) -> bool:
    return pick_date >= GRADE_START.isoformat()


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


def slate_on(
    store: Store,
    *,
    settings: Settings,
    as_of: datetime,
) -> list[Pick]:
    return rank_slate(
        store,
        as_of=as_of,
        lookback_days=settings.ats_lookback_days,
        timezone_name=settings.timezone,
    )


def slate_payload(slate: list[Pick], *, pick_date: str, top_n: int) -> dict:
    return {
        "pick_date": pick_date,
        "picks": [p.to_dict() for p in slate[:top_n]],
        "slate": [p.to_dict() for p in slate],
    }


def next_slate_picks(
    store: Store,
    *,
    settings: Settings,
    after_date: str,
) -> dict | None:
    """If today has no games, preview the next day that has qualifying games."""
    tz = ZoneInfo(settings.timezone)
    start = datetime.fromisoformat(after_date).replace(tzinfo=tz) + timedelta(days=1)
    for offset in range(0, 7):
        day = start + timedelta(days=offset)
        as_of = day.replace(hour=8, minute=0, second=0, microsecond=0)
        slate = slate_on(store, settings=settings, as_of=as_of)
        if slate:
            return slate_payload(
                slate, pick_date=day.date().isoformat(), top_n=settings.top_n_picks
            )
    return None


def _bet_result(game, bet_team: str) -> str | None:
    if game.status != "final" or game.home_ats is None:
        return None
    bet_ats = game.home_ats if bet_team == game.home_team else game.away_ats
    if bet_ats is None:
        return None
    if bet_ats > 0:
        return "W"
    if bet_ats < 0:
        return "L"
    return "P"


def graded_signals(store: Store, *, settings: Settings) -> list[tuple[float, str]]:
    """Finished games on or after GRADE_START, as (abs_diff, W/L/P)."""
    tz = ZoneInfo(settings.timezone)
    games = store.list_games()
    if not games:
        return []
    first = min(datetime.fromisoformat(g.tipoff_utc.replace("Z", "+00:00")) for g in games)
    day = max(first.astimezone(tz).date(), GRADE_START)
    last = datetime.now(tz).date()
    samples: list[tuple[float, str]] = []
    while day <= last:
        as_of = datetime(day.year, day.month, day.day, 8, tzinfo=tz)
        for pick in slate_on(store, settings=settings, as_of=as_of):
            game = store.get_game(pick.game_id)
            if game is None:
                continue
            result = _bet_result(game, pick.bet_team)
            if result is None:
                continue
            samples.append((pick.abs_diff, result))
        day += timedelta(days=1)
    return samples


def build_board(
    store: Store,
    *,
    pick_date: str,
    settings: Settings,
) -> dict:
    history = [
        grade_pick(store, row)
        for row in load_all_picks(store)
        if counts_toward_grade(row["pick_date"])
    ]
    graded = [h for h in history if h["result"] in {"W", "L", "P"}]
    wins = sum(1 for h in graded if h["result"] == "W")
    losses = sum(1 for h in graded if h["result"] == "L")
    pushes = sum(1 for h in graded if h["result"] == "P")
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    if pick_date == now.date().isoformat():
        as_of = now
    else:
        as_of = datetime.fromisoformat(pick_date).replace(
            tzinfo=tz, hour=8, minute=0, second=0, microsecond=0
        )
    slate = slate_on(store, settings=settings, as_of=as_of)
    upcoming = None
    if not slate:
        upcoming = next_slate_picks(store, settings=settings, after_date=pick_date)
    return {
        "updated": now.isoformat(),
        "timezone": settings.timezone,
        "lookback_days": settings.ats_lookback_days,
        "grade_start": GRADE_START.isoformat(),
        "today": slate_payload(slate, pick_date=pick_date, top_n=settings.top_n_picks),
        "upcoming": upcoming,
        "record": {
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "pending": sum(1 for h in history if h["result"] == "pending"),
        },
        "history": history,
        "accuracy_by_percentile": accuracy_by_percentile(
            graded_signals(store, settings=settings)
        ),
    }


def write_board(board: dict, path: Path | None = None) -> Path:
    out = path or DEFAULT_SITE_BOARD
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(board, indent=2), encoding="utf-8")
    return out
