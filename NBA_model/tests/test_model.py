from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nba.espn import _home_spread_from_odds, _parse_line
from nba.model import compute_picks, team_ats_scores
from nba.storage import Game, Store


class SpreadParseTests(unittest.TestCase):
    def test_parse_line(self) -> None:
        self.assertEqual(_parse_line("+1.5"), 1.5)
        self.assertEqual(_parse_line("-7.5"), -7.5)
        self.assertEqual(_parse_line("PK"), 0.0)

    def test_home_spread_from_point_spread(self) -> None:
        odds = {
            "pointSpread": {
                "home": {"close": {"line": "+1.5", "odds": "-110"}},
                "away": {"close": {"line": "-1.5", "odds": "-110"}},
            },
            "details": "BOS -1.5",
            "homeTeamOdds": {
                "team": {"abbreviation": "DET"},
                "favorite": False,
            },
        }
        self.assertEqual(_home_spread_from_odds(odds), 1.5)


class ModelTests(unittest.TestCase):
    def test_team_scores_and_picks(self) -> None:
        now = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "test.db")
            # Underperforming home team (DET), overperforming away (BOS)
            store.upsert_spread(
                game_id="g1",
                tipoff_utc=(now - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
                home_team="DET",
                away_team="CHI",
                home_spread=-3.5,
                spread_source="test",
            )
            store.upsert_result(
                game_id="g1",
                tipoff_utc=(now - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
                home_team="DET",
                away_team="CHI",
                home_score=100,
                away_score=110,
                status="final",
            )
            # DET ATS = (100-110) + (-3.5) = -13.5
            store.upsert_spread(
                game_id="g2",
                tipoff_utc=(now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                home_team="BOS",
                away_team="NY",
                home_spread=-4.5,
                spread_source="test",
            )
            store.upsert_result(
                game_id="g2",
                tipoff_utc=(now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                home_team="BOS",
                away_team="NY",
                home_score=120,
                away_score=100,
                status="final",
            )
            # BOS ATS = (120-100) + (-4.5) = 15.5

            tip = now.replace(hour=23).isoformat().replace("+00:00", "Z")
            store.upsert_spread(
                game_id="today",
                tipoff_utc=tip,
                home_team="DET",
                away_team="BOS",
                home_spread=1.5,
                spread_source="test",
            )

            picks = compute_picks(
                store,
                as_of=now,
                lookback_days=7,
                top_n=3,
                timezone_name="UTC",
            )
            self.assertEqual(len(picks), 1)
            self.assertEqual(picks[0].bet_team, "DET")
            self.assertAlmostEqual(picks[0].abs_diff, 13.5 + 15.5)
            store.close()


if __name__ == "__main__":
    unittest.main()
