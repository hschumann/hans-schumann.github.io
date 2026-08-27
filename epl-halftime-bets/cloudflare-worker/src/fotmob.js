/** Shared helpers for FotMob match parsing and HT scores. */

export function normalizeTeam(name) {
  const cleaned = String(name || "").trim();
  return TEAM_ALIASES[cleaned] || cleaned;
}

const TEAM_ALIASES = {
  "Nottm Forest": "Nott'm Forest",
  "Nottingham Forest": "Nott'm Forest",
  "Manchester United": "Man United",
  "Manchester City": "Man City",
  "Newcastle United": "Newcastle",
  "Tottenham Hotspur": "Tottenham",
  "Wolverhampton Wanderers": "Wolves",
  "West Ham United": "West Ham",
  "Brighton and Hove Albion": "Brighton",
  "Brighton & Hove Albion": "Brighton",
  "Ipswich Town": "Ipswich",
  "Leicester City": "Leicester",
};

export function parseScore(scoreStr) {
  if (!scoreStr) return null;
  const parts = String(scoreStr).split("-").map((s) => s.trim());
  if (parts.length !== 2) return null;
  const home = Number(parts[0]);
  const away = Number(parts[1]);
  if (Number.isNaN(home) || Number.isNaN(away)) return null;
  return { home, away };
}

export function classifyPhase(status, reason) {
  const key = String(reason?.shortKey || "").toLowerCase();
  const short = String(reason?.short || "").toLowerCase();
  const longKey = String(reason?.longKey || "").toLowerCase();
  const halfs = status?.halfs || {};

  if (!status?.started) return "not_started";
  if (status.finished || key.includes("fulltime") || longKey.includes("finished")) {
    return "finished";
  }

  const atHalftime =
    key.includes("halftime") ||
    short === "ht" ||
    longKey.includes("halftime") ||
    key.includes("pause") ||
    (Boolean(halfs.firstHalfEnded) && !halfs.secondHalfStarted);

  if (atHalftime) return "halftime";

  if (halfs.secondHalfStarted) return "second_half";
  return "first_half";
}

export function halftimeScoreFromEvents(details) {
  const events = details?.header?.events || {};
  let home = 0;
  let away = 0;

  for (const goalList of Object.values(events.homeTeamGoals || {})) {
    for (const goal of goalList) {
      if (isFirstHalfGoal_(goal)) home += 1;
    }
  }
  for (const goalList of Object.values(events.awayTeamGoals || {})) {
    for (const goal of goalList) {
      if (isFirstHalfGoal_(goal)) away += 1;
    }
  }

  if (home + away > 0) return { home, away };

  const shots = details?.content?.shotmap?.shots || [];
  const homeId = details?.general?.homeTeam?.id ?? details?.header?.teams?.[0]?.id;
  for (const shot of shots) {
    if (shot.period !== "FirstHalf") continue;
    if (String(shot.eventType || "").toLowerCase() !== "goal") continue;
    if (Number(shot.teamId) === Number(homeId)) home += 1;
    else away += 1;
  }

  return { home, away };
}

function isFirstHalfGoal_(goal) {
  const period = goal?.shotmapEvent?.period;
  if (period === "FirstHalf") return true;
  const minute = Number(goal?.time ?? goal?.timeStr ?? 999);
  return minute <= 45;
}

export function findOdds(oddsPayload, date, home, away) {
  const fixtures = oddsPayload?.fixtures || [];
  const matchDate = (date || "").slice(0, 10);
  return (
    fixtures.find(
      (f) =>
        f.date === matchDate &&
        normalizeTeam(f.home_team) === home &&
        normalizeTeam(f.away_team) === away
    ) || null
  );
}

export function phaseSortRank(phase) {
  const order = {
    halftime: 0,
    first_half: 1,
    second_half: 2,
    not_started: 3,
    finished: 4,
  };
  return order[phase] ?? 9;
}

export function round(value, digits) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}
