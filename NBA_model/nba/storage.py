from __future__ import annotations

import csv
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    tipoff_utc TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_spread REAL,
    spread_source TEXT,
    spread_captured_at TEXT,
    home_score INTEGER,
    away_score INTEGER,
    home_ats REAL,
    away_ats REAL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_tipoff ON games(tipoff_utc);
CREATE INDEX IF NOT EXISTS idx_games_status ON games(status);

CREATE TABLE IF NOT EXISTS picks (
    pick_date TEXT NOT NULL,
    rank INTEGER NOT NULL,
    game_id TEXT NOT NULL,
    bet_team TEXT NOT NULL,
    bet_spread REAL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_score_7d REAL,
    away_score_7d REAL,
    abs_diff REAL NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (pick_date, rank)
);
"""


@dataclass
class Game:
    game_id: str
    tipoff_utc: str
    home_team: str
    away_team: str
    home_spread: float | None = None
    spread_source: str | None = None
    spread_captured_at: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    home_ats: float | None = None
    away_ats: float | None = None
    status: str = "scheduled"
    updated_at: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Store:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def upsert_scheduled(
        self,
        *,
        game_id: str,
        tipoff_utc: str,
        home_team: str,
        away_team: str,
    ) -> None:
        """Ensure a scheduled game row exists (no spread yet)."""
        now = utc_now()
        self._conn.execute(
            """
            INSERT INTO games (
                game_id, tipoff_utc, home_team, away_team, status, updated_at
            ) VALUES (?, ?, ?, ?, 'scheduled', ?)
            ON CONFLICT(game_id) DO UPDATE SET
                tipoff_utc = excluded.tipoff_utc,
                home_team = excluded.home_team,
                away_team = excluded.away_team,
                updated_at = excluded.updated_at
            WHERE games.status = 'scheduled'
            """,
            (game_id, tipoff_utc, home_team, away_team, now),
        )
        self._conn.commit()

    def upsert_spread(
        self,
        *,
        game_id: str,
        tipoff_utc: str,
        home_team: str,
        away_team: str,
        home_spread: float,
        spread_source: str,
        freeze_if_started: bool = True,
    ) -> None:
        """Insert/update pregame spread. Once tipoff passed, keep last pregame line."""
        now = utc_now()
        existing = self.get_game(game_id)
        if existing and existing.home_spread is not None:
            if freeze_if_started and existing.status in {"final", "in_progress"}:
                return
            # Keep last pregame snapshot once tipoff has passed.
            if freeze_if_started and tipoff_utc <= now and existing.spread_captured_at:
                return

        self._conn.execute(
            """
            INSERT INTO games (
                game_id, tipoff_utc, home_team, away_team, home_spread,
                spread_source, spread_captured_at, status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'scheduled', ?)
            ON CONFLICT(game_id) DO UPDATE SET
                tipoff_utc = excluded.tipoff_utc,
                home_team = excluded.home_team,
                away_team = excluded.away_team,
                home_spread = excluded.home_spread,
                spread_source = excluded.spread_source,
                spread_captured_at = excluded.spread_captured_at,
                updated_at = excluded.updated_at
            WHERE games.status = 'scheduled'
            """,
            (
                game_id,
                tipoff_utc,
                home_team,
                away_team,
                home_spread,
                spread_source,
                now,
                now,
            ),
        )
        self._conn.commit()

    def set_spread_for_completed(
        self,
        game_id: str,
        home_spread: float,
        spread_source: str,
    ) -> None:
        """Attach a closing line to a finished game and recompute ATS."""
        now = utc_now()
        existing = self.get_game(game_id)
        if not existing:
            return
        home_ats = away_ats = None
        if (
            existing.status == "final"
            and existing.home_score is not None
            and existing.away_score is not None
        ):
            home_ats = (existing.home_score - existing.away_score) + home_spread
            away_ats = -home_ats
        self._conn.execute(
            """
            UPDATE games SET
                home_spread = ?,
                spread_source = ?,
                spread_captured_at = COALESCE(spread_captured_at, ?),
                home_ats = ?,
                away_ats = ?,
                updated_at = ?
            WHERE game_id = ?
            """,
            (home_spread, spread_source, now, home_ats, away_ats, now, game_id),
        )
        self._conn.commit()

    def upsert_result(
        self,
        *,
        game_id: str,
        tipoff_utc: str,
        home_team: str,
        away_team: str,
        home_score: int,
        away_score: int,
        status: str = "final",
    ) -> None:
        now = utc_now()
        existing = self.get_game(game_id)
        home_spread = existing.home_spread if existing else None
        home_ats = away_ats = None
        if home_spread is not None and status == "final":
            margin = home_score - away_score
            home_ats = margin + home_spread
            away_ats = -home_ats

        self._conn.execute(
            """
            INSERT INTO games (
                game_id, tipoff_utc, home_team, away_team,
                home_score, away_score, home_ats, away_ats, status, updated_at,
                home_spread, spread_source, spread_captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id) DO UPDATE SET
                tipoff_utc = excluded.tipoff_utc,
                home_team = excluded.home_team,
                away_team = excluded.away_team,
                home_score = excluded.home_score,
                away_score = excluded.away_score,
                home_ats = CASE
                    WHEN games.home_spread IS NOT NULL AND excluded.status = 'final'
                    THEN (excluded.home_score - excluded.away_score) + games.home_spread
                    ELSE games.home_ats
                END,
                away_ats = CASE
                    WHEN games.home_spread IS NOT NULL AND excluded.status = 'final'
                    THEN -((excluded.home_score - excluded.away_score) + games.home_spread)
                    ELSE games.away_ats
                END,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                game_id,
                tipoff_utc,
                home_team,
                away_team,
                home_score,
                away_score,
                home_ats,
                away_ats,
                status,
                now,
                home_spread,
                existing.spread_source if existing else None,
                existing.spread_captured_at if existing else None,
            ),
        )
        self._conn.commit()

    def get_game(self, game_id: str) -> Game | None:
        row = self._conn.execute(
            "SELECT * FROM games WHERE game_id = ?", (game_id,)
        ).fetchone()
        return _row_to_game(row) if row else None

    def list_games(
        self,
        *,
        status: str | None = None,
        tipoff_from: str | None = None,
        tipoff_to: str | None = None,
    ) -> list[Game]:
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if tipoff_from:
            clauses.append("tipoff_utc >= ?")
            params.append(tipoff_from)
        if tipoff_to:
            clauses.append("tipoff_utc < ?")
            params.append(tipoff_to)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM games {where} ORDER BY tipoff_utc", params
        ).fetchall()
        return [_row_to_game(r) for r in rows]

    def completed_with_ats(self, since_utc: str, until_utc: str) -> list[Game]:
        rows = self._conn.execute(
            """
            SELECT * FROM games
            WHERE status = 'final'
              AND home_ats IS NOT NULL
              AND tipoff_utc >= ?
              AND tipoff_utc < ?
            ORDER BY tipoff_utc
            """,
            (since_utc, until_utc),
        ).fetchall()
        return [_row_to_game(r) for r in rows]

    def save_picks(self, pick_date: str, picks: Iterable[dict]) -> None:
        self._conn.execute("DELETE FROM picks WHERE pick_date = ?", (pick_date,))
        now = utc_now()
        for pick in picks:
            self._conn.execute(
                """
                INSERT INTO picks (
                    pick_date, rank, game_id, bet_team, bet_spread,
                    home_team, away_team, home_score_7d, away_score_7d,
                    abs_diff, message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pick_date,
                    pick["rank"],
                    pick["game_id"],
                    pick["bet_team"],
                    pick.get("bet_spread"),
                    pick["home_team"],
                    pick["away_team"],
                    pick["home_score_7d"],
                    pick["away_score_7d"],
                    pick["abs_diff"],
                    pick["message"],
                    now,
                ),
            )
        self._conn.commit()

    def export_games_csv(self, path: Path) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        games = self.list_games()
        fields = list(asdict(Game(game_id="", tipoff_utc="", home_team="", away_team="")).keys())
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for g in games:
                writer.writerow(asdict(g))
        return len(games)


def _row_to_game(row: sqlite3.Row) -> Game:
    return Game(
        game_id=row["game_id"],
        tipoff_utc=row["tipoff_utc"],
        home_team=row["home_team"],
        away_team=row["away_team"],
        home_spread=row["home_spread"],
        spread_source=row["spread_source"],
        spread_captured_at=row["spread_captured_at"],
        home_score=row["home_score"],
        away_score=row["away_score"],
        home_ats=row["home_ats"],
        away_ats=row["away_ats"],
        status=row["status"],
        updated_at=row["updated_at"],
    )