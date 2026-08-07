from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from statsbomb.config import DATA_ROOT, EVENTS_DIR, MATCHES_DIR

PITCH_LENGTH = 120.0
PITCH_WIDTH = 80.0
YARDS_PER_UNIT = 105.0 / PITCH_LENGTH
OPEN_DATA_RAW = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
CACHE_EVENTS_DIR = DATA_ROOT / "events"

# Restarts that begin from fixed deep positions and are not representative
# of field position after winning live possession.
EXCLUDED_PLAY_PATTERNS = frozenset({"From Penalty", "From Goal Kick"})


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def fetch_json(url: str) -> Any:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.json()


def load_events(match_id: int) -> list[dict[str, Any]]:
    cached = CACHE_EVENTS_DIR / f"{match_id}.json"
    if cached.exists():
        return load_json(cached)

    local = EVENTS_DIR / f"{match_id}.json"
    if local.exists():
        return load_json(local)

    events = fetch_json(f"{OPEN_DATA_RAW}/events/{match_id}.json")
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(events), encoding="utf-8")
    return events


def match_ids_for_season(competition_id: int, season_id: int) -> list[int]:
    season_dir = MATCHES_DIR / str(competition_id) / str(season_id)
    if season_dir.exists():
        match_ids: list[int] = []
        for path in sorted(season_dir.glob("*.json")):
            payload = load_json(path)
            if isinstance(payload, list) and payload:
                match_ids.append(int(payload[0]["match_id"]))
            else:
                match_ids.append(int(path.stem))
        return match_ids

    matches = fetch_json(f"{OPEN_DATA_RAW}/matches/{competition_id}/{season_id}.json")
    return [int(match["match_id"]) for match in matches]


def load_matches(competition_id: int, season_id: int) -> list[dict[str, Any]]:
    season_dir = MATCHES_DIR / str(competition_id) / str(season_id)
    if season_dir.exists():
        matches: list[dict[str, Any]] = []
        for path in sorted(season_dir.glob("*.json")):
            payload = load_json(path)
            if isinstance(payload, list):
                matches.extend(payload)
            else:
                matches.append(payload)
        return matches

    return fetch_json(f"{OPEN_DATA_RAW}/matches/{competition_id}/{season_id}.json")


def team_attacks_high_x(events: list[dict[str, Any]], team_name: str) -> bool:
    xs: list[float] = []
    for event in events:
        if event.get("period") != 1:
            continue
        if (event.get("team") or {}).get("name") != team_name:
            continue
        location = event.get("location")
        if location:
            xs.append(float(location[0]))

    if not xs:
        return True

    return sum(xs) / len(xs) >= PITCH_LENGTH / 2


def to_attacking_x(raw_x: float, team_name: str, attacks_high: dict[str, bool]) -> float:
    if attacks_high.get(team_name, True):
        return raw_x
    return PITCH_LENGTH - raw_x


def yards_from_opponent_goal(attacking_x: float) -> float:
    return (PITCH_LENGTH - attacking_x) * YARDS_PER_UNIT


def first_located_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in events:
        if event.get("location"):
            return event
    return None


def is_penalty_shot(event: dict[str, Any]) -> bool:
    if (event.get("type") or {}).get("name") != "Shot":
        return False
    return ((event.get("shot") or {}).get("type") or {}).get("name") == "Penalty"


def extract_possessions(events: list[dict[str, Any]], match_id: int) -> list[dict[str, Any]]:
    if not events:
        return []

    # StatsBomb event locations are already oriented so the team in possession
    # attacks toward x = 120. Do not flip by half-time average position.
    ordered = sorted(events, key=lambda e: (e.get("period", 0), e.get("timestamp", ""), e.get("index", 0)))

    grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for event in ordered:
        possession_id = event.get("possession")
        possession_team = (event.get("possession_team") or {}).get("name")
        if possession_id is None or not possession_team:
            continue
        grouped.setdefault((int(possession_id), possession_team), []).append(event)

    possessions: list[dict[str, Any]] = []
    for (possession_id, possession_team), possession_events in grouped.items():
        play_pattern = (possession_events[0].get("play_pattern") or {}).get("name", "")
        if play_pattern in EXCLUDED_PLAY_PATTERNS:
            continue

        # Penalty kicks (and their rebound sequences) sit on the spot ~10–12 yards
        # out with ~0.78 xG and blow up the near-box curve bins.
        if any(is_penalty_shot(event) for event in possession_events):
            continue

        start_event = first_located_event(possession_events)
        if start_event is None:
            continue

        start_x = float(start_event["location"][0])
        start_y_raw = float(start_event["location"][1])

        shots = [
            event
            for event in possession_events
            if (event.get("type") or {}).get("name") == "Shot" and not is_penalty_shot(event)
        ]
        shot_xg = sum(float((event.get("shot") or {}).get("statsbomb_xg") or 0.0) for event in shots)

        possessions.append(
            {
                "match_id": match_id,
                "possession_id": possession_id,
                "possession_team": possession_team,
                "play_pattern": play_pattern,
                "start_x": start_x,
                "start_y": start_y_raw,
                "yards_from_goal": yards_from_opponent_goal(start_x),
                "had_shot": len(shots) > 0,
                "shot_count": len(shots),
                "shot_xg": shot_xg,
            }
        )

    return possessions


def possessions_to_zone_summary(
    possessions: list[dict[str, Any]],
    bin_width_yards: float = 10.0,
) -> pd.DataFrame:
    frame = pd.DataFrame(possessions)
    if frame.empty:
        return frame

    max_yards = 105.0
    frame["zone_start_yards"] = (frame["yards_from_goal"] // bin_width_yards) * bin_width_yards
    frame["zone_end_yards"] = frame["zone_start_yards"] + bin_width_yards
    frame["zone_label"] = frame.apply(
        lambda row: f"{int(row['zone_start_yards'])}-{int(row['zone_end_yards'])}y",
        axis=1,
    )

    summary = frame.groupby("zone_label", as_index=False).agg(
        zone_start_yards=("zone_start_yards", "first"),
        possessions=("match_id", "count"),
        shots=("had_shot", "sum"),
        total_xg=("shot_xg", "sum"),
    )
    summary["shot_probability"] = summary["shots"] / summary["possessions"]
    summary["avg_xg_per_possession"] = summary["total_xg"] / summary["possessions"]
    summary["avg_xg_per_shot"] = summary["total_xg"] / summary["shots"].replace(0, pd.NA)
    summary = summary.sort_values("zone_start_yards").reset_index(drop=True)
    return summary
