#!/usr/bin/env python3
"""Summarize exported FotMob and model CSV files."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


DEFAULT_MATCHES = Path(__file__).with_name("epl_2025_26_xg_momentum.csv")
DEFAULT_SHOTS = Path(__file__).with_name("epl_2025_26_shots.csv")
DEFAULT_MODEL = Path(__file__).with_name("epl_model_gw1_4.csv")


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def summarize_model(path: Path) -> None:
    rows = load_csv(path)
    if not rows:
        print(f"No rows found in {path}")
        return

    results = Counter(row["result"] for row in rows)
    print(f"Model data from {path.name}")
    print(f"  Matches: {len(rows)}")
    print(f"  Results: {dict(results)}")
    print("\nSample feature row:")
    row = rows[0]
    print(
        f"  {row['home_team']} vs {row['away_team']} ({row['result']}) | "
        f"xG diff {float(row['xg_margin_diff']):+.2f}, "
        f"momentum diff {float(row['momentum_margin_diff']):+.0f}, "
        f"start-x diff {float(row['possession_start_x_diff']):+.1f}, "
        f"xG residual diff {float(row['xg_start_position_residual_diff']):+.3f}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize exported CSV files.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.model.exists():
        summarize_model(args.model)
    else:
        print(f"Missing model file: {args.model}")
        print("Run: python build_model_data.py")


if __name__ == "__main__":
    main()
