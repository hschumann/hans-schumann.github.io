#!/usr/bin/env python3
"""Build Women's World Cup 2019+2023 possession starts for the site page."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from statsbomb.loader import (
    extract_possessions,
    load_events,
    load_matches,
    possessions_to_zone_summary,
)

COMPETITION_ID = 72  # Women's World Cup
SEASONS = (
    {"season_id": 30, "year": "2019"},
    {"season_id": 107, "year": "2023"},
)

SHORT_NAMES = {
    "United States Women's": "USA",
    "United States": "USA",
    "England Women's": "England",
    "France Women's": "France",
    "Germany Women's": "Germany",
    "Spain Women's": "Spain",
    "Brazil Women's": "Brazil",
    "Japan Women's": "Japan",
    "Canada Women's": "Canada",
    "Australia Women's": "Australia",
    "Netherlands Women's": "Netherlands",
    "Sweden Women's": "Sweden",
    "Norway Women's": "Norway",
    "Italy Women's": "Italy",
    "China PR Women's": "China PR",
    "Korea Republic Women's": "Korea Republic",
    "South Africa Women's": "South Africa",
    "Nigeria Women's": "Nigeria",
    "Jamaica Women's": "Jamaica",
    "Argentina Women's": "Argentina",
    "New Zealand Women's": "New Zealand",
    "Scotland Women's": "Scotland",
    "Scotland W": "Scotland",
    "Chile Women's": "Chile",
    "Thailand Women's": "Thailand",
    "Thailand W": "Thailand",
    "Cameroon Women's": "Cameroon",
    "Cameroon W": "Cameroon",
    "Morocco Women's": "Morocco",
    "Colombia Women's": "Colombia",
    "Switzerland Women's": "Switzerland",
    "Denmark Women's": "Denmark",
    "Zambia Women's": "Zambia",
    "Zambia W": "Zambia",
    "Philippines Women's": "Philippines",
    "Costa Rica Women's": "Costa Rica",
    "Portugal Women's": "Portugal",
    "Ireland Women's": "Ireland",
    "Republic of Ireland Women's": "Ireland",
    "Panama Women's": "Panama",
    "Haiti Women's": "Haiti",
    "Vietnam Women's": "Vietnam",
}

DEFAULT_POSSESSIONS = PROJECT_ROOT / "wwc_possessions.csv"
DEFAULT_ZONES = PROJECT_ROOT / "wwc_possession_zones.csv"
DEFAULT_TEAM_SUMMARY = PROJECT_ROOT / "wwc_team_start_distance.csv"
DEFAULT_PAGE_DATA = PROJECT_ROOT.parent / "epl-distance-from-goal" / "data.js"


def display_team_name(raw_name: str, year: str) -> str:
    base = SHORT_NAMES.get(raw_name)
    if base is None:
        base = re.sub(r"\s+Women'?s$", "", raw_name).strip() or raw_name
        base = re.sub(r"\s+W$", "", base).strip() or base
    return f"{base} {year}"


def enrich_possession_shots(
    events: list[dict[str, Any]],
    match_id: int,
    year: str,
    team_label_map: dict[str, str],
) -> list[dict[str, Any]]:
    base = extract_possessions(events, match_id)
    ordered = sorted(
        events,
        key=lambda e: (e.get("period", 0), e.get("timestamp", ""), e.get("index", 0)),
    )
    shot_details: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for event in ordered:
        if (event.get("type") or {}).get("name") != "Shot":
            continue
        if ((event.get("shot") or {}).get("type") or {}).get("name") == "Penalty":
            continue
        possession_id = event.get("possession")
        possession_team = (event.get("possession_team") or {}).get("name")
        if possession_id is None or not possession_team:
            continue
        shot = event.get("shot") or {}
        location = event.get("location") or [None, None]
        shot_details.setdefault((int(possession_id), possession_team), []).append(
            {
                "xg": float(shot.get("statsbomb_xg") or 0.0),
                "outcome": (shot.get("outcome") or {}).get("name"),
                "x": location[0],
                "y": location[1],
            }
        )

    enriched: list[dict[str, Any]] = []
    for row in base:
        key = (int(row["possession_id"]), row["possession_team"])
        shots = shot_details.get(key, [])
        raw_team = row["possession_team"]
        labeled = team_label_map.get(raw_team, display_team_name(raw_team, year))
        enriched.append(
            {
                **row,
                "season_year": year,
                "raw_team": raw_team,
                "possession_team": labeled,
                "shot_xg_list": "|".join(f"{s['xg']:.6f}" for s in shots),
                "shot_outcomes": "|".join(str(s["outcome"] or "") for s in shots),
            }
        )
    return enriched


# Furthest-stage labels for the page table (higher rank = further).
STAGE_RANK = {
    "Group stage": 0,
    "Round of 16": 1,
    "Quarterfinals": 2,
    "Semifinals": 3,
    "4th place": 4,
    "3rd place": 5,
    "Runner-up": 6,
    "Champions": 7,
}


def group_points_from_match(match: dict[str, Any], year: str) -> list[dict[str, Any]]:
    """3/1/0 points and goal difference from group-stage matches only."""
    stage = (match.get("competition_stage") or {}).get("name")
    if stage != "Group Stage":
        return []

    home = match["home_team"]["home_team_name"]
    away = match["away_team"]["away_team_name"]
    home_score = match.get("home_score")
    away_score = match.get("away_score")
    if home_score is None or away_score is None:
        return []

    if home_score > away_score:
        home_pts, away_pts = 3, 0
    elif home_score < away_score:
        home_pts, away_pts = 0, 3
    else:
        home_pts, away_pts = 1, 1

    return [
        {
            "team": display_team_name(home, year),
            "points": home_pts,
            "gf": int(home_score),
            "ga": int(away_score),
            "group_games": 1,
        },
        {
            "team": display_team_name(away, year),
            "points": away_pts,
            "gf": int(away_score),
            "ga": int(home_score),
            "group_games": 1,
        },
    ]


def furthest_stage_for_teams(matches: list[dict[str, Any]], year: str) -> dict[str, dict[str, Any]]:
    """Map team-year label -> furthest knockout result label + sort rank."""
    stages_played: dict[str, set[str]] = {}
    final_result: dict[str, str] = {}
    third_result: dict[str, str] = {}

    for match in matches:
        stage_raw = (match.get("competition_stage") or {}).get("name") or ""
        home = display_team_name(match["home_team"]["home_team_name"], year)
        away = display_team_name(match["away_team"]["away_team_name"], year)
        for team in (home, away):
            stages_played.setdefault(team, set()).add(stage_raw)

        home_score = match.get("home_score")
        away_score = match.get("away_score")
        if home_score is None or away_score is None:
            continue

        if stage_raw == "Final":
            if home_score > away_score:
                final_result[home], final_result[away] = "Champions", "Runner-up"
            elif home_score < away_score:
                final_result[away], final_result[home] = "Champions", "Runner-up"
        elif stage_raw == "3rd Place Final":
            if home_score > away_score:
                third_result[home], third_result[away] = "3rd place", "4th place"
            elif home_score < away_score:
                third_result[away], third_result[home] = "3rd place", "4th place"

    outcomes: dict[str, dict[str, Any]] = {}
    for team, played in stages_played.items():
        if team in final_result:
            label = final_result[team]
        elif team in third_result:
            label = third_result[team]
        elif "Semi-finals" in played:
            label = "Semifinals"
        elif "Quarter-finals" in played:
            label = "Quarterfinals"
        elif "Round of 16" in played:
            label = "Round of 16"
        else:
            label = "Group stage"
        outcomes[team] = {"stage": label, "stage_rank": STAGE_RANK[label]}
    return outcomes


def fit_quadratic(bins: pd.DataFrame) -> np.poly1d:
    usable = bins[bins["n"] >= 20]
    if len(usable) < 3:
        usable = bins[bins["n"] >= 5]
    coef = np.polyfit(usable["zone"] + 2.5, usable["avg_xg"], deg=2, w=usable["n"])
    return np.poly1d(coef)


def build_team_summary(possessions: pd.DataFrame, standings: pd.DataFrame) -> pd.DataFrame:
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
        possessions.groupby(["possession_team", "season_year"], as_index=False)
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
    summary = summary.merge(standings, on="team", how="left")
    return summary


def export_page_data(
    possessions: pd.DataFrame,
    team_summary: pd.DataFrame,
    output_path: Path,
    match_count: int,
) -> None:
    possessions = possessions.copy()
    possessions = possessions[possessions["yards_from_goal"] >= 0]
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
    teams = []
    for row in team_summary.itertuples():
        teams.append(
            {
                "team": row.team,
                "year": str(row.season_year),
                "possessions": int(row.possessions),
                "matches": int(row.matches),
                "avg_yards_from_goal": round(float(row.avg_yards_from_goal), 1),
                "avg_xg": round(float(row.avg_xg), 4),
                "avg_resid": round(float(row.avg_resid), 4),
                "shot_rate": round(float(row.shot_rate), 4),
                "group_points": int(row.group_points) if pd.notna(row.group_points) else None,
                "group_gd": int(row.group_gd) if pd.notna(row.group_gd) else None,
                "stage": row.stage if pd.notna(row.stage) else None,
                "stage_rank": int(row.stage_rank) if pd.notna(row.stage_rank) else None,
                # Keep points alias for any leftover consumers; group-stage only.
                "points": int(row.group_points) if pd.notna(row.group_points) else None,
                "games": int(row.group_games) if pd.notna(row.group_games) else 3,
            }
        )

    payload = {
        "statsbomb_season": (
            f"FIFA Women's World Cup 2019 & 2023 (StatsBomb open data, {match_count} matches)"
        ),
        "fotmob_window": None,
        "curve_kind": "possession_start_distance",
        "bins": bins,
        "poly_coef": [float(c) for c in poly.coefficients],
        "curve": curve,
        "zones": [
            {
                "label": f"{int(row.zone)}-{int(row.zone + 5)}y",
                "yards": float(row.zone),
                "avg_xg": round(float(row.avg_xg), 6),
                "shot_prob": None,
                "n": int(row.n),
            }
            for row in bins_frame.itertuples()
        ],
        "teams": teams,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "window.EPL_DISTANCE_DATA = " + json.dumps(payload, indent=2) + ";\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build WWC 2019+2023 possession start data.")
    parser.add_argument("--limit-per-season", type=int, default=None)
    parser.add_argument("--possessions-output", type=Path, default=DEFAULT_POSSESSIONS)
    parser.add_argument("--zones-output", type=Path, default=DEFAULT_ZONES)
    parser.add_argument("--team-summary-output", type=Path, default=DEFAULT_TEAM_SUMMARY)
    parser.add_argument("--page-data", type=Path, default=DEFAULT_PAGE_DATA)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    all_possessions: list[dict[str, Any]] = []
    standing_rows: list[dict[str, Any]] = []
    stage_rows: list[dict[str, Any]] = []
    match_count = 0

    for season in SEASONS:
        year = season["year"]
        season_id = season["season_id"]
        matches = load_matches(COMPETITION_ID, season_id)
        matches = sorted(matches, key=lambda m: m.get("match_date", ""))
        if args.limit_per_season is not None:
            matches = matches[: args.limit_per_season]

        print(f"WWC {year}: {len(matches)} matches")
        for index, match in enumerate(matches, start=1):
            match_id = int(match["match_id"])
            home = match["home_team"]["home_team_name"]
            away = match["away_team"]["away_team_name"]
            print(f"  [{index}/{len(matches)}] {home} vs {away}", flush=True)
            events = load_events(match_id)
            label_map = {
                home: display_team_name(home, year),
                away: display_team_name(away, year),
            }
            all_possessions.extend(
                enrich_possession_shots(events, match_id, year, label_map)
            )
            standing_rows.extend(group_points_from_match(match, year))
            match_count += 1

        for team, outcome in furthest_stage_for_teams(matches, year).items():
            stage_rows.append({"team": team, **outcome})

    if not all_possessions:
        print("No possessions extracted.")
        return 1

    possessions = pd.DataFrame(all_possessions)
    zones = possessions_to_zone_summary(all_possessions, bin_width_yards=10.0)
    standings = (
        pd.DataFrame(standing_rows)
        .groupby("team", as_index=False)
        .agg(
            group_points=("points", "sum"),
            gf=("gf", "sum"),
            ga=("ga", "sum"),
            group_games=("group_games", "sum"),
        )
    )
    standings["group_gd"] = standings["gf"] - standings["ga"]
    stages = pd.DataFrame(stage_rows)
    standings = standings.merge(stages, on="team", how="left")
    team_summary = build_team_summary(possessions, standings)

    possessions.to_csv(args.possessions_output, index=False)
    zones.to_csv(args.zones_output, index=False)
    team_summary.to_csv(args.team_summary_output, index=False)
    export_page_data(possessions, team_summary, args.page_data, match_count)

    print()
    print(f"Saved {len(possessions)} possessions -> {args.possessions_output}")
    print(f"Saved {len(team_summary)} team-years -> {args.team_summary_output}")
    print(f"Updated page data -> {args.page_data}")

    # Quick predictiveness snapshot for the console.
    corr = team_summary[["avg_yards_from_goal", "avg_resid", "group_points", "group_gd", "stage_rank"]].corr()
    print("\nCorrelations (lower yards = closer starts):")
    print(corr[["group_points", "group_gd", "stage_rank"]].loc[["avg_yards_from_goal", "avg_resid"]].to_string())
    print("\nClosest average starts:")
    print(
        team_summary[
            ["team", "avg_yards_from_goal", "group_points", "group_gd", "stage", "avg_resid"]
        ]
        .head(10)
        .to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
