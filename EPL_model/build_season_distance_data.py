#!/usr/bin/env python3
"""Fetch 2025/26 EPL shots and build xG vs starting distance from goal."""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path
from typing import Any

from fotmob_api import FotmobAPI

from fotmob_utils import is_penalty_shot, parse_season_arg, shot_sort_key, shot_to_row

PREMIER_LEAGUE_ID = 47
DEFAULT_SEASON = "2025/2026"
# FotMob shotmaps use attacking orientation for every team; x increases toward
# the goal being attacked. Values can exceed 100 because the pitch is ~105 long.
PITCH_LENGTH = 105.0
PROJECT_ROOT = Path(__file__).resolve().parent
SITE_ROOT = PROJECT_ROOT.parent
DEFAULT_SHOTS_OUTPUT = PROJECT_ROOT / "epl_2025_26_shots.csv"
DEFAULT_POSSESSIONS_OUTPUT = PROJECT_ROOT / "epl_2025_26_possessions.csv"
DEFAULT_ZONES_OUTPUT = PROJECT_ROOT / "epl_2025_26_possession_zones.csv"
DEFAULT_PAGE_DATA = SITE_ROOT / "epl-distance-from-goal" / "data.js"
CACHE_DIR = PROJECT_ROOT / "data" / "fotmob" / "matches"


def yards_from_goal(attacking_x: float) -> float:
    return max(0.0, PITCH_LENGTH - float(attacking_x))


def load_cached_match(match_id: int) -> dict[str, Any] | None:
    path = CACHE_DIR / f"{match_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_cached_match(match_id: int, payload: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{match_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")


def get_match_details(client: FotmobAPI, match_id: int, use_cache: bool) -> dict[str, Any]:
    if use_cache:
        cached = load_cached_match(match_id)
        if cached is not None:
            return cached
    details = client.get_match_details(match_id=match_id)
    if use_cache:
        save_cached_match(match_id, details)
    return details


def extract_possessions_fotmob(
    shots: list[dict[str, Any]],
    home_team_id: int,
    away_team_id: int,
) -> list[dict[str, Any]]:
    """
    Approximate possessions from shot sequences.

    FotMob shot x is already attacking-oriented for each shooting team, so a
    higher x is always closer to the opponent goal. When possession changes,
    mirror the previous shot location onto the new team's attacking axis.
    """
    if not shots:
        return []

    ordered = sorted(shots, key=shot_sort_key)
    possessions: list[dict[str, Any]] = []

    for index, shot in enumerate(ordered):
        if is_penalty_shot(shot):
            continue
        if shot.get("x") is None:
            continue

        team_id = int(shot["teamId"])
        end_x = float(shot["x"])
        end_y = float(shot.get("y") or 50.0)

        if index == 0:
            start_x = PITCH_LENGTH / 2.0
            start_y = 50.0
        else:
            previous = ordered[index - 1]
            previous_team_id = int(previous["teamId"])
            previous_x = float(previous["x"])
            previous_y = float(previous.get("y") or 50.0)

            if previous_team_id == team_id:
                start_x = previous_x
                start_y = previous_y
            else:
                start_x = max(0.0, min(PITCH_LENGTH, PITCH_LENGTH - previous_x))
                start_y = previous_y

        possessions.append(
            {
                "team_id": team_id,
                "team": "home" if team_id == home_team_id else "away",
                "start_x": start_x,
                "start_y": start_y,
                "end_x": end_x,
                "end_y": end_y,
                "yards_from_goal": yards_from_goal(start_x),
                "shot_yards_from_goal": yards_from_goal(end_x),
                "xg": float(shot.get("expectedGoals") or 0.0),
            }
        )

    return possessions


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    if not rows:
        raise ValueError(f"No rows to write to {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def bin_by_distance(
    rows: list[dict[str, Any]],
    distance_key: str,
    bin_width: float,
    max_yards: float | None = None,
) -> list[dict[str, Any]]:
    buckets: dict[float, dict[str, float]] = {}
    for row in rows:
        distance = float(row[distance_key])
        if max_yards is not None and distance > max_yards:
            continue
        start = math.floor(distance / bin_width) * bin_width
        bucket = buckets.setdefault(start, {"count": 0.0, "total_xg": 0.0})
        bucket["count"] += 1
        bucket["total_xg"] += float(row["xg"])

    zones: list[dict[str, Any]] = []
    for start in sorted(buckets):
        bucket = buckets[start]
        n = bucket["count"]
        avg = bucket["total_xg"] / n if n else 0.0
        zones.append(
            {
                "zone_label": f"{int(start)}-{int(start + bin_width)}y",
                "zone_start_yards": start,
                "possessions": int(n),
                "shots": int(n),
                "total_xg": bucket["total_xg"],
                "shot_probability": 1.0,
                "avg_xg_per_possession": avg,
                "avg_xg_per_shot": avg,
            }
        )
    return zones


