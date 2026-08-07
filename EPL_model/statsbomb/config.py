from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "data" / "statsbomb"
OPEN_DATA_DIR = DATA_ROOT / "open-data"
OPEN_DATA_REPO = "https://github.com/statsbomb/open-data.git"

COMPETITIONS_FILE = OPEN_DATA_DIR / "data" / "competitions.json"
MATCHES_DIR = OPEN_DATA_DIR / "data" / "matches"
EVENTS_DIR = OPEN_DATA_DIR / "data" / "events"
LINEUPS_DIR = OPEN_DATA_DIR / "data" / "lineups"

# Useful defaults when exploring possession modeling before EPL open-data sync.
DEFAULT_COMPETITION_ID = 2  # Premier League
DEFAULT_SEASON_ID = 27  # 2015/2016 in open-data
