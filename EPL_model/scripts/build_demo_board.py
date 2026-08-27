#!/usr/bin/env python3
"""Build a static demo board from historical HT scores (no live games needed)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from football_data.loader import load_epl_matches
from football_data.odds import add_fair_over_under, add_fair_probabilities
from models.odds_half_goals import expected_goals_from_odds, predicted_final_from_halftime

DEFAULT_OUTPUT = PROJECT_ROOT.parent / "epl-halftime-bets" / "board.json"
NO_BET_THRESHOLD = 0.5


def recommend(pred_total: float) -> dict:
    edge = pred_total - 2.5
    if edge >= NO_BET_THRESHOLD:
        return {"call": "over", "label": "OVER", "edge": edge}
    if edge <= -NO_BET_THRESHOLD:
        return {"call": "under", "label": "UNDER", "edge": edge}
    return {"call": "no_bet", "label": "NO BET", "edge": edge}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build demo HT board from past matches.")
    parser.add_argument("--season", default="2025/26")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    matches = load_epl_matches()
    matches = add_fair_probabilities(matches, prefix="avg")
    matches = add_fair_over_under(matches)
    matches = matches.dropna(
        subset=["ht_home_goals", "ht_away_goals", "home_goals", "away_goals", "fair_home"]
    )
    matches = matches[matches["season"] == args.season].sort_values("date").tail(args.limit)

    rows = []
    for match in matches.itertuples(index=False):
        expected = expected_goals_from_odds(match.fair_home, match.fair_over_2_5)
        pred_home, pred_away = predicted_final_from_halftime(
            match.ht_home_goals,
            match.ht_away_goals,
            expected["expected_2h_home"],
            expected["expected_2h_away"],
        )
        pred_total = pred_home + pred_away
        bet = recommend(pred_total)
        actual_total = int(match.home_goals + match.away_goals)
        rows.append(
            {
                "match_id": None,
                "home_team": match.home_team,
                "away_team": match.away_team,
                "kickoff_utc": f"{match.date.date()}T00:00:00Z",
                "phase": "halftime",
                "status_label": "Demo (historical HT)",
                "score_str": f"{int(match.ht_home_goals)} - {int(match.ht_away_goals)}",
                "ht_home": int(match.ht_home_goals),
                "ht_away": int(match.ht_away_goals),
                "pred_ft_home": round(pred_home, 2),
                "pred_ft_away": round(pred_away, 2),
                "pred_total": round(pred_total, 2),
                "call": bet["call"],
                "call_label": bet["label"],
                "edge": round(bet["edge"], 2),
                "odds_matched": True,
                "fair_home": round(float(match.fair_home), 3),
                "fair_over_2_5": round(float(match.fair_over_2_5), 3),
                "actual_ft": f"{int(match.home_goals)}-{int(match.away_goals)}",
                "actual_total": actual_total,
                "result_hit": (
                    (bet["call"] == "over" and actual_total >= 3)
                    or (bet["call"] == "under" and actual_total <= 2)
                    or bet["call"] == "no_bet"
                ),
            }
        )

    board = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "date": "demo",
        "source": "historical demo from Football-Data HT scores",
        "disclaimer": "Demo board — not live. Research tool only, not betting advice.",
        "rules": {
            "line": 2.5,
            "over": "pred_total >= 3.0",
            "under": "pred_total <= 2.0",
            "no_bet": "2.0 < pred_total < 3.0",
        },
        "matches": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(board, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} demo matches -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
