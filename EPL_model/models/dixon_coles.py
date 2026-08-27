"""Dixon-Coles Poisson baseline for match scorelines."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson


MAX_GOALS = 10


@dataclass
class DixonColesModel:
    teams: list[str]
    attack: dict[str, float]
    defense: dict[str, float]
    home_advantage: float
    rho: float
    intercept: float

    def expected_goals(self, home_team: str, away_team: str) -> tuple[float, float]:
        home_rate = np.exp(
            self.intercept
            + self.home_advantage
            + self.attack[home_team]
            - self.defense[away_team]
        )
        away_rate = np.exp(
            self.intercept + self.attack[away_team] - self.defense[home_team]
        )
        return float(home_rate), float(away_rate)


def _dixon_coles_tau(
    home_goals: int,
    away_goals: int,
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lambda_away * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + lambda_home * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def _negative_log_likelihood(
    params: np.ndarray,
    home_idx: np.ndarray,
    away_idx: np.ndarray,
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    team_count: int,
) -> float:
    intercept = params[0]
    home_advantage = params[1]
    rho = params[2]
    attack = params[3 : 3 + team_count]
    defense = params[3 + team_count : 3 + 2 * team_count]

    attack_centered = attack - attack.mean()
    defense_centered = defense - defense.mean()

    log_lambda_home = intercept + home_advantage + attack_centered[home_idx] - defense_centered[away_idx]
    log_lambda_away = intercept + attack_centered[away_idx] - defense_centered[home_idx]
    lambda_home = np.exp(log_lambda_home)
    lambda_away = np.exp(log_lambda_away)

    tau = np.array(
        [
            _dixon_coles_tau(int(h), int(a), lh, la, rho)
            for h, a, lh, la in zip(home_goals, away_goals, lambda_home, lambda_away)
        ],
        dtype=float,
    )
    if np.any(tau <= 0):
        return 1e12

    ll = np.sum(
        np.log(tau)
        + home_goals * log_lambda_home
        - lambda_home
        + away_goals * log_lambda_away
        - lambda_away
        - gammaln(home_goals + 1)
        - gammaln(away_goals + 1)
    )
    return float(-ll)


def fit_dixon_coles(matches: pd.DataFrame) -> DixonColesModel:
    """Fit attack/defence strengths on completed matches with goal columns."""
    required = {"home_team", "away_team", "home_goals", "away_goals"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    frame = matches.dropna(subset=["home_goals", "away_goals"]).copy()
    frame["home_goals"] = frame["home_goals"].astype(int)
    frame["away_goals"] = frame["away_goals"].astype(int)

    teams = sorted(set(frame["home_team"]).union(frame["away_team"]))
    team_to_idx = {team: index for index, team in enumerate(teams)}

    home_idx = frame["home_team"].map(team_to_idx).to_numpy()
    away_idx = frame["away_team"].map(team_to_idx).to_numpy()
    home_goals = frame["home_goals"].to_numpy()
    away_goals = frame["away_goals"].to_numpy()

    team_count = len(teams)
    initial = np.zeros(3 + 2 * team_count)
    initial[0] = np.log(frame["home_goals"].mean())
    initial[1] = 0.2
    initial[2] = -0.05

    result = minimize(
        _negative_log_likelihood,
        initial,
        args=(home_idx, away_idx, home_goals, away_goals, team_count),
        method="L-BFGS-B",
    )
    if not result.success:
        raise RuntimeError(f"Dixon-Coles fit failed: {result.message}")

    intercept, home_advantage, rho = result.x[:3]
    attack_raw = result.x[3 : 3 + team_count]
    defense_raw = result.x[3 + team_count : 3 + 2 * team_count]
    attack_centered = attack_raw - attack_raw.mean()
    defense_centered = defense_raw - defense_raw.mean()

    return DixonColesModel(
        teams=teams,
        attack={team: float(attack_centered[index]) for index, team in enumerate(teams)},
        defense={team: float(defense_centered[index]) for index, team in enumerate(teams)},
        home_advantage=float(home_advantage),
        rho=float(rho),
        intercept=float(intercept),
    )


def score_matrix(home_rate: float, away_rate: float, rho: float) -> np.ndarray:
    """Return (MAX_GOALS+1) x (MAX_GOALS+1) probability matrix."""
    matrix = np.outer(
        poisson.pmf(np.arange(MAX_GOALS + 1), home_rate),
        poisson.pmf(np.arange(MAX_GOALS + 1), away_rate),
    )
    for home_goals in (0, 1):
        for away_goals in (0, 1):
            tau = _dixon_coles_tau(home_goals, away_goals, home_rate, away_rate, rho)
            matrix[home_goals, away_goals] *= tau
    matrix = np.clip(matrix, 0.0, None)
    return matrix / matrix.sum()


def outcome_probabilities(home_rate: float, away_rate: float, rho: float) -> dict[str, float]:
    matrix = score_matrix(home_rate, away_rate, rho)
    home_win = float(np.tril(matrix, k=-1).sum())
    draw = float(np.trace(matrix))
    away_win = float(np.triu(matrix, k=1).sum())
    return {"home_win": home_win, "draw": draw, "away_win": away_win}


def predict_matches(model: DixonColesModel, fixtures: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for fixture in fixtures.itertuples(index=False):
        home_rate, away_rate = model.expected_goals(fixture.home_team, fixture.away_team)
        probs = outcome_probabilities(home_rate, away_rate, model.rho)
        rows.append(
            {
                "date": getattr(fixture, "date", None),
                "home_team": fixture.home_team,
                "away_team": fixture.away_team,
                "expected_home_goals": round(home_rate, 3),
                "expected_away_goals": round(away_rate, 3),
                "prob_home_win": round(probs["home_win"], 4),
                "prob_draw": round(probs["draw"], 4),
                "prob_away_win": round(probs["away_win"], 4),
            }
        )
    return pd.DataFrame(rows)


def evaluate_predictions(
    model: DixonColesModel,
    matches: pd.DataFrame,
) -> dict[str, float]:
    """Log-loss and Brier score for 1X2 outcomes on completed matches."""
    frame = matches.dropna(subset=["home_goals", "away_goals", "result"]).copy()
    log_loss_total = 0.0
    brier_total = 0.0
    count = 0

    for row in frame.itertuples(index=False):
        home_rate, away_rate = model.expected_goals(row.home_team, row.away_team)
        probs = outcome_probabilities(home_rate, away_rate, model.rho)
        actual = {"H": "home_win", "D": "draw", "A": "away_win"}[row.result]
        predicted_prob = probs[actual]
        log_loss_total += -np.log(max(predicted_prob, 1e-12))
        brier_total += sum(
            (probs[outcome] - (1.0 if outcome == actual else 0.0)) ** 2
            for outcome in ("home_win", "draw", "away_win")
        )
        count += 1

    return {
        "matches": count,
        "log_loss": log_loss_total / count if count else float("nan"),
        "brier_score": brier_total / count if count else float("nan"),
    }
