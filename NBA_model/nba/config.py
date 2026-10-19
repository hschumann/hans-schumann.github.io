from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "nba_ats.db"
PICKS_JSON = DATA_DIR / "latest_picks.json"
GAMES_CSV = DATA_DIR / "games.csv"

load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_EMAIL_TO = "hansschumann24@gmail.com"


@dataclass(frozen=True)
class Settings:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    email_from: str
    email_to: str
    odds_api_key: str
    preferred_book: str
    ats_lookback_days: int
    top_n_picks: int
    timezone: str
    db_path: Path
    picks_json: Path
    games_csv: Path


def get_settings() -> Settings:
    smtp_user = os.getenv("SMTP_USER", "").strip()
    return Settings(
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=smtp_user,
        smtp_password=os.getenv("SMTP_PASSWORD", "").strip(),
        email_from=os.getenv("EMAIL_FROM", smtp_user).strip(),
        email_to=os.getenv("EMAIL_TO", DEFAULT_EMAIL_TO).strip(),
        odds_api_key=os.getenv("ODDS_API_KEY", "").strip(),
        preferred_book=os.getenv("PREFERRED_BOOK", "draftkings").strip().lower(),
        ats_lookback_days=int(os.getenv("ATS_LOOKBACK_DAYS", "7")),
        top_n_picks=int(os.getenv("TOP_N_PICKS", "3")),
        timezone=os.getenv("TIMEZONE", "America/New_York").strip(),
        db_path=Path(os.getenv("NBA_DB_PATH", str(DB_PATH))),
        picks_json=Path(os.getenv("NBA_PICKS_JSON", str(PICKS_JSON))),
        games_csv=Path(os.getenv("NBA_GAMES_CSV", str(GAMES_CSV))),
    )
