#!/usr/bin/env python3
"""Download Premier League CSVs from Football-Data.co.uk."""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://www.football-data.co.uk/mmz4281"
FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"
EPL_DIVISION = "E0"
DEFAULT_RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "football_data" / "raw"


def season_code(start_year: int) -> str:
    """Convert 2024 -> '2425' for the 2024/25 season file."""
    end = start_year + 1
    return f"{start_year % 100:02d}{end % 100:02d}"


def season_label(start_year: int) -> str:
    end = start_year + 1
    return f"{start_year}/{str(end)[-2:]}"


def season_url(start_year: int) -> str:
    return f"{BASE_URL}/{season_code(start_year)}/{EPL_DIVISION}.csv"


def download_file(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "EPL_model/1.0"})
    try:
        import ssl

        context = ssl.create_default_context()
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            output_path.write_bytes(response.read())
    except urllib.error.URLError:
        # Fallback for environments with incomplete CA bundles (common on macOS).
        import subprocess

        subprocess.run(
            ["curl", "-fsSL", url, "-o", str(output_path)],
            check=True,
        )


def download_epl_season(start_year: int, raw_dir: Path = DEFAULT_RAW_DIR) -> Path:
    """Download one EPL season CSV. Returns the saved file path."""
    url = season_url(start_year)
    output_path = raw_dir / f"E0_{season_code(start_year)}.csv"
    download_file(url, output_path)
    return output_path


def download_epl_seasons(
    start_year: int,
    end_year: int,
    raw_dir: Path = DEFAULT_RAW_DIR,
) -> list[Path]:
    """Download EPL seasons from start_year through end_year (inclusive)."""
    paths: list[Path] = []
    for year in range(start_year, end_year + 1):
        path = download_epl_season(year, raw_dir=raw_dir)
        paths.append(path)
        print(f"Downloaded {season_label(year)} -> {path.name}")
    return paths


def download_fixtures(raw_dir: Path = DEFAULT_RAW_DIR) -> Path:
    output_path = raw_dir / "fixtures.csv"
    download_file(FIXTURES_URL, output_path)
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download EPL data from Football-Data.co.uk")
    parser.add_argument("--start-year", type=int, default=2015, help="First season start year")
    parser.add_argument("--end-year", type=int, default=2025, help="Last season start year")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--fixtures", action="store_true", help="Also download upcoming fixtures")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    download_epl_seasons(args.start_year, args.end_year, raw_dir=args.raw_dir)
    if args.fixtures:
        path = download_fixtures(raw_dir=args.raw_dir)
        print(f"Downloaded fixtures -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
