"""Load and normalize Football-Data.co.uk EPL CSV files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "football_data" / "raw"
PROCESSED_PATH = Path(__file__).resolve().parents[1] / "data" / "football_data" / "epl_matches.csv"
EPL_DIVISION = "E0"

# Canonical names used in modelling scripts.
CORE_COLUMNS = [
    "season",
    "date",
    "time",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "result",
    "ht_home_goals",
    "ht_away_goals",
    "ht_result",
    "referee",
    "home_shots",
    "away_shots",
    "home_shots_on_target",
    "away_shots_on_target",
    "home_fouls",
    "away_fouls",
    "home_corners",
    "away_corners",
    "home_yellows",
    "away_yellows",
    "home_reds",
    "away_reds",
    "b365_home",
    "b365_draw",
    "b365_away",
    "avg_home",
    "avg_draw",
    "avg_away",
    "b365_over_2_5",
    "b365_under_2_5",
    "avg_over_2_5",
    "avg_under_2_5",
    "asian_handicap_line",
    "avg_ah_home",
    "avg_ah_away",
]

RENAME_MAP = {
    "Div": "division",
    "Date": "date_raw",
    "Time": "time",
    "HomeTeam": "home_team",
    "AwayTeam": "away_team",
    "FTHG": "home_goals",
    "FTAG": "away_goals",
    "FTR": "result",
    "HTHG": "ht_home_goals",
    "HTAG": "ht_away_goals",
    "HTR": "ht_result",
    "Referee": "referee",
    "HS": "home_shots",
    "AS": "away_shots",
    "HST": "home_shots_on_target",
    "AST": "away_shots_on_target",
    "HF": "home_fouls",
    "AF": "away_fouls",
    "HC": "home_corners",
    "AC": "away_corners",
    "HY": "home_yellows",
    "AY": "away_yellows",
    "HR": "home_reds",
    "AR": "away_reds",
    "B365H": "b365_home",
    "B365D": "b365_draw",
    "B365A": "b365_away",
    "AvgH": "avg_home",
    "AvgD": "avg_draw",
    "AvgA": "avg_away",
    "B365>2.5": "b365_over_2_5",
    "B365<2.5": "b365_under_2_5",
    "Avg>2.5": "avg_over_2_5",
    "Avg<2.5": "avg_under_2_5",
    "AHh": "asian_handicap_line",
    "AvgAHH": "avg_ah_home",
    "AvgAHA": "avg_ah_away",
}


def season_from_filename(path: Path) -> str | None:
    stem = path.stem  # E0_2425
    if "_" not in stem:
        return None
    code = stem.rsplit("_", 1)[-1]
    if len(code) != 4 or not code.isdigit():
        return None
    start = int(code[:2])
    end = int(code[2:])
    start_year = 2000 + start if start < 50 else 1900 + start
    end_year = 2000 + end if end < 50 else 1900 + end
    return f"{start_year}/{str(end_year)[-2:]}"


def parse_match_date(frame: pd.DataFrame) -> pd.Series:
    parsed = pd.to_datetime(frame["date_raw"], format="%d/%m/%Y", errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(
            frame.loc[missing, "date_raw"],
            format="%d/%m/%y",
            errors="coerce",
        )
    return parsed


def read_season_file(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    frame.columns = frame.columns.str.replace("\ufeff", "", regex=False)
    frame["season"] = season_from_filename(path)
    return frame


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.rename(columns=RENAME_MAP).copy()
    normalized["date"] = parse_match_date(normalized)
    normalized = normalized[normalized["division"] == EPL_DIVISION].copy()
    normalized = normalized.dropna(subset=["date", "home_team", "away_team"])

    for column in [
        "home_goals",
        "away_goals",
        "ht_home_goals",
        "ht_away_goals",
        "home_shots",
        "away_shots",
        "home_shots_on_target",
        "away_shots_on_target",
        "home_fouls",
        "away_fouls",
        "home_corners",
        "away_corners",
        "home_yellows",
        "away_yellows",
        "home_reds",
        "away_reds",
        "b365_home",
        "b365_draw",
        "b365_away",
        "avg_home",
        "avg_draw",
        "avg_away",
        "b365_over_2_5",
        "b365_under_2_5",
        "avg_over_2_5",
        "avg_under_2_5",
        "asian_handicap_line",
        "avg_ah_home",
        "avg_ah_away",
    ]:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    keep = [column for column in CORE_COLUMNS if column in normalized.columns]
    return normalized[keep].sort_values(["date", "home_team"]).reset_index(drop=True)


def load_epl_matches(
    raw_dir: Path = RAW_DIR,
    processed_path: Path = PROCESSED_PATH,
    refresh: bool = False,
) -> pd.DataFrame:
    """Load all downloaded EPL season files into one tidy dataframe."""
    if processed_path.exists() and not refresh:
        return pd.read_csv(processed_path, parse_dates=["date"])

    season_files = sorted(raw_dir.glob("E0_*.csv"))
    if not season_files:
        raise FileNotFoundError(
            f"No season files in {raw_dir}. Run: python -m football_data.download"
        )

    frames = [normalize_frame(read_season_file(path)) for path in season_files]
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("date").drop_duplicates(
        subset=["date", "home_team", "away_team"],
        keep="last",
    )
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(processed_path, index=False)
    return combined


def load_fixtures(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Load upcoming fixtures (E0 only) with pre-match odds."""
    path = raw_dir / "fixtures.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Download with: python -m football_data.download --fixtures"
        )

    frame = pd.read_csv(path, encoding="utf-8-sig")
    frame.columns = frame.columns.str.replace("\ufeff", "", regex=False)
    frame = frame[frame["Div"] == EPL_DIVISION].copy()
    frame["date"] = pd.to_datetime(frame["Date"], format="%d/%m/%Y", errors="coerce")
    frame = frame.rename(
        columns={
            "HomeTeam": "home_team",
            "AwayTeam": "away_team",
            "Time": "time",
            "Referee": "referee",
            "B365H": "b365_home",
            "B365D": "b365_draw",
            "B365A": "b365_away",
            "AvgH": "avg_home",
            "AvgD": "avg_draw",
            "AvgA": "avg_away",
        }
    )
    return frame.sort_values("date").reset_index(drop=True)
