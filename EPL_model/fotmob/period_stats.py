"""Extract half-level match stats from cached FotMob match JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STAT_KEYS = {
    "total_shots": "shots",
    "ShotsOnTarget": "shots_on_target",
    "corners": "corners",
}

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "fotmob" / "matches"


def _parse_stat_value(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def extract_period_stat_map(period_data: dict[str, Any]) -> dict[str, int]:
    """Return home/away values for shots, SOT, corners in one period block."""
    values: dict[str, int | None] = {label: None for label in STAT_KEYS.values()}
    for group in period_data.get("stats", []):
        for stat in group.get("stats", []):
            key = stat.get("key")
            if key not in STAT_KEYS:
                continue
            stats = stat.get("stats") or []
            if len(stats) < 2:
                continue
            home_value = _parse_stat_value(stats[0])
            away_value = _parse_stat_value(stats[1])
            label = STAT_KEYS[key]
            values[f"home_{label}"] = home_value
            values[f"away_{label}"] = away_value
    return values


def extract_match_period_stats(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Parse one FotMob match payload into HT and 2H team stat rows."""
    header = payload.get("header", {})
    teams = header.get("teams", [])
    if len(teams) < 2:
        return None

    home_name = teams[0].get("name")
    away_name = teams[1].get("name")
    general = payload.get("general", {})
    match_id = general.get("matchId") or payload.get("general", {}).get("matchId")
    status = header.get("status", {})
    utc = status.get("utcTime", "")
    date = utc[:10] if utc else None

    periods = payload.get("content", {}).get("stats", {}).get("Periods", {})
    first_half = extract_period_stat_map(periods.get("FirstHalf", {}))
    second_half = extract_period_stat_map(periods.get("SecondHalf", {}))

    if not first_half and not second_half:
        return None

    row: dict[str, Any] = {
        "match_id": match_id,
        "date": date,
        "home_team": home_name,
        "away_team": away_name,
        "home_score": teams[0].get("score"),
        "away_score": teams[1].get("score"),
    }

    for prefix, period_values in (("ht", first_half), ("h2", second_half)):
        for stat_label in STAT_KEYS.values():
            row[f"{prefix}_home_{stat_label}"] = period_values.get(f"home_{stat_label}")
            row[f"{prefix}_away_{stat_label}"] = period_values.get(f"away_{stat_label}")

    return row


def load_cached_match_stats(cache_dir: Path = DEFAULT_CACHE_DIR) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(cache_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        parsed = extract_match_period_stats(payload)
        if parsed is not None:
            parsed["match_id"] = int(path.stem)
            rows.append(parsed)
    return rows


def period_stats_dataframe(cache_dir: Path = DEFAULT_CACHE_DIR) -> pd.DataFrame:
    import pandas as pd

    rows = load_cached_match_stats(cache_dir)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame.sort_values(["date", "match_id"]).reset_index(drop=True)