def fit_quadratic(zones: list[dict[str, Any]], bin_width: float = 5.0) -> list[float]:
    usable = [z for z in zones if z["possessions"] >= 50]
    xs = [z["zone_start_yards"] + bin_width / 2.0 for z in usable]
    ys = [z["avg_xg_per_possession"] for z in usable]
    if len(xs) < 3:
        mean_y = sum(ys) / len(ys) if ys else 0.0
        return [0.0, 0.0, mean_y]

    try:
        import numpy as np

        weights = [max(z["possessions"], 1) for z in usable]
        coef = np.polyfit(xs, ys, deg=2, w=weights)
        return [float(c) for c in coef]
    except Exception:
        return [0.0, 0.0, sum(ys) / len(ys)]


def team_rankings(possession_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    start_values = [row["start_x"] for row in possession_rows]
    xg_values = [row["xg"] for row in possession_rows]
    mean_x = sum(start_values) / len(start_values)
    mean_y = sum(xg_values) / len(xg_values)
    denom = sum((x - mean_x) ** 2 for x in start_values) or 1.0
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(start_values, xg_values)) / denom
    intercept = mean_y - slope * mean_x

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in possession_rows:
        grouped.setdefault(row["team"], []).append(row)

    rankings: list[dict[str, Any]] = []
    for team, rows in grouped.items():
        avg_yards = sum(r["yards_from_goal"] for r in rows) / len(rows)
        avg_xg = sum(r["xg"] for r in rows) / len(rows)
        avg_resid = sum(r["xg"] - (intercept + slope * r["start_x"]) for r in rows) / len(rows)
        rankings.append(
            {
                "team": team,
                "possessions": len(rows),
                "avg_yards_from_goal": round(avg_yards, 1),
                "avg_xg": round(avg_xg, 4),
                "avg_resid": round(avg_resid, 4),
            }
        )

    rankings.sort(key=lambda row: row["avg_yards_from_goal"])
    return rankings


