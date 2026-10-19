"""Optional The Odds API client (FanDuel / DraftKings) as a spread fallback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode

from nba.http_util import get_json
from nba.teams import normalize_team_name

ODDS_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"


@dataclass
class OddsApiGame:
    game_id: str
    tipoff_utc: str
    home_team: str
    away_team: str
    home_spread: float
    spread_source: str


def fetch_spreads(api_key: str, preferred_book: str = "draftkings") -> list[OddsApiGame]:
    if not api_key:
        return []
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": "spreads",
        "oddsFormat": "american",
        "bookmakers": preferred_book,
    }
    url = f"{ODDS_URL}?{urlencode(params)}"
    payload = get_json(url)
    games: list[OddsApiGame] = []
    for event in payload:
        home_name = event["home_team"]
        away_name = event["away_team"]
        home_team = normalize_team_name(home_name)
        away_team = normalize_team_name(away_name)
        tip = datetime.fromisoformat(
            event["commence_time"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        tipoff = tip.replace(microsecond=0).isoformat().replace("+00:00", "Z")

        home_spread = None
        source = None
        for book in event.get("bookmakers") or []:
            for market in book.get("markets") or []:
                if market.get("key") != "spreads":
                    continue
                for outcome in market.get("outcomes") or []:
                    if outcome.get("name") == home_name and "point" in outcome:
                        home_spread = float(outcome["point"])
                        source = f"oddsapi:{book.get('key')}"
                        break
            if home_spread is not None:
                break
        if home_spread is None:
            continue
        games.append(
            OddsApiGame(
                game_id=event["id"],
                tipoff_utc=tipoff,
                home_team=home_team,
                away_team=away_team,
                home_spread=home_spread,
                spread_source=source or f"oddsapi:{preferred_book}",
            )
        )
    return games
