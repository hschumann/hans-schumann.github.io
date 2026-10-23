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


def rank_slate(
    store: Store,
    *,
    as_of: datetime | None = None,
    lookback_days: int = 7,
    timezone_name: str = "America/New_York",
    min_games: int = 1,
) -> list[Pick]:
    """
    Score each team by average ATS margin over the trailing lookback window,
    then rank every qualifying game on that local day by |home_7d - away_7d|.

    Bet the underperformer (lower / more negative 7-day ATS average).
    """
    as_of = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    window_end = as_of
    window_start = as_of - timedelta(days=lookback_days)
    completed = store.completed_with_ats(
        window_start.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        window_end.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    day_start, day_end = local_day_bounds(as_of, timezone_name)
    # Keep each delta pregame: don't fold today's results back into the averages.
    scores = team_ats_scores([g for g in completed if g.tipoff_utc < day_start])
    todays = [
        g
        for g in store.list_games(tipoff_from=day_start, tipoff_to=day_end)
        if g.status in {"scheduled", "in_progress", "final"} and g.home_spread is not None
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
    for i, pick in enumerate(candidates, start=1):
        pick.rank = i
    return candidates


def compute_picks(
    store: Store,
    *,
    as_of: datetime | None = None,
    lookback_days: int = 7,
    top_n: int = 3,
    timezone_name: str = "America/New_York",
    min_games: int = 1,
) -> list[Pick]:
    """Top `top_n` games from the day's slate, already sorted by |Δ|."""
    return rank_slate(
        store,
        as_of=as_of,
        lookback_days=lookback_days,
        timezone_name=timezone_name,
        min_games=min_games,
    )[:top_n]


# Eight equal bands, largest |Δ| first. Each cutoff is the |Δ| at `low`.
PERCENTILE_BINS: tuple[tuple[float, float], ...] = (
    (87.5, 100),
    (75, 87.5),
    (62.5, 75),
    (50, 62.5),
    (37.5, 50),
    (25, 37.5),
    (12.5, 25),
    (0, 12.5),
)


def _pct_label(value: float) -> str:
    return f"{value:g}th"


def accuracy_by_percentile(samples: list[tuple[float, str]]) -> list[dict]:
    """Win rate of graded bets in eight |Δ| percentile bins.

    `samples` are `(abs_diff, result)` with result in {W, L, P}.
    A bin's cutoff is the interpolated |Δ| at its lower percentile.
    A game belongs to the highest bin whose cutoff it clears.
    Accuracy ignores pushes.
    """
    diffs = [diff for diff, _ in samples]
    ordered = sorted(diffs)
    cutoffs = (
        [_percentile_value(ordered, low) for low, _ in PERCENTILE_BINS]
        if ordered
        else [None] * len(PERCENTILE_BINS)
    )
    grouped: list[list[tuple[float, str]]] = [[] for _ in PERCENTILE_BINS]
    for sample in samples:
        grouped[_bin_for_diff(sample[0], cutoffs)].append(sample)

    bins: list[dict] = []
    for (low, high), cutoff, rows in zip(PERCENTILE_BINS, cutoffs, grouped):
        wins = sum(1 for _, result in rows if result == "W")
        losses = sum(1 for _, result in rows if result == "L")
        pushes = sum(1 for _, result in rows if result == "P")
        decided = wins + losses
        bins.append(
            {
                "label": f"{_pct_label(low)}–{_pct_label(high)}",
                "low": low,
                "high": high,
                "cutoff": round(cutoff, 3) if cutoff is not None else None,
                "games": len(rows),
                "wins": wins,
                "losses": losses,
                "pushes": pushes,
                "accuracy": (wins / decided) if decided else None,
            }
        )
    return bins


def _percentile_value(sorted_asc: list[float], pct: float) -> float:
    """Linearly interpolated |Δ| at `pct` (0 = smallest, 100 = largest)."""
    if pct <= 0:
        return sorted_asc[0]
    if pct >= 100:
        return sorted_asc[-1]
    rank = pct / 100 * (len(sorted_asc) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_asc) - 1)
    frac = rank - lo
    return sorted_asc[lo] * (1 - frac) + sorted_asc[hi] * frac


def _bin_for_diff(diff: float, cutoffs: list[float | None]) -> int:
    for index, cutoff in enumerate(cutoffs):
        if cutoff is not None and diff + 1e-9 >= cutoff:
            return index
    return len(cutoffs) - 1


def format_alert(picks: list[Pick], *, pick_date: str) -> str:
    if not picks:
        return f"NBA ATS ({pick_date}): no qualifying games today."
    lines = [f"NBA ATS top {len(picks)} ({pick_date}):"]
    for p in picks:
        lines.append(f"{p.rank}) {p.message}")
    return "\n".join(lines)


# Back-compat alias
format_sms = format_alert

