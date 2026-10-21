#!/usr/bin/env python3
"""
Build rolling 4-week MLB standings (win pct + league rank) for a season.

Starting once each team has a full 4-week lookback window, compute daily
sliding 28-day records for every team and rank all 30 clubs by win pct.

Usage:
    python rolling_standings.py
    python rolling_standings.py --season 2026
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
from pybaseball import cache, schedule_and_record

SCRIPT_DIR = Path(__file__).parent
DEFAULT_OUTPUT = SCRIPT_DIR / "rolling_standings_2026.csv"
RAW_GAMES_OUTPUT = SCRIPT_DIR / "data" / "mlb_2026_game_results.csv"

WINDOW_DAYS = 28  # 4 weeks, inclusive

# Baseball-Reference abbreviations for current MLB teams.
MLB_TEAMS = [
    "ARI", "ATL", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE", "COL", "DET",
    "HOU", "KCR", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY", "ATH",
    "PHI", "PIT", "SDP", "SEA", "SFG", "STL", "TBR", "TEX", "TOR", "WSN",
]

cache.enable()


def parse_game_date(series: pd.Series, season: int) -> pd.Series:
    cleaned = (
        series.str.replace(r"^\w+,\s*", "", regex=True)
        .str.replace(r"\s*\(\d+\)$", "", regex=True)
        .str.strip()
    )
    dates = pd.to_datetime(cleaned + f" {season}", format="%b %d %Y")
    # Games after the All-Star break stay in the same season; Jan/Feb belong to next calendar year.
    rollover = dates.dt.month <= 2
    dates.loc[rollover] = dates.loc[rollover] + pd.DateOffset(years=1)
    return dates


def fetch_season_games(season: int, teams: list[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for team in teams:
        with contextlib.redirect_stdout(io.StringIO()):
            schedule = schedule_and_record(season, team)
        schedule["game_date"] = parse_game_date(schedule["Date"], season)
        played = schedule.loc[schedule["W/L"].isin(["W", "L", "T"]), ["Tm", "game_date", "W/L"]].copy()
        played["team"] = team
        played["result"] = played["W/L"]
        frames.append(played[["team", "game_date", "result"]])

    games = pd.concat(frames, ignore_index=True)
    games = games.sort_values(["team", "game_date"]).reset_index(drop=True)
    return games


def build_rolling_standings(games: pd.DataFrame, season: int) -> pd.DataFrame:
    season_start = games["game_date"].min()
    last_game_date = games["game_date"].max()
    first_window_end = season_start + timedelta(days=WINDOW_DAYS - 1)

    window_ends = pd.date_range(first_window_end, last_game_date, freq="D")
    rows: list[dict] = []

    for window_end in window_ends:
        window_start = window_end - timedelta(days=WINDOW_DAYS - 1)
        window_games = games.loc[
            (games["game_date"] >= window_start) & (games["game_date"] <= window_end)
        ]

        team_stats = (
            window_games.groupby("team", as_index=False)
            .agg(
                wins=("result", lambda s: (s == "W").sum()),
                losses=("result", lambda s: (s == "L").sum()),
                ties=("result", lambda s: (s == "T").sum()),
            )
        )
        team_stats["games"] = team_stats["wins"] + team_stats["losses"] + team_stats["ties"]
        team_stats["win_pct"] = (
            team_stats["wins"] + 0.5 * team_stats["ties"]
        ) / team_stats["games"]
        team_stats = team_stats.drop(columns=["ties"])
        team_stats = team_stats.sort_values(
            ["win_pct", "wins", "team"], ascending=[False, False, True]
        )
        team_stats["rank"] = team_stats["win_pct"].rank(method="min", ascending=False).astype(int)
        team_stats["window_start"] = window_start.date()
        team_stats["window_end"] = window_end.date()
        team_stats["season"] = season

        rows.extend(
            team_stats[
                [
                    "season",
                    "window_start",
                    "window_end",
                    "team",
                    "wins",
                    "losses",
                    "win_pct",
                    "rank",
                ]
            ].to_dict("records")
        )

    return pd.DataFrame(rows)


def build_daily_leaders(standings: pd.DataFrame) -> pd.DataFrame:
    leaders = standings.loc[standings["rank"] == 1].copy()
    return leaders.sort_values(["window_end", "team"]).reset_index(drop=True)


def build_rank_counts(standings: pd.DataFrame, teams: list[str]) -> pd.DataFrame:
    counts = (
        standings.groupby(["rank", "team"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )
    matrix = counts.pivot(index="rank", columns="team", values="count").fillna(0).astype(int)
    matrix = matrix.reindex(index=range(1, 31), columns=teams, fill_value=0)
    matrix.index.name = "rank"
    return matrix.reset_index()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build rolling 4-week MLB standings.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-download game results instead of using cached CSV.",
    )
    args = parser.parse_args()

    raw_path = SCRIPT_DIR / "data" / f"mlb_{args.season}_game_results.csv"
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    if raw_path.exists() and not args.refresh:
        print(f"Loading cached game results from {raw_path} …")
        games = pd.read_csv(raw_path, parse_dates=["game_date"])
    else:
        print(f"Fetching {args.season} game results for {len(MLB_TEAMS)} teams …")
        games = fetch_season_games(args.season, MLB_TEAMS)
        games.to_csv(raw_path, index=False)
        print(f"Saved raw game results → {raw_path}")

    standings = build_rolling_standings(games, args.season)
    standings["win_pct"] = standings["win_pct"].round(3)
    standings.to_csv(args.output, index=False, float_format="%.3f")

    leader_output = args.output.with_name(
        args.output.name.replace("rolling_standings", "rolling_standings_leader")
    )
    leaders = build_daily_leaders(standings)
    leaders.to_csv(leader_output, index=False, float_format="%.3f")

    rank_counts_output = args.output.with_name(
        args.output.name.replace("rolling_standings", "rolling_standings_rank_counts")
    )
    rank_counts = build_rank_counts(standings, MLB_TEAMS)
    rank_counts.to_csv(rank_counts_output, index=False)

    print(f"\nSeason start: {games['game_date'].min().date()}")
    print(f"Latest game:  {games['game_date'].max().date()}")
    print(f"Window ends:  {standings['window_end'].min()} to {standings['window_end'].max()}")
    print(f"Rows:         {len(standings):,} ({standings['window_end'].nunique()} days × 30 teams)")
    print(f"Saved → {args.output}")
    print(f"Daily leaders → {leader_output} ({len(leaders)} rows, {leaders['window_end'].nunique()} dates)")
    print(f"Rank counts → {rank_counts_output}")

    sample = standings.loc[
        (standings["team"] == "BOS")
        & (standings["window_end"].astype(str).isin(["2026-05-30", "2026-05-31"]))
    ]
    if not sample.empty:
        print("\nBoston sample windows:")
        print(sample.to_string(index=False))


if __name__ == "__main__":
    main()
