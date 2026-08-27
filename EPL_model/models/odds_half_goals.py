"""
Odds → expected goals by half, then a halftime-updated final-score mock.

Formulas (independent Poisson, no Dixon–Coles ρ):

1. Fair probabilities (vig stripped)
   p_H, p_D, p_A from AvgH/D/A
   p_over = implied(Avg>2.5) / (implied(Avg>2.5) + implied(Avg<2.5))

2. Expected total goals λ from the over/under
   Independent Poisson total ~ Poisson(λ)
   P(over 2.5) = 1 − e^{−λ} (1 + λ + λ²/2)
   Invert that for λ.

3. Split λ into team rates μ_home, μ_away
   μ_home + μ_away = λ
   Choose share s ∈ (0,1) so μ_home = s λ, μ_away = (1−s) λ
   and the independent-Poisson P(home win) is as close as possible to p_H.

   P(home goals = i) = e^{−μ_h} μ_h^i / i!
   P(home win) = Σ_{i>j} P(i) P(j)

4. Half split (empirical, not 50/50)
   Historical EPL share of goals in the first half is about 0.445,
   so second-half share is about 0.555.
   E[1H home] = μ_home * share_1h
   E[2H home] = μ_home * (1 − share_1h)
   Same for away.

5. Halftime mock final
   Predicted remaining 2H is still the pregame 2H expectation
   (Poisson increments in each half are independent, so 1H score
   does not change the remaining 2H mean).
   pred_FT_home = HT_home + E[2H home]
   pred_FT_away = HT_away + E[2H away]
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq
from scipy.stats import poisson

MAX_GOALS = 12
DEFAULT_FIRST_HALF_SHARE = 0.4452  # EPL 2015/16–2025/26, goals in first half / all goals


def poisson_over_2_5(total_rate: float) -> float:
    """P(total goals >= 3) if total ~ Poisson(total_rate)."""
    return float(1.0 - poisson.cdf(2, total_rate))


def total_rate_from_over_probability(p_over: float) -> float:
    """Invert P(over 2.5) = 1 − e^{−λ}(1 + λ + λ²/2) for λ."""
    p = min(max(float(p_over), 0.05), 0.95)

    def gap(rate: float) -> float:
        return poisson_over_2_5(rate) - p

    return float(brentq(gap, 0.4, 6.5))


def poisson_home_win_probability(mu_home: float, mu_away: float) -> float:
    home_pmf = poisson.pmf(np.arange(MAX_GOALS + 1), mu_home)
    away_pmf = poisson.pmf(np.arange(MAX_GOALS + 1), mu_away)
    matrix = np.outer(home_pmf, away_pmf)
    return float(np.tril(matrix, k=-1).sum() / matrix.sum())


def split_total_rate(total_rate: float, fair_home: float) -> tuple[float, float]:
    """
    Find μ_home, μ_away with μ_home + μ_away = total_rate whose
    Poisson P(home win) matches fair_home as closely as possible.
    """
    target = min(max(float(fair_home), 0.05), 0.92)

    def home_win_gap(share: float) -> float:
        mu_home = share * total_rate
        mu_away = (1.0 - share) * total_rate
        return poisson_home_win_probability(mu_home, mu_away) - target

    low, high = 0.08, 0.92
    if home_win_gap(low) > 0:
        share = low
    elif home_win_gap(high) < 0:
        share = high
    else:
        share = float(brentq(home_win_gap, low, high))

    return share * total_rate, (1.0 - share) * total_rate


def expected_goals_from_odds(
    fair_home: float,
    fair_over_2_5: float,
    first_half_share: float = DEFAULT_FIRST_HALF_SHARE,
) -> dict[str, float]:
    total_rate = total_rate_from_over_probability(fair_over_2_5)
    mu_home, mu_away = split_total_rate(total_rate, fair_home)
    share_1h = float(first_half_share)
    share_2h = 1.0 - share_1h
    return {
        "expected_total_goals": total_rate,
        "expected_home_goals": mu_home,
        "expected_away_goals": mu_away,
        "share_1h": share_1h,
        "share_2h": share_2h,
        "expected_1h_home": mu_home * share_1h,
        "expected_1h_away": mu_away * share_1h,
        "expected_2h_home": mu_home * share_2h,
        "expected_2h_away": mu_away * share_2h,
    }


def predicted_final_from_halftime(
    ht_home: float,
    ht_away: float,
    expected_2h_home: float,
    expected_2h_away: float,
) -> tuple[float, float]:
    """pred_FT = actual HT + pregame expected second-half goals."""
    return float(ht_home) + float(expected_2h_home), float(ht_away) + float(expected_2h_away)
