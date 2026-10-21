#!/usr/bin/env python3
"""Build StatsBomb possession starts, team averages, and page data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from statsbomb.loader import extract_possessions, load_events, possessions_to_zone_summary

EVENTS_DIR = PROJECT_ROOT / "data" / "statsbomb" / "events"
DEFAULT_POSSESSIONS = PROJECT_ROOT / "statsbomb_possessions.csv"
DEFAULT_ZONES = PROJECT_ROOT / "statsbomb_possession_zones.csv"
DEFAULT_TEAM_SUMMARY = PROJECT_ROOT / "statsbomb_team_start_distance.csv"
DEFAULT_PAGE_DATA = PROJECT_ROOT.parent / "epl-distance-from-goal" / "data.js"


def list_local_match_ids() -> list[int]:
    return sorted(int(path.stem) for path in EVENTS_DIR.glob("*.json"))


def home_away_teams(events: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    home = away = None
    for event in events:
        if (event.get("type") or {}).get("name") != "Starting XI":
            continue
        team = (event.get("team") or {}).get("name")
        if event.get("period") != 1:
            continue
        # First Starting XI is home in StatsBomb open data convention for this set.
        if home is None:
            home = team
        elif team != home:
            away = team
            break
    return home, away


def match_points_from_events(events: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Return per-team W/D/L points contribution for one match."""
    home, away = home_away_teams(events)
    if not home or not away:
        return {}

    home_goals = 0
    away_goals = 0
    for event in events:
        if (event.get("type") or {}).get("name") != "Shot":
            continue
        shot = event.get("shot") or {}
        if (shot.get("outcome") or {}).get("name") != "Goal":
            continue
        team = (event.get("team") or {}).get("name")
        own_goal = bool(shot.get("own_goal"))
        if own_goal:
            if team == home:
                away_goals += 1
            elif team == away:
                home_goals += 1
        else:
            if team == home:
                home_goals += 1
            elif team == away:
                away_goals += 1

    if home_goals > away_goals:
        home_pts, away_pts = 3, 0
        home_w, home_d, home_l = 1, 0, 0
        away_w, away_d, away_l = 0, 0, 1
    elif home_goals < away_goals:
        home_pts, away_pts = 0, 3
        home_w, home_d, home_l = 0, 0, 1
        away_w, away_d, away_l = 1, 0, 0
    else:
        home_pts, away_pts = 1, 1
        home_w, home_d, home_l = 0, 1, 0
        away_w, away_d, away_l = 0, 1, 0

    return {
        home: {
            "points": home_pts,
            "w": home_w,
            "d": home_d,
            "l": home_l,
            "gf": home_goals,
            "ga": away_goals,
            "games": 1,
        },
        away: {
            "points": away_pts,
            "w": away_w,
            "d": away_d,
            "l": away_l,
            "gf": away_goals,
            "ga": home_goals,
            "games": 1,
        },
    }


def enrich_possession_shots(events: list[dict[str, Any]], match_id: int) -> list[dict[str, Any]]:
    """Extract possessions and attach per-shot xG lists when a possession ends in shots."""
    base = extract_possessions(events, match_id)

    # Rebuild shot lists keyed by possession id + team for richer detail.
    ordered = sorted(events, key=lambda e: (e.get("period", 0), e.get("timestamp", ""), e.get("index", 0)))
    shot_details: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for event in ordered:
        if (event.get("type") or {}).get("name") != "Shot":
            continue
        possession_id = event.get("possession")
        possession_team = (event.get("possession_team") or {}).get("name")
        if possession_id is None or not possession_team:
            continue
        shot = event.get("shot") or {}
        location = event.get("location") or [None, None]
        shot_details.setdefault((int(possession_id), possession_team), []).append(
            {
                "player": (event.get("player") or {}).get("name"),
                "xg": float(shot.get("statsbomb_xg") or 0.0),
                "outcome": (shot.get("outcome") or {}).get("name"),
                "body_part": (shot.get("body_part") or {}).get("name"),
                "x": location[0],
                "y": location[1],
            }
        )

    enriched: list[dict[str, Any]] = []
    for row in base:
        key = (int(row["possession_id"]), row["possession_team"])
        shots = shot_details.get(key, [])
        row = dict(row)
        row["shot_xg_list"] = "|".join(f"{s['xg']:.6f}" for s in shots)
        row["shot_outcomes"] = "|".join(str(s["outcome"] or "") for s in shots)
        enriched.append(row)
    return enriched


def fit_quadratic(bins: pd.DataFrame) -> np.poly1d:
    usable = bins[bins["n"] >= 30]
    coef = np.polyfit(usable["zone"] + 2.5, usable["avg_xg"], deg=2, w=usable["n"])
    return np.poly1d(coef)


