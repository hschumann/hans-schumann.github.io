"""Fetch NBA schedules, DraftKings spreads, and scores from ESPN's public API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterator

from nba.http_util import get_json
from nba.teams import normalize_abbrev

SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
)
SUMMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"
)


@dataclass
class EspnGame:
    game_id: str
    tipoff_utc: str
    home_team: str
    away_team: str
    home_spread: float | None
    home_score: int | None
    away_score: int | None
    status: str  # scheduled | in_progress | final
    spread_source: str | None


def _parse_line(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip().replace("−", "-").replace("–", "-")
    if not text or text.upper() in {"PK", "PICK", "PICK'EM", "EVEN"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        # ESPN uses OFF when a number is not posted yet.
        return None


def _status_from_espn(event: dict) -> str:
    st = event.get("status", {}).get("type", {})
    if st.get("completed"):
        return "final"
    state = (st.get("state") or "").lower()
    if state == "in":
        return "in_progress"
    return "scheduled"


def _home_spread_from_odds(odds: dict) -> float | None:
    point_spread = odds.get("pointSpread") or {}
    home = point_spread.get("home") or {}
    for bucket in ("close", "open"):
        line = (home.get(bucket) or {}).get("line")
        parsed = _parse_line(line)
        if parsed is not None:
            return parsed

    # Fallback: details like "BOS -1.5" + favorite flags
    details = (odds.get("details") or "").strip()
    if not details:
        return None
    parts = details.replace("−", "-").split()
    if len(parts) < 2:
        return None
    fav_abbr = normalize_abbrev(parts[0])
    fav_line = _parse_line(parts[1])
    if fav_line is None:
        return None
    home_odds = odds.get("homeTeamOdds") or {}
    home_abbr = normalize_abbrev(
        ((home_odds.get("team") or {}).get("abbreviation")) or ""
    )
    if home_abbr == fav_abbr:
        return fav_line if fav_line < 0 else -abs(fav_line)
    # home is dog: opposite sign of favorite's line magnitude
    return abs(fav_line) if fav_line < 0 else -abs(fav_line)


def parse_event(event: dict) -> EspnGame | None:
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    comp = competitions[0]
    competitors = comp.get("competitors") or []
    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if not home or not away:
        return None

    tipoff = event.get("date") or comp.get("date")
    if not tipoff:
        return None
    # Normalize to ISO with Z
    tipoff_utc = tipoff.replace("Z", "+00:00")
    tipoff_dt = datetime.fromisoformat(tipoff_utc).astimezone(timezone.utc)
    tipoff_iso = tipoff_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    home_team = normalize_abbrev(home["team"]["abbreviation"])
    away_team = normalize_abbrev(away["team"]["abbreviation"])

    home_score = away_score = None
    if home.get("score") not in (None, ""):
        home_score = int(home["score"])
    if away.get("score") not in (None, ""):
        away_score = int(away["score"])

    status = _status_from_espn(event)
    home_spread = None
    spread_source = None
    odds_list = comp.get("odds") or []
    if odds_list:
        odds = odds_list[0]
        home_spread = _home_spread_from_odds(odds)
        provider = ((odds.get("provider") or {}).get("name") or "espn").lower()
        spread_source = f"espn:{provider.replace(' ', '')}"

    return EspnGame(
        game_id=str(event["id"]),
        tipoff_utc=tipoff_iso,
        home_team=home_team,
        away_team=away_team,
        home_spread=home_spread,
        home_score=home_score,
        away_score=away_score,
        status=status,
        spread_source=spread_source,
    )


def fetch_scoreboard(day: date | None = None) -> list[EspnGame]:
    url = SCOREBOARD_URL
    if day is not None:
        url = f"{SCOREBOARD_URL}?dates={day.strftime('%Y%m%d')}"
    payload = get_json(url)
    games: list[EspnGame] = []
    for event in payload.get("events") or []:
        parsed = parse_event(event)
        if parsed:
            games.append(parsed)
    return games


def fetch_closing_home_spread(game_id: str) -> tuple[float | None, str | None]:
    """Pull closing home spread from ESPN game summary pickcenter."""
    payload = get_json(f"{SUMMARY_URL}?event={game_id}")
    pickcenter = payload.get("pickcenter") or []
    if not pickcenter:
        return None, None
    odds = pickcenter[0]
    home_spread = _home_spread_from_odds(odds)
    provider = ((odds.get("provider") or {}).get("name") or "espn").lower()
    source = f"espn-summary:{provider.replace(' ', '')}"
    return home_spread, source


def iter_days(start: date, end: date) -> Iterator[date]:
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def fetch_range(start: date, end: date) -> list[EspnGame]:
    out: list[EspnGame] = []
    seen: set[str] = set()
    for day in iter_days(start, end):
        for game in fetch_scoreboard(day):
            if game.game_id in seen:
                continue
            seen.add(game.game_id)
            out.append(game)
    return out
