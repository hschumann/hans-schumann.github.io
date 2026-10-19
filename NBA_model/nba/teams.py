"""Canonical NBA team abbreviations and name mapping."""

from __future__ import annotations

NBA_TEAMS: frozenset[str] = frozenset(
    {
        "ATL",
        "BOS",
        "BKN",
        "CHA",
        "CHI",
        "CLE",
        "DAL",
        "DEN",
        "DET",
        "GS",
        "HOU",
        "IND",
        "LAC",
        "LAL",
        "MEM",
        "MIA",
        "MIL",
        "MIN",
        "NO",
        "NY",
        "OKC",
        "ORL",
        "PHI",
        "PHX",
        "POR",
        "SAC",
        "SA",
        "TOR",
        "UTAH",
        "WSH",
    }
)

# ESPN / Odds API display names -> abbrev
TEAM_ALIASES: dict[str, str] = {
    "atlanta hawks": "ATL",
    "boston celtics": "BOS",
    "brooklyn nets": "BKN",
    "charlotte hornets": "CHA",
    "chicago bulls": "CHI",
    "cleveland cavaliers": "CLE",
    "dallas mavericks": "DAL",
    "denver nuggets": "DEN",
    "detroit pistons": "DET",
    "golden state warriors": "GS",
    "houston rockets": "HOU",
    "indiana pacers": "IND",
    "la clippers": "LAC",
    "los angeles clippers": "LAC",
    "los angeles lakers": "LAL",
    "memphis grizzlies": "MEM",
    "miami heat": "MIA",
    "milwaukee bucks": "MIL",
    "minnesota timberwolves": "MIN",
    "new orleans pelicans": "NO",
    "new york knicks": "NY",
    "oklahoma city thunder": "OKC",
    "orlando magic": "ORL",
    "philadelphia 76ers": "PHI",
    "phoenix suns": "PHX",
    "portland trail blazers": "POR",
    "sacramento kings": "SAC",
    "san antonio spurs": "SA",
    "toronto raptors": "TOR",
    "utah jazz": "UTAH",
    "washington wizards": "WSH",
}

# Normalize ESPN abbrevs that differ from Odds API / common usage
ESPN_ABBREV_MAP: dict[str, str] = {
    "GS": "GS",
    "GSW": "GS",
    "NO": "NO",
    "NOP": "NO",
    "NY": "NY",
    "NYK": "NY",
    "SA": "SA",
    "SAS": "SA",
    "UTAH": "UTAH",
    "UTA": "UTAH",
    "WSH": "WSH",
    "WAS": "WSH",
    "PHX": "PHX",
    "PHO": "PHX",
    "BKN": "BKN",
    "BRK": "BKN",
    "CHA": "CHA",
    "CHO": "CHA",
}


def normalize_abbrev(abbrev: str | None) -> str:
    if not abbrev:
        raise ValueError("Missing team abbreviation")
    key = abbrev.strip().upper()
    return ESPN_ABBREV_MAP.get(key, key)


def normalize_team_name(name: str) -> str:
    key = name.strip().lower()
    if key in TEAM_ALIASES:
        return TEAM_ALIASES[key]
    # already an abbrev?
    try:
        return normalize_abbrev(name)
    except ValueError as exc:
        raise ValueError(f"Unknown team name: {name!r}") from exc


def is_nba_matchup(home_team: str, away_team: str) -> bool:
    return home_team in NBA_TEAMS and away_team in NBA_TEAMS
