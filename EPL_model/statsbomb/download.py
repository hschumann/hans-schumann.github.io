#!/usr/bin/env python3
"""Download or update the StatsBomb open-data repository locally."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from typing import Any

from statsbomb.config import (
    COMPETITIONS_FILE,
    DATA_ROOT,
    DEFAULT_COMPETITION_ID,
    DEFAULT_SEASON_ID,
    EVENTS_DIR,
    LINEUPS_DIR,
    MATCHES_DIR,
    OPEN_DATA_DIR,
    OPEN_DATA_REPO,
)


def run_git(args: list[str], cwd: Path | None = None) -> None:
    if shutil.which("git") is None:
        raise RuntimeError("git is required to download StatsBomb open-data.")

    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(message)


def clone_or_update_repo() -> Path:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)

    if OPEN_DATA_DIR.exists():
        print(f"Updating existing repo at {OPEN_DATA_DIR}")
        run_git(["pull", "--ff-only"], cwd=OPEN_DATA_DIR)
    else:
        print(f"Cloning {OPEN_DATA_REPO} into {OPEN_DATA_DIR}")
        run_git(["clone", "--depth", "1", OPEN_DATA_REPO, str(OPEN_DATA_DIR)])

    return OPEN_DATA_DIR


def load_competitions() -> list[dict[str, Any]]:
    with COMPETITIONS_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def list_competitions() -> None:
    competitions = load_competitions()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in competitions:
        grouped.setdefault(row["competition_name"], []).append(row)

    print("Available competitions in open-data:\n")
    for name in sorted(grouped):
        seasons = sorted({row["season_name"] for row in grouped[name]})
        print(f"  {name}")
        print(f"    competition_id={grouped[name][0]['competition_id']}")
        print(f"    seasons: {', '.join(seasons)}")
        print()


def filter_match_files(competition_id: int, season_id: int) -> list[Path]:
    season_dir = MATCHES_DIR / str(competition_id) / str(season_id)
    if not season_dir.exists():
        raise FileNotFoundError(f"No local matches found at {season_dir}")

    return sorted(season_dir.glob("*.json"))


def summarize_local_dataset(competition_id: int, season_id: int) -> None:
    match_files = filter_match_files(competition_id, season_id)
    missing_events = [
        path.stem
        for path in match_files
        if not (EVENTS_DIR / f"{path.stem}.json").exists()
    ]
    missing_lineups = [
        path.stem
        for path in match_files
        if not (LINEUPS_DIR / f"{path.stem}.json").exists()
    ]

    print(f"Competition {competition_id}, season {season_id}")
    print(f"  Matches: {len(match_files)}")
    print(f"  Missing event files: {len(missing_events)}")
    print(f"  Missing lineup files: {len(missing_lineups)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download StatsBomb open-data locally. "
            "This can take a while and use several hundred MB of disk space."
        )
    )
    parser.add_argument(
        "--list-competitions",
        action="store_true",
        help="Print competitions/seasons available in the local open-data repo",
    )
    parser.add_argument(
        "--competition-id",
        type=int,
        default=DEFAULT_COMPETITION_ID,
        help=f"Competition ID to summarize after download (default: {DEFAULT_COMPETITION_ID})",
    )
    parser.add_argument(
        "--season-id",
        type=int,
        default=DEFAULT_SEASON_ID,
        help=f"Season ID to summarize after download (default: {DEFAULT_SEASON_ID})",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.list_competitions:
        if not COMPETITIONS_FILE.exists():
            print("No local open-data repo found. Run without --list-competitions first.")
            return 1
        list_competitions()
        return 0

    clone_or_update_repo()
    summarize_local_dataset(args.competition_id, args.season_id)
    print()
    print("Next steps:")
    print("  python statsbomb/export_events.py --competition-id 2 --season-id 27 --limit 5")
    print("  python statsbomb/export_possessions.py --competition-id 2 --season-id 27 --limit 5")
    return 0


if __name__ == "__main__":
    sys.exit(main())