def export_page_data(
    start_zones: list[dict[str, Any]],
    poly_coef: list[float],
    rankings: list[dict[str, Any]],
    output_path: Path,
    match_count: int,
) -> None:
    a, b, c = poly_coef
    bins = []
    for zone in start_zones:
        if zone["possessions"] < 10:
            continue
        yards = float(zone["zone_start_yards"]) + 2.5
        bins.append(
            {
                "yards": yards,
                "avg_xg": round(float(zone["avg_xg_per_possession"]), 6),
                "n": int(zone["possessions"]),
            }
        )

    curve = []
    for yards in range(0, 106):
        expected = max(0.0, a * (yards**2) + b * yards + c)
        curve.append({"yards": float(yards), "expected_xg": round(float(expected), 6)})

    payload = {
        "statsbomb_season": None,
        "fotmob_window": f"2025/26 Premier League, full season ({match_count} matches)",
        "curve_kind": "possession_start_distance",
        "bins": bins,
        "poly_coef": poly_coef,
        "curve": curve,
        "zones": [
            {
                "label": z["zone_label"],
                "yards": float(z["zone_start_yards"]),
                "avg_xg": round(float(z["avg_xg_per_possession"]), 6),
                "shot_prob": 1.0,
                "n": int(z["possessions"]),
            }
            for z in start_zones
        ],
        "teams": rankings,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "window.EPL_DISTANCE_DATA = " + json.dumps(payload, indent=2) + ";\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build 2025/26 xG vs distance-from-goal data.")
    parser.add_argument("--season", default=DEFAULT_SEASON)
    parser.add_argument("--shots-output", type=Path, default=DEFAULT_SHOTS_OUTPUT)
    parser.add_argument("--possessions-output", type=Path, default=DEFAULT_POSSESSIONS_OUTPUT)
    parser.add_argument("--zones-output", type=Path, default=DEFAULT_ZONES_OUTPUT)
    parser.add_argument("--page-data", type=Path, default=DEFAULT_PAGE_DATA)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.05, help="Pause between uncached requests")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    season = parse_season_arg(args.season)
    client = FotmobAPI()
    use_cache = not args.no_cache

    fixtures = client.get_fixtures(id=PREMIER_LEAGUE_ID, season=season)
    if args.limit is not None:
        fixtures = fixtures[: args.limit]

    print(f"Fetching shotmaps for {len(fixtures)} fixtures ({season})")
    started = time.time()

    shot_rows: list[dict[str, Any]] = []
    possession_rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for index, fixture in enumerate(fixtures, start=1):
        match_id = int(fixture["id"])
        home = fixture["home"]["name"]
        away = fixture["away"]["name"]
        home_team_id = int(fixture["home"]["id"])
        away_team_id = int(fixture["away"]["id"])
        date = fixture.get("status", {}).get("utcTime", "")[:10]
        gameweek = ((index - 1) // 10) + 1

        cached = use_cache and load_cached_match(match_id) is not None
        print(f"[{index}/{len(fixtures)}] GW{gameweek} {home} vs {away}" + (" [cache]" if cached else ""), flush=True)

        try:
            details = get_match_details(client, match_id, use_cache=use_cache)
            shots = details.get("content", {}).get("shotmap", {}).get("shots", []) or []
        except Exception as error:
            skipped.append({"match_id": match_id, "reason": str(error)})
            continue

        if not shots:
            skipped.append({"match_id": match_id, "reason": "missing shotmap"})
            continue

        if not cached and args.sleep > 0:
            time.sleep(args.sleep)

        for shot in shots:
            shot_rows.append(
                shot_to_row(
                    shot=shot,
                    match_id=match_id,
                    date=date,
                    home_team=home,
                    away_team=away,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                )
            )

        possessions = extract_possessions_fotmob(shots, home_team_id, away_team_id)
        team_name = {home_team_id: home, away_team_id: away}
        for possession in possessions:
            possession_rows.append(
                {
                    "match_id": match_id,
                    "date": date,
                    "gameweek": gameweek,
                    "team": team_name[possession["team_id"]],
                    "is_home": possession["team_id"] == home_team_id,
                    "start_x": possession["start_x"],
                    "start_y": possession["start_y"],
                    "end_x": possession["end_x"],
                    "end_y": possession["end_y"],
                    "yards_from_goal": possession["yards_from_goal"],
                    "shot_yards_from_goal": possession["shot_yards_from_goal"],
                    "xg": possession["xg"],
                }
            )

    if not possession_rows:
        print("No possessions extracted.")
        return 1

    start_zones_10 = bin_by_distance(possession_rows, "yards_from_goal", bin_width=10.0)
    start_zones_5 = bin_by_distance(possession_rows, "yards_from_goal", bin_width=5.0)
    poly_coef = fit_quadratic(start_zones_5, bin_width=5.0)
    rankings = team_rankings(possession_rows)

    write_csv(shot_rows, args.shots_output)
    write_csv(possession_rows, args.possessions_output)
    write_csv(start_zones_10, args.zones_output)
    export_page_data(
        start_zones=start_zones_5,
        poly_coef=poly_coef,
        rankings=rankings,
        output_path=args.page_data,
        match_count=len({row["match_id"] for row in possession_rows}),
    )

    print()
    print(f"Saved {len(shot_rows)} shots -> {args.shots_output}")
    print(f"Saved {len(possession_rows)} possessions -> {args.possessions_output}")
    print(f"Saved zone summary -> {args.zones_output}")
    print(f"Updated page data -> {args.page_data}")
    if skipped:
        print(f"Skipped {len(skipped)} matches")
    print(f"Done in {time.time() - started:.1f}s")
    print("Top 5 closest avg starts:")
    for row in rankings[:5]:
        print(f"  {row['team']:<16} {row['avg_yards_from_goal']:5.1f}y  resid {row['avg_resid']:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
