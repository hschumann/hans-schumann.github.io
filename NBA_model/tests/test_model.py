from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nba.espn import _home_spread_from_odds, _parse_line
from nba.model import accuracy_by_percentile, compute_picks, rank_slate, team_ats_scores
from nba.storage import Game, Store


class SpreadParseTests(unittest.TestCase):
    def test_parse_line(self) -> None:
        self.assertEqual(_parse_line("+1.5"), 1.5)
        self.assertEqual(_parse_line("-7.5"), -7.5)
        self.assertEqual(_parse_line("PK"), 0.0)
        self.assertIsNone(_parse_line("OFF"))
        self.assertIsNone(_parse_line("NL"))

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

            # A second game with a smaller gap should sort behind DET/BOS.
            store.upsert_spread(
                game_id="g3",
                tipoff_utc=(now - timedelta(days=3)).isoformat().replace("+00:00", "Z"),
                home_team="MIA",
                away_team="ORL",
                home_spread=-2.0,
                spread_source="test",
            )
            store.upsert_result(
                game_id="g3",
                tipoff_utc=(now - timedelta(days=3)).isoformat().replace("+00:00", "Z"),
                home_team="MIA",
                away_team="ORL",
                home_score=110,
                away_score=100,
                status="final",
            )
            store.upsert_spread(
                game_id="today-2",
                tipoff_utc=tip,
                home_team="MIA",
                away_team="ORL",
                home_spread=-1.5,
                spread_source="test",
            )
            slate = rank_slate(
                store,
                as_of=now,
                lookback_days=7,
                timezone_name="UTC",
            )
            self.assertEqual([p.game_id for p in slate], ["today", "today-2"])
            self.assertGreater(slate[0].abs_diff, slate[1].abs_diff)
            top = compute_picks(
                store,
                as_of=now,
                lookback_days=7,
                top_n=1,
                timezone_name="UTC",
            )
            self.assertEqual([p.game_id for p in top], ["today"])
            store.close()


class PercentileAccuracyTests(unittest.TestCase):
    def test_eight_games_land_one_per_bin_with_cutoffs(self) -> None:
        samples = [(float(i), "W" if i == 8 else "L") for i in range(1, 9)]
        bins = accuracy_by_percentile(samples)
        self.assertEqual([b["label"] for b in bins], [
            "87.5th–100th",
            "75th–87.5th",
            "62.5th–75th",
            "50th–62.5th",
            "37.5th–50th",
            "25th–37.5th",
            "12.5th–25th",
            "0th–12.5th",
        ])
        self.assertEqual([b["games"] for b in bins], [1] * 8)
        self.assertEqual(bins[0]["wins"], 1)
        self.assertEqual(bins[0]["accuracy"], 1.0)
        self.assertAlmostEqual(bins[0]["cutoff"], 7.125)
        self.assertAlmostEqual(bins[1]["cutoff"], 6.25)
        self.assertGreater(bins[0]["cutoff"], bins[1]["cutoff"])
        self.assertEqual(bins[-1]["losses"], 1)
        self.assertEqual(bins[-1]["accuracy"], 0.0)
        self.assertAlmostEqual(bins[-1]["cutoff"], 1.0)

    def test_pushes_do_not_count_toward_accuracy(self) -> None:
        bins = accuracy_by_percentile([(10.0, "W"), (1.0, "P")])
        top = bins[0]
        self.assertEqual(top["wins"], 1)
        self.assertEqual(top["accuracy"], 1.0)
        bottom = next(b for b in bins if b["pushes"])
        self.assertEqual(bottom["accuracy"], None)
        self.assertEqual(bottom["games"], 1)

    def test_empty_sample_still_returns_eight_bins(self) -> None:
        bins = accuracy_by_percentile([])
        self.assertEqual(len(bins), 8)
        self.assertTrue(
            all(b["games"] == 0 and b["accuracy"] is None and b["cutoff"] is None for b in bins)
        )


if __name__ == "__main__":
    unittest.main()
