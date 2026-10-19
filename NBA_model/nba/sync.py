"""Pull ESPN (and optional Odds API) data into the local store."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nba.config import Settings
from nba.espn import EspnGame, fetch_closing_home_spread, fetch_range
from nba.odds_api import fetch_spreads
from nba.storage import Store
from nba.teams import is_nba_matchup


def _apply_espn_game(store: Store, game: EspnGame, *, fill_closing: bool = True) -> None:
    if not is_nba_matchup(game.home_team, game.away_team):
        return
    if game.status == "scheduled":
        store.upsert_scheduled(
            game_id=game.game_id,
            tipoff_utc=game.tipoff_utc,
            home_team=game.home_team,
            away_team=game.away_team,
        )
        if game.home_spread is not None:
            store.upsert_spread(
                game_id=game.game_id,
                tipoff_utc=game.tipoff_utc,
                home_team=game.home_team,
                away_team=game.away_team,
                home_spread=game.home_spread,
                spread_source=game.spread_source or "espn",
            )
    if game.status in {"final", "in_progress"} and game.home_score is not None:
        store.upsert_result(
            game_id=game.game_id,
            tipoff_utc=game.tipoff_utc,
            home_team=game.home_team,
            away_team=game.away_team,
            home_score=game.home_score,
            away_score=game.away_score or 0,
            status=game.status,
        )
        if fill_closing and game.status == "final":
            existing = store.get_game(game.game_id)
            if existing and existing.home_spread is None:
                closing, source = fetch_closing_home_spread(game.game_id)
                if closing is not None:
                    store.set_spread_for_completed(
                        game.game_id, closing, source or "espn-summary"
                    )


def sync_from_espn(
    store: Store,
    *,
    lookback_days: int = 10,
    lookahead_days: int = 2,
    tz_name: str = "America/New_York",
) -> dict[str, int]:
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()
    start = today - timedelta(days=lookback_days)
    end = today + timedelta(days=lookahead_days)
    games = fetch_range(start, end)
    spreads = results = 0
    for game in games:
        before = store.get_game(game.game_id)
        _apply_espn_game(store, game)
        after = store.get_game(game.game_id)
        if after and after.home_spread is not None:
            if not before or before.home_spread != after.home_spread:
                spreads += 1
        if after and after.status == "final" and after.home_ats is not None:
            if not before or before.home_ats != after.home_ats:
                results += 1
    return {"espn_games": len(games), "spreads_touched": spreads, "results_touched": results}


def sync_odds_api_spreads(store: Store, settings: Settings) -> int:
    if not settings.odds_api_key:
        return 0
    api_games = fetch_spreads(settings.odds_api_key, settings.preferred_book)
    updated = 0
    # Match Odds API events onto ESPN rows by teams + tipoff calendar day (UTC)
    indexed = {
        (g.home_team, g.away_team, g.tipoff_utc[:10]): g
        for g in store.list_games(status="scheduled")
    }
    for og in api_games:
        key = (og.home_team, og.away_team, og.tipoff_utc[:10])
        existing = indexed.get(key)
        if not existing:
            continue
        store.upsert_spread(
            game_id=existing.game_id,
            tipoff_utc=existing.tipoff_utc,
            home_team=existing.home_team,
            away_team=existing.away_team,
            home_spread=og.home_spread,
            spread_source=og.spread_source,
        )
        updated += 1
    return updated


def bootstrap_history(store: Store, days: int = 14, tz_name: str = "America/New_York") -> int:
    """Backfill recent completed games (scores only; spreads must already be stored)."""
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()
    games = fetch_range(today - timedelta(days=days), today)
    n = 0
    for game in games:
        _apply_espn_game(store, game)
        n += 1
    return n


def today_local(tz_name: str) -> date:
    return datetime.now(ZoneInfo(tz_name)).date()
