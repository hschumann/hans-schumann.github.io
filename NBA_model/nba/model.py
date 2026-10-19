"""7-day ATS mean-reversion picks (NBA adaptation of the NFL public-overreaction theory)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from nba.storage import Game, Store


@dataclass
class TeamWindowScore:
    team: str
    avg_ats: float
    games: int
    total_ats: float


@dataclass
class Pick:
    rank: int
    game_id: str
    tipoff_utc: str
    home_team: str
    away_team: str
    home_spread: float | None
    home_score_7d: float
    away_score_7d: float
    home_games_7d: int
    away_games_7d: int
    abs_diff: float
    bet_team: str
    bet_spread: float | None
    against_team: str

    @property
    def message(self) -> str:
        spread_txt = ""
        if self.bet_spread is not None:
            spread_txt = f" {self.bet_spread:+g}"
        loc = "vs" if self.bet_team == self.home_team else "@"
        return (
            f"{self.bet_team}{spread_txt} {loc} {self.against_team} "
            f"(Δ{self.abs_diff:.1f}: {self.bet_team} {self._bet_score():+.1f} "
            f"vs {self.against_team} {self._against_score():+.1f})"
        )

    def _bet_score(self) -> float:
        return (
            self.home_score_7d
            if self.bet_team == self.home_team
            else self.away_score_7d
        )

    def _against_score(self) -> float:
        return (
            self.away_score_7d
            if self.bet_team == self.home_team
            else self.home_score_7d
        )

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "game_id": self.game_id,
            "tipoff_utc": self.tipoff_utc,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "home_spread": self.home_spread,
            "home_score_7d": round(self.home_score_7d, 3),
            "away_score_7d": round(self.away_score_7d, 3),
            "home_games_7d": self.home_games_7d,
            "away_games_7d": self.away_games_7d,
            "abs_diff": round(self.abs_diff, 3),
            "bet_team": self.bet_team,
            "bet_spread": self.bet_spread,
            "against_team": self.against_team,
            "message": self.message,
        }


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def team_ats_scores(
    games: list[Game],
) -> dict[str, TeamWindowScore]:
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for g in games:
        if g.home_ats is None or g.away_ats is None:
            continue
        totals[g.home_team] += g.home_ats
        counts[g.home_team] += 1
        totals[g.away_team] += g.away_ats
        counts[g.away_team] += 1
    out: dict[str, TeamWindowScore] = {}
    for team, total in totals.items():
        n = counts[team]
        out[team] = TeamWindowScore(
            team=team, avg_ats=total / n, games=n, total_ats=total
        )
    return out


def local_day_bounds(day_local: datetime, tz_name: str) -> tuple[str, str]:
    """Return [start, end) UTC ISO bounds for a local calendar day."""
    tz = ZoneInfo(tz_name)
    start_local = day_local.astimezone(tz).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_local = start_local + timedelta(days=1)
    start = start_local.astimezone(timezone.utc).replace(microsecond=0)
    end = end_local.astimezone(timezone.utc).replace(microsecond=0)
    return (
        start.isoformat().replace("+00:00", "Z"),
        end.isoformat().replace("+00:00", "Z"),
    )


def compute_picks(
    store: Store,
    *,
    as_of: datetime | None = None,
    lookback_days: int = 7,
    top_n: int = 3,
    timezone_name: str = "America/New_York",
    min_games: int = 1,
) -> list[Pick]:
    """
    Score each team by average ATS margin over the trailing lookback window,
    then rank today's matchups by |home_7d - away_7d|.

    Bet the underperformer (lower / more negative 7-day ATS average).
    """
    as_of = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    window_end = as_of
    window_start = as_of - timedelta(days=lookback_days)
    completed = store.completed_with_ats(
        window_start.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        window_end.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    scores = team_ats_scores(completed)

    day_start, day_end = local_day_bounds(as_of, timezone_name)
    todays = [
        g
        for g in store.list_games(tipoff_from=day_start, tipoff_to=day_end)
        if g.status in {"scheduled", "in_progress"} and g.home_spread is not None
    ]

    candidates: list[Pick] = []
    for g in todays:
        home = scores.get(g.home_team)
        away = scores.get(g.away_team)
        if not home or not away:
            continue
        if home.games < min_games or away.games < min_games:
            continue
        abs_diff = abs(home.avg_ats - away.avg_ats)
        # Bet the team that underperformed ATS recently
        if home.avg_ats < away.avg_ats:
            bet_team = g.home_team
            against = g.away_team
            bet_spread = g.home_spread
        else:
            bet_team = g.away_team
            against = g.home_team
            bet_spread = None if g.home_spread is None else -g.home_spread

        candidates.append(
            Pick(
                rank=0,
                game_id=g.game_id,
                tipoff_utc=g.tipoff_utc,
                home_team=g.home_team,
                away_team=g.away_team,
                home_spread=g.home_spread,
                home_score_7d=home.avg_ats,
                away_score_7d=away.avg_ats,
                home_games_7d=home.games,
                away_games_7d=away.games,
                abs_diff=abs_diff,
                bet_team=bet_team,
                bet_spread=bet_spread,
                against_team=against,
            )
        )

    candidates.sort(key=lambda p: (-p.abs_diff, p.tipoff_utc, p.game_id))
    ranked: list[Pick] = []
    for i, pick in enumerate(candidates[:top_n], start=1):
        ranked.append(
            Pick(
                rank=i,
                game_id=pick.game_id,
                tipoff_utc=pick.tipoff_utc,
                home_team=pick.home_team,
                away_team=pick.away_team,
                home_spread=pick.home_spread,
                home_score_7d=pick.home_score_7d,
                away_score_7d=pick.away_score_7d,
                home_games_7d=pick.home_games_7d,
                away_games_7d=pick.away_games_7d,
                abs_diff=pick.abs_diff,
                bet_team=pick.bet_team,
                bet_spread=pick.bet_spread,
                against_team=pick.against_team,
            )
        )
    return ranked


def format_alert(picks: list[Pick], *, pick_date: str) -> str:
    if not picks:
        return f"NBA ATS ({pick_date}): no qualifying games today."
    lines = [f"NBA ATS top {len(picks)} ({pick_date}):"]
    for p in picks:
        lines.append(f"{p.rank}) {p.message}")
    return "\n".join(lines)


# Back-compat alias
format_sms = format_alert

