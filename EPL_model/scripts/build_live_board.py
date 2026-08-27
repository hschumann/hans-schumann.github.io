#!/usr/bin/env python3
"""Build live HT board from FotMob + odds.json (GitHub Pages fallback)."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from football_data.team_names import ALIASES
from models.odds_half_goals import expected_goals_from_odds, predicted_final_from_halftime

DEFAULT_ODDS = PROJECT_ROOT.parent / "epl-halftime-bets" / "odds.json"
DEFAULT_OUTPUT = PROJECT_ROOT.parent / "epl-halftime-bets" / "board.json"
FOTMOB_MATCHES = "https://www.fotmob.com/api/data/matches"
FOTMOB_MATCH = "https://www.fotmob.com/api/data/matchDetails"
PREMIER_LEAGUE_ID = 47
NO_BET_THRESHOLD = 0.5
PHASE_ORDER = {
    "halftime": 0,
    "first_half": 1,
    "second_half": 2,
    "not_started": 3,
    "finished": 4,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build live EPL HT board from FotMob.")
    parser.add_argument("--odds", type=Path, default=DEFAULT_ODDS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--date", help="UTC date YYYYMMDD (default: today + yesterday)")
    return parser


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "epl-halftime-bets/1.0", "Accept": "application/json"},
    )
    try:
        import ssl

        context = ssl.create_default_context()
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError:
        import subprocess

        result = subprocess.run(
            ["curl", "-fsSL", url],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)


def normalize_team(name: str) -> str:
    cleaned = (name or "").strip()
    return ALIASES.get(cleaned, cleaned)


def parse_score(score_str: str | None) -> tuple[int, int] | None:
    if not score_str:
        return None
    parts = [part.strip() for part in str(score_str).split("-")]
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def classify_phase(status: dict, reason: dict) -> str:
    key = str(reason.get("shortKey") or "").lower()
    short = str(reason.get("short") or "").lower()
    long_key = str(reason.get("longKey") or "").lower()
    halfs = status.get("halfs") or {}

    if not status.get("started"):
        return "not_started"
    if status.get("finished") or "fulltime" in key or "finished" in long_key:
        return "finished"

    at_halftime = (
        "halftime" in key
        or short == "ht"
        or "halftime" in long_key
        or "pause" in key
        or (bool(halfs.get("firstHalfEnded")) and not halfs.get("secondHalfStarted"))
    )
    if at_halftime:
        return "halftime"
    if halfs.get("secondHalfStarted"):
        return "second_half"
    return "first_half"


def is_first_half_goal(goal: dict) -> bool:
    period = (goal.get("shotmapEvent") or {}).get("period")
    if period == "FirstHalf":
        return True
    minute = goal.get("time")
    if minute is None:
        minute = goal.get("timeStr", 999)
    try:
        return float(minute) <= 45
    except (TypeError, ValueError):
        return False


def halftime_score_from_events(details: dict) -> tuple[int, int]:
    events = (details.get("header") or {}).get("events") or {}
    home = 0
    away = 0

    for goal_list in (events.get("homeTeamGoals") or {}).values():
        for goal in goal_list:
            if is_first_half_goal(goal):
                home += 1
    for goal_list in (events.get("awayTeamGoals") or {}).values():
        for goal in goal_list:
            if is_first_half_goal(goal):
                away += 1

    if home + away > 0:
        return home, away

    shots = ((details.get("content") or {}).get("shotmap") or {}).get("shots") or []
    home_id = (
        ((details.get("general") or {}).get("homeTeam") or {}).get("id")
        or ((details.get("header") or {}).get("teams") or [{}])[0].get("id")
    )
    for shot in shots:
        if shot.get("period") != "FirstHalf":
            continue
        if str(shot.get("eventType") or "").lower() != "goal":
            continue
        if int(shot.get("teamId") or -1) == int(home_id or -2):
            home += 1
        else:
            away += 1
    return home, away


def find_odds(fixtures: list[dict], date: str, home: str, away: str) -> dict | None:
    match_date = (date or "")[:10]
    for fixture in fixtures:
        if (
            fixture.get("date") == match_date
            and normalize_team(fixture.get("home_team", "")) == home
            and normalize_team(fixture.get("away_team", "")) == away
        ):
            return fixture
    return None


def recommend(pred_total: float) -> dict:
    edge = pred_total - 2.5
    if edge >= NO_BET_THRESHOLD:
        return {"call": "over", "label": "OVER", "edge": edge}
    if edge <= -NO_BET_THRESHOLD:
        return {"call": "under", "label": "UNDER", "edge": edge}
    return {"call": "no_bet", "label": "NO BET", "edge": edge}


def extract_premier_league_matches(payload: dict) -> list[dict]:
    rows = []
    for league in payload.get("leagues") or []:
        league_id = league.get("id") or league.get("primaryId")
        if league_id != PREMIER_LEAGUE_ID:
            continue
        rows.extend(league.get("matches") or [])
    return rows


def enrich_match(match: dict, odds_payload: dict) -> dict:
    status = match.get("status") or {}
    reason = status.get("reason") or {}
    phase = classify_phase(status, reason)
    home_name = normalize_team(match.get("home", {}).get("name", ""))
    away_name = normalize_team(match.get("away", {}).get("name", ""))
    kickoff = (status.get("utcTime") or "")[:10]
    score = parse_score(status.get("scoreStr"))

    row = {
        "match_id": match.get("id"),
        "home_team": home_name,
        "away_team": away_name,
        "kickoff_utc": status.get("utcTime"),
        "phase": phase,
        "status_label": reason.get("long") or reason.get("short") or phase,
        "score_str": status.get("scoreStr") or "–",
        "ht_home": None,
        "ht_away": None,
        "pred_ft_home": None,
        "pred_ft_away": None,
        "pred_total": None,
        "call": None,
        "call_label": None,
        "edge": None,
        "live_call": False,
        "odds_matched": False,
    }

    fixtures = odds_payload.get("fixtures") or []
    odds = find_odds(fixtures, kickoff, home_name, away_name)
    if odds:
        row["odds_matched"] = True
        row["fair_home"] = odds.get("fair_home")
        row["fair_over_2_5"] = odds.get("fair_over_2_5")

    if phase == "not_started" or score is None:
        return row

    ht_home, ht_away = score

    if phase == "halftime":
        row["ht_home"] = ht_home
        row["ht_away"] = ht_away
    elif phase in {"second_half", "finished", "first_half"}:
        try:
            details = fetch_json(f"{FOTMOB_MATCH}?matchId={match.get('id')}")
            ht_from_events = halftime_score_from_events(details)
            if phase == "first_half":
                row["ht_home"] = ht_home
                row["ht_away"] = ht_away
            elif ht_from_events[0] + ht_from_events[1] > 0 or phase == "finished":
                row["ht_home"], row["ht_away"] = ht_from_events
            else:
                row["ht_home"] = ht_home
                row["ht_away"] = ht_away
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            row["ht_home"] = ht_home
            row["ht_away"] = ht_away

    if not odds or row["ht_home"] is None:
        return row

    expected = expected_goals_from_odds(odds["fair_home"], odds["fair_over_2_5"])
    pred_home, pred_away = predicted_final_from_halftime(
        row["ht_home"],
        row["ht_away"],
        expected["expected_2h_home"],
        expected["expected_2h_away"],
    )
    pred_total = pred_home + pred_away
    bet = recommend(pred_total)
    row["pred_ft_home"] = round(pred_home, 2)
    row["pred_ft_away"] = round(pred_away, 2)
    row["pred_total"] = round(pred_total, 2)
    row["call"] = bet["call"]
    row["call_label"] = bet["label"]
    row["edge"] = round(bet["edge"], 2)

    if phase == "halftime":
        row["live_call"] = True
    elif phase in {"second_half", "finished"}:
        row["call_note"] = "HT window passed — shown for tracking only"

    return row


def utc_dates(date_arg: str | None) -> list[str]:
    if date_arg:
        return [date_arg]
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y%m%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y%m%d")
    return [today, yesterday]


def main() -> int:
    args = build_parser().parse_args()
    if not args.odds.exists():
        print(f"Missing odds file: {args.odds}", file=sys.stderr)
        return 1

    odds_payload = json.loads(args.odds.read_text(encoding="utf-8"))
    dates = utc_dates(args.date)
    seen: set[int] = set()
    pl_matches: list[dict] = []

    for date in dates:
        payload = fetch_json(f"{FOTMOB_MATCHES}?date={date}&ccode3=ENG")
        for match in extract_premier_league_matches(payload):
            match_id = match.get("id")
            if match_id in seen:
                continue
            seen.add(match_id)
            pl_matches.append(match)

    rows = [enrich_match(match, odds_payload) for match in pl_matches]
    rows.sort(
        key=lambda row: (
            PHASE_ORDER.get(row["phase"], 9),
            row.get("kickoff_utc") or "",
        )
    )

    live_calls = [row for row in rows if row.get("live_call")]
    board = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "mode": "live",
        "dates_fetched": [
            f"{d[:4]}-{d[4:6]}-{d[6:8]}" for d in dates
        ],
        "source": "fotmob + football-data odds snapshot",
        "disclaimer": (
            "Research tool only — not betting advice. "
            "Live calls appear at halftime only."
        ),
        "rules": {
            "line": 2.5,
            "over": f"pred_total >= {2.5 + NO_BET_THRESHOLD}",
            "under": f"pred_total <= {2.5 - NO_BET_THRESHOLD}",
            "no_bet": f"within ±{NO_BET_THRESHOLD} of 2.5",
        },
        "live_call_count": len(live_calls),
        "matches": rows,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(board, indent=2), encoding="utf-8")
    print(
        f"Wrote {len(rows)} matches ({len(live_calls)} live HT calls) -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