def build_team_summary(possessions: pd.DataFrame, standings: pd.DataFrame) -> pd.DataFrame:
    # Expected xG from start distance via league curve on all possessions.
    possessions = possessions.copy()
    possessions["zone"] = (possessions["yards_from_goal"] // 5) * 5
    bins = (
        possessions.groupby("zone", as_index=False)
        .agg(n=("shot_xg", "count"), avg_xg=("shot_xg", "mean"))
        .sort_values("zone")
    )
    poly = fit_quadratic(bins)
    possessions["expected_xg"] = poly(possessions["yards_from_goal"])
    possessions["resid"] = possessions["shot_xg"] - possessions["expected_xg"]

    summary = (
        possessions.groupby("possession_team", as_index=False)
        .agg(
            possessions=("match_id", "count"),
            matches=("match_id", "nunique"),
            avg_yards_from_goal=("yards_from_goal", "mean"),
            median_yards_from_goal=("yards_from_goal", "median"),
            shot_rate=("had_shot", "mean"),
            avg_xg=("shot_xg", "mean"),
            total_xg=("shot_xg", "sum"),
            avg_resid=("resid", "mean"),
        )
        .rename(columns={"possession_team": "team"})
        .sort_values("avg_yards_from_goal")
    )

    if not standings.empty:
        summary = summary.merge(standings, on="team", how="left")
    else:
        summary["points"] = pd.NA
        summary["games"] = summary["matches"]

    return summary


def export_page_data(
    possessions: pd.DataFrame,
    team_summary: pd.DataFrame,
    output_path: Path,
) -> None:
    possessions = possessions.copy()
    possessions["zone"] = (possessions["yards_from_goal"] // 5) * 5
    bins_frame = (
        possessions.groupby("zone", as_index=False)
        .agg(n=("shot_xg", "count"), avg_xg=("shot_xg", "mean"))
        .sort_values("zone")
    )
    poly = fit_quadratic(bins_frame)

    bins = [
        {
            "yards": float(row.zone + 2.5),
            "avg_xg": round(float(row.avg_xg), 6),
            "n": int(row.n),
        }
        for row in bins_frame.itertuples()
    ]
    curve = [
        {"yards": float(yards), "expected_xg": round(float(max(poly(yards), 0.0)), 6)}
        for yards in range(0, 106)
    ]
    zones = [
        {
            "label": f"{int(row.zone)}-{int(row.zone + 5)}y",
            "yards": float(row.zone),
            "avg_xg": round(float(row.avg_xg), 6),
            "shot_prob": None,
            "n": int(row.n),
        }
        for row in bins_frame.itertuples()
    ]
    teams = []
    for row in team_summary.itertuples():
        teams.append(
            {
                "team": row.team,
                "possessions": int(row.possessions),
                "matches": int(row.matches),
                "avg_yards_from_goal": round(float(row.avg_yards_from_goal), 1),
                "avg_xg": round(float(row.avg_xg), 4),
                "avg_resid": round(float(row.avg_resid), 4),
                "shot_rate": round(float(row.shot_rate), 4),
                "points": int(row.points) if pd.notna(row.points) else None,
                "games": int(row.games) if pd.notna(row.games) else int(row.matches),
            }
        )

    payload = {
        "statsbomb_season": "2015/16 Premier League (StatsBomb open data, full season)",
        "fotmob_window": None,
        "curve_kind": "possession_start_distance",
        "bins": bins,
        "poly_coef": [float(c) for c in poly.coefficients],
        "curve": curve,
        "zones": zones,
        "teams": teams,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "window.EPL_DISTANCE_DATA = " + json.dumps(payload, indent=2) + ";\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build StatsBomb possession start-distance dataset.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--possessions-output", type=Path, default=DEFAULT_POSSESSIONS)
    parser.add_argument("--zones-output", type=Path, default=DEFAULT_ZONES)
    parser.add_argument("--team-summary-output", type=Path, default=DEFAULT_TEAM_SUMMARY)
    parser.add_argument("--page-data", type=Path, default=DEFAULT_PAGE_DATA)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    match_ids = list_local_match_ids()
    if args.limit is not None:
        match_ids = match_ids[: args.limit]
    if not match_ids:
        print(f"No event files found in {EVENTS_DIR}")
        return 1

    print(f"Processing {len(match_ids)} StatsBomb matches...")
    all_possessions: list[dict[str, Any]] = []
    standing_rows: list[dict[str, Any]] = []

    for index, match_id in enumerate(match_ids, start=1):
        print(f"[{index}/{len(match_ids)}] match {match_id}", flush=True)
        events = load_events(match_id)
        all_possessions.extend(enrich_possession_shots(events, match_id))
        for team, stats in match_points_from_events(events).items():
            standing_rows.append({"team": team, **stats})

    possessions = pd.DataFrame(all_possessions)
    zones = possessions_to_zone_summary(all_possessions, bin_width_yards=10.0)

    if standing_rows:
        standings = (
            pd.DataFrame(standing_rows)
            .groupby("team", as_index=False)
            .agg(
                points=("points", "sum"),
                w=("w", "sum"),
                d=("d", "sum"),
                l=("l", "sum"),
                gf=("gf", "sum"),
                ga=("ga", "sum"),
                games=("games", "sum"),
            )
        )
        standings["gd"] = standings["gf"] - standings["ga"]
    else:
        standings = pd.DataFrame(columns=["team", "points", "games"])

    team_summary = build_team_summary(possessions, standings)

    # CSV-friendly: keep shot lists as strings already
    possessions.to_csv(args.possessions_output, index=False)
    zones.to_csv(args.zones_output, index=False)
    team_summary.to_csv(args.team_summary_output, index=False)
    export_page_data(possessions, team_summary, args.page_data)

    print()
    print(f"Saved {len(possessions)} possessions -> {args.possessions_output}")
    print(f"Saved zones -> {args.zones_output}")
    print(f"Saved team summary -> {args.team_summary_output}")
    print(f"Updated page data -> {args.page_data}")
    print("\nClosest average starts:")
    print(
        team_summary[
            ["team", "matches", "avg_yards_from_goal", "avg_xg", "avg_resid", "points"]
        ]
        .head(8)
        .to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
