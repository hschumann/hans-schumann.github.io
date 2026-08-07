#!/usr/bin/env python3
"""Export StatsBomb possessions from local open-data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from statsbomb.config import DATA_ROOT, DEFAULT_COMPETITION_ID, DEFAULT_SEASON_ID
from statsbomb.loader import extract_possessions, load_events, match_ids_for_season


def export_possessions(
    competition_id: int,
    season_id: int,
    output_dir: Path,
    limit: int | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    match_ids = match_ids_for_season(competition_id, season_id)
    if limit is not None:
        match_ids = match_ids[:limit]

    all_rows: list[dict] = []
    for match_id in match_ids:
        events = load_events(match_id)
        possessions = extract_possessions(events, match_id)
        all_rows.extend(possessions)
        print(f"Match {match_id}: {len(possessions)} possessions")

    combined = pd.DataFrame(all_rows)
    output_path = output_dir / f"possessions_{competition_id}_{season_id}.csv"
    combined.to_csv(output_path, index=False)
    print(f"Saved {len(combined)} possessions -> {output_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export StatsBomb possessions to CSV.")
    parser.add_argument("--competition-id", type=int, default=DEFAULT_COMPETITION_ID)
    parser.add_argument("--season-id", type=int, default=DEFAULT_SEASON_ID)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DATA_ROOT / "exports",
        help="Directory for exported CSV files",
    )
    parser.add_argument("--limit", type=int, default=None, help="Only export the first N matches")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    export_possessions(args.competition_id, args.season_id, args.output_dir, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
