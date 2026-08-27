"""Column metadata for Football-Data.co.uk CSV files.

See https://www.football-data.co.uk/notes.txt for the upstream definitions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    group: str
    availability: str  # "prematch" | "postmatch" | "both"
    description: str


# Columns you can use before kickoff (fixtures file or historical odds columns).
PREMATCH_COLUMNS: tuple[str, ...] = (
    "Div",
    "Date",
    "Time",
    "HomeTeam",
    "AwayTeam",
    "Referee",
)

# Result columns — only known after the match finishes.
POSTMATCH_COLUMNS: tuple[str, ...] = (
    "FTHG",
    "FTAG",
    "FTR",
    "HTHG",
    "HTAG",
    "HTR",
    "HS",
    "AS",
    "HST",
    "AST",
    "HF",
    "AF",
    "HC",
    "AC",
    "HY",
    "AY",
    "HR",
    "AR",
)

# Odds are collected pre-match (opening) and again near kickoff (closing, suffix C).
ODDS_1X2_PREFIXES: tuple[str, ...] = (
    "B365",
    "BWH",
    "BF",
    "PS",
    "WH",
    "1XB",
    "Max",
    "Avg",
    "BFE",
)

COLUMN_GROUPS: dict[str, list[ColumnInfo]] = {
    "fixture": [
        ColumnInfo("Div", "fixture", "prematch", "League division (E0 = Premier League)"),
        ColumnInfo("Date", "fixture", "prematch", "Match date (dd/mm/yy)"),
        ColumnInfo("Time", "fixture", "prematch", "Kick-off time"),
        ColumnInfo("HomeTeam", "fixture", "prematch", "Home team name"),
        ColumnInfo("AwayTeam", "fixture", "prematch", "Away team name"),
        ColumnInfo("Referee", "fixture", "prematch", "Assigned referee (when published)"),
    ],
    "result": [
        ColumnInfo("FTHG", "result", "postmatch", "Full-time home goals"),
        ColumnInfo("FTAG", "result", "postmatch", "Full-time away goals"),
        ColumnInfo("FTR", "result", "postmatch", "Full-time result (H/D/A)"),
        ColumnInfo("HTHG", "result", "postmatch", "Half-time home goals"),
        ColumnInfo("HTAG", "result", "postmatch", "Half-time away goals"),
        ColumnInfo("HTR", "result", "postmatch", "Half-time result (H/D/A)"),
    ],
    "match_stats": [
        ColumnInfo("HS", "match_stats", "postmatch", "Home shots"),
        ColumnInfo("AS", "match_stats", "postmatch", "Away shots"),
        ColumnInfo("HST", "match_stats", "postmatch", "Home shots on target"),
        ColumnInfo("AST", "match_stats", "postmatch", "Away shots on target"),
        ColumnInfo("HF", "match_stats", "postmatch", "Home fouls"),
        ColumnInfo("AF", "match_stats", "postmatch", "Away fouls"),
        ColumnInfo("HC", "match_stats", "postmatch", "Home corners"),
        ColumnInfo("AC", "match_stats", "postmatch", "Away corners"),
        ColumnInfo("HY", "match_stats", "postmatch", "Home yellow cards"),
        ColumnInfo("AY", "match_stats", "postmatch", "Away yellow cards"),
        ColumnInfo("HR", "match_stats", "postmatch", "Home red cards"),
        ColumnInfo("AR", "match_stats", "postmatch", "Away red cards"),
    ],
    "odds_1x2": [
        ColumnInfo(
            "B365H/D/A",
            "odds_1x2",
            "prematch",
            "Bet365 home/draw/away decimal odds (opening; add C for closing)",
        ),
        ColumnInfo(
            "AvgH/D/A",
            "odds_1x2",
            "prematch",
            "Market-average 1X2 odds across bookmakers",
        ),
        ColumnInfo(
            "MaxH/D/A",
            "odds_1x2",
            "prematch",
            "Market-maximum 1X2 odds across bookmakers",
        ),
        ColumnInfo(
            "BFEH/D/A",
            "odds_1x2",
            "prematch",
            "Betfair Exchange 1X2 odds",
        ),
    ],
    "odds_totals": [
        ColumnInfo(
            "B365>2.5 / B365<2.5",
            "odds_totals",
            "prematch",
            "Over/under 2.5 goals (opening; add C for closing)",
        ),
        ColumnInfo(
            "Avg>2.5 / Avg<2.5",
            "odds_totals",
            "prematch",
            "Market-average over/under 2.5 goals",
        ),
    ],
    "odds_handicap": [
        ColumnInfo(
            "AHh",
            "odds_handicap",
            "prematch",
            "Asian handicap line for the home team",
        ),
        ColumnInfo(
            "B365AHH / B365AHA",
            "odds_handicap",
            "prematch",
            "Bet365 Asian handicap home/away odds",
        ),
        ColumnInfo(
            "AvgAHH / AvgAHA",
            "odds_handicap",
            "prematch",
            "Market-average Asian handicap odds",
        ),
    ],
}


def list_columns(availability: str | None = None) -> list[ColumnInfo]:
    """Return column metadata, optionally filtered by availability."""
    columns = [info for group in COLUMN_GROUPS.values() for info in group]
    if availability is None:
        return columns
    return [info for info in columns if info.availability == availability]
