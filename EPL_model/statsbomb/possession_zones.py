#!/usr/bin/env python3
"""Analyze P(shot) and xG value by possession start zone from StatsBomb events."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from statsbomb.config import DATA_ROOT, DEFAULT_COMPETITION_ID, DEFAULT_SEASON_ID
from statsbomb.loader import (
    extract_possessions,
    load_events,
    match_ids_for_season,
    possessions_to_zone_summary,
)


DEFAULT_POSSESSIONS_OUTPUT = PROJECT_ROOT / "statsbomb_possessions.csv"
DEFAULT_ZONES_OUTPUT = PROJECT_ROOT / "statsbomb_possession_zones.csv"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute shot probability and xG value by possession start zone."
    )
    parser.add_argument("--competition-id", type=int, default=DEFAULT_COMPETITION_ID)
    parser.add_argument("--season-id", type=int, default=DEFAULT_SEASON_ID)
    parser.add_argument("--bin-width-yards", type=float, default=10.0)
    parser.add_argument("--limit", type=int, default=40, help="Only process first N matches")
    parser.add_argument("--possessions-output", type=Path, default=DEFAULT_POSSESSIONS_OUTPUT)
    parser.add_argument("--zones-output", type=Path, default=DEFAULT_ZONES_OUTPUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    match_ids = match_ids_for_season(args.competition_id, args.season_id)
    if args.limit is not None:
        match_ids = match_ids[: args.limit]

    if not match_ids:
        print(
            "No local match files found. Run:\n"
            "  .venv/bin/python statsbomb/download.py"
        )
        return 1

    all_possessions: list[dict] = []
    for index, match_id in enumerate(match_ids, start=1):
        print(f"[{index}/{len(match_ids)}] match {match_id}", flush=True)
        events = load_events(match_id)
        all_possessions.extend(extract_possessions(events, match_id))

    possessions_frame = pd.DataFrame(all_possessions)
    zones_frame = possessions_to_zone_summary(all_possessions, args.bin_width_yards)

    possessions_frame.to_csv(args.possessions_output, index=False)
    zones_frame.to_csv(args.zones_output, index=False)

    print()
    print(f"Saved {len(possessions_frame)} possessions -> {args.possessions_output}")
    print(f"Saved {len(zones_frame)} zones -> {args.zones_output}")
    print("\nZone summary (yards from opponent goal):")
    print(
        zones_frame[
            ["zone_label", "possessions", "shot_probability", "avg_xg_per_possession", "avg_xg_per_shot"]
        ].to_string(index=False, float_format=lambda x: f"{x:.3f}")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
