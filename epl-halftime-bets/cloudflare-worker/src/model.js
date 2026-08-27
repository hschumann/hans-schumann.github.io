/**
 * Odds → expected goals by half (JS port of models/odds_half_goals.py).
 */

const MAX_GOALS = 12;
const FIRST_HALF_SHARE = 0.4452;
const NO_BET_THRESHOLD = 0.5;

function logFactorial(n) {
  if (n <= 1) return 0;
  let total = 0;
  for (let i = 2; i <= n; i++) total += Math.log(i);
  return total;
}

function poissonPmf(k, lambda) {
  if (lambda <= 0) return k === 0 ? 1 : 0;
  return Math.exp(-lambda + k * Math.log(lambda) - logFactorial(k));
}

function poissonOver25(lambda) {
  return 1 - poissonPmf(0, lambda) - poissonPmf(1, lambda) - poissonPmf(2, lambda);
}

function bisect(fn, lo, hi, tolerance = 1e-6) {
  let a = lo;
  let b = hi;
  let fa = fn(a);
  let fb = fn(b);
  if (fa === 0) return a;
  if (fb === 0) return b;
  if (fa * fb > 0) {
    return Math.abs(fa) < Math.abs(fb) ? a : b;
  }
  for (let i = 0; i < 80; i++) {
    const mid = (a + b) / 2;
    const fm = fn(mid);
    if (Math.abs(fm) < tolerance) return mid;
    if (fa * fm <= 0) {
      b = mid;
      fb = fm;
    } else {
      a = mid;
      fa = fm;
    }
  }
  return (a + b) / 2;
}

function totalRateFromOverProbability(pOver) {
  const p = Math.min(Math.max(pOver, 0.05), 0.95);
  return bisect((rate) => poissonOver25(rate) - p, 0.4, 6.5);
}

function poissonHomeWinProbability(muHome, muAway) {
  const homePmf = Array.from({ length: MAX_GOALS + 1 }, (_, i) => poissonPmf(i, muHome));
  const awayPmf = Array.from({ length: MAX_GOALS + 1 }, (_, j) => poissonPmf(j, muAway));
  let total = 0;
  let homeWin = 0;
  for (let i = 0; i <= MAX_GOALS; i++) {
    for (let j = 0; j <= MAX_GOALS; j++) {
      const prob = homePmf[i] * awayPmf[j];
      total += prob;
      if (i > j) homeWin += prob;
    }
  }
  return total > 0 ? homeWin / total : 0;
}

function splitTotalRate(totalRate, fairHome) {
  const target = Math.min(Math.max(fairHome, 0.05), 0.92);
  const gap = (share) => {
    const muHome = share * totalRate;
    const muAway = (1 - share) * totalRate;
    return poissonHomeWinProbability(muHome, muAway) - target;
  };
  const low = 0.08;
  const high = 0.92;
  if (gap(low) > 0) return [low * totalRate, (1 - low) * totalRate];
  if (gap(high) < 0) return [high * totalRate, (1 - high) * totalRate];
  const share = bisect(gap, low, high);
  return [share * totalRate, (1 - share) * totalRate];
}

export function expectedGoalsFromOdds(fairHome, fairOver25) {
  const totalRate = totalRateFromOverProbability(fairOver25);
  const [muHome, muAway] = splitTotalRate(totalRate, fairHome);
  const share2h = 1 - FIRST_HALF_SHARE;
  return {
    expected_total_goals: totalRate,
    expected_home_goals: muHome,
    expected_away_goals: muAway,
    expected_2h_home: muHome * share2h,
    expected_2h_away: muAway * share2h,
  };
}

export function predictedFinalFromHalftime(htHome, htAway, expected2hHome, expected2hAway) {
  return {
    pred_home: htHome + expected2hHome,
    pred_away: htAway + expected2hAway,
    pred_total: htHome + htAway + expected2hHome + expected2hAway,
  };
}

export function recommendBet(predTotal, threshold = NO_BET_THRESHOLD) {
  const edge = predTotal - 2.5;
  if (edge >= threshold) {
    return { call: "over", label: "OVER", edge: edge };
  }
  if (edge <= -threshold) {
    return { call: "under", label: "UNDER", edge: edge };
  }
  return { call: "no_bet", label: "NO BET", edge: edge };
}

export function buildHalftimeRecommendation(odds, htHome, htAway) {
  const expected = expectedGoalsFromOdds(odds.fair_home, odds.fair_over_2_5);
  const predicted = predictedFinalFromHalftime(
    htHome,
    htAway,
    expected.expected_2h_home,
    expected.expected_2h_away
  );
  const bet = recommendBet(predicted.pred_total);
  return { expected, predicted, bet };
}
