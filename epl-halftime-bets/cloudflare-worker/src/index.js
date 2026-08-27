/**
 * EPL Halftime Bets — Cloudflare Worker
 */

import { buildHalftimeRecommendation } from "./model.js";
import {
  classifyPhase,
  findOdds,
  halftimeScoreFromEvents,
  normalizeTeam,
  parseScore,
  phaseSortRank,
  round,
} from "./fotmob.js";

const PREMIER_LEAGUE_ID = 47;
const FOTMOB_MATCHES = "https://www.fotmob.com/api/data/matches";
const FOTMOB_MATCH = "https://www.fotmob.com/api/data/matchDetails";
const DEFAULT_ODDS_URL =
  "https://hans-schumann.github.io/epl-halftime-bets/odds.json";
const BOARD_KEY = "board";
const ODDS_CACHE_KEY = "odds_cache";
const NO_BET_THRESHOLD = 0.5;

export default {
  async fetch(request, env, ctx) {
    const cors = corsHeaders_();
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    try {
      if (path === "/health") {
        return json_({ ok: true, time: new Date().toISOString() }, 200, cors);
      }

      if (path === "/" || path === "/board") {
        const force = url.searchParams.get("refresh") === "1";
        const board = await getBoard_(env, force);
        return json_(board, 200, cors);
      }

      return json_({ error: "Not found" }, 404, cors);
    } catch (err) {
      return json_({ error: err.message || "Worker failed" }, 502, cors);
    }
  },

  async scheduled(_event, env, ctx) {
    ctx.waitUntil(refreshBoard_(env));
  },
};

async function getBoard_(env, force) {
  if (!force && env.HT_BOARD) {
    const cached = await env.HT_BOARD.get(BOARD_KEY, "json");
    if (cached?.updated) {
      const ageMs = Date.now() - Date.parse(cached.updated);
      if (ageMs < 90_000) return cached;
    }
  }
  return refreshBoard_(env);
}

async function refreshBoard_(env) {
  const oddsPayload = await loadOdds_(env);
  const dates = [todayUtcYyyymmdd_(), yesterdayUtcYyyymmdd_()];
  const seen = new Set();
  const plMatches = [];

  for (const date of dates) {
    const payload = await fotmobFetch_(`${FOTMOB_MATCHES}?date=${date}&ccode3=ENG`);
    for (const match of extractPremierLeagueMatches_(payload)) {
      if (seen.has(match.id)) continue;
      seen.add(match.id);
      plMatches.push(match);
    }
  }

  const rows = [];
  for (const match of plMatches) {
    rows.push(await enrichMatch_(match, oddsPayload));
  }

  rows.sort((a, b) => {
    const phaseDiff = phaseSortRank(a.phase) - phaseSortRank(b.phase);
    if (phaseDiff !== 0) return phaseDiff;
    return String(a.kickoff_utc || "").localeCompare(String(b.kickoff_utc || ""));
  });

  const liveCalls = rows.filter((row) => row.live_call);

  const board = {
    updated: new Date().toISOString(),
    mode: "live",
    dates_fetched: dates.map(formatYyyymmdd_),
    source: "fotmob + football-data odds snapshot",
    disclaimer:
      "Research tool only — not betting advice. Live calls appear at halftime only.",
    rules: {
      line: 2.5,
      over: `pred_total >= ${2.5 + NO_BET_THRESHOLD}`,
      under: `pred_total <= ${2.5 - NO_BET_THRESHOLD}`,
      no_bet: `within ±${NO_BET_THRESHOLD} of 2.5`,
    },
    live_call_count: liveCalls.length,
    matches: rows,
  };

  if (env.HT_BOARD) {
    await env.HT_BOARD.put(BOARD_KEY, JSON.stringify(board));
  }
  return board;
}

async function enrichMatch_(match, oddsPayload) {
  const status = match.status || {};
  const reason = status.reason || {};
  const phase = classifyPhase(status, reason);
  const homeName = normalizeTeam(match.home?.name || "");
  const awayName = normalizeTeam(match.away?.name || "");
  const kickoff = (status.utcTime || "").slice(0, 10);
  const score = parseScore(status.scoreStr);

  const base = {
    match_id: match.id,
    home_team: homeName,
    away_team: awayName,
    kickoff_utc: status.utcTime || null,
    phase,
    status_label: reason.long || reason.short || phase,
    score_str: status.scoreStr || "–",
    ht_home: null,
    ht_away: null,
    pred_ft_home: null,
    pred_ft_away: null,
    pred_total: null,
    call: null,
    call_label: null,
    edge: null,
    live_call: false,
    odds_matched: false,
  };

  const odds = findOdds(oddsPayload, kickoff, homeName, awayName);
  if (odds) {
    base.odds_matched = true;
    base.fair_home = odds.fair_home;
    base.fair_over_2_5 = odds.fair_over_2_5;
  }

  if (phase === "not_started" || !score) {
    return base;
  }

  let htHome = score.home;
  let htAway = score.away;

  if (phase === "halftime") {
    base.ht_home = htHome;
    base.ht_away = htAway;
  } else if (
    phase === "second_half" ||
    phase === "finished" ||
    phase === "first_half"
  ) {
    try {
      const details = await fotmobFetch_(`${FOTMOB_MATCH}?matchId=${match.id}`);
      const ht = halftimeScoreFromEvents(details);
      if (phase === "first_half") {
        base.ht_home = score.home;
        base.ht_away = score.away;
      } else if (ht.home + ht.away > 0 || phase === "finished") {
        base.ht_home = ht.home;
        base.ht_away = ht.away;
      } else {
        base.ht_home = htHome;
        base.ht_away = htAway;
      }
    } catch {
      base.ht_home = htHome;
      base.ht_away = htAway;
    }
  }

  if (!odds || base.ht_home == null) {
    return base;
  }

  if (phase === "halftime") {
    const rec = buildHalftimeRecommendation(odds, base.ht_home, base.ht_away);
    base.pred_ft_home = round(rec.predicted.pred_home, 2);
    base.pred_ft_away = round(rec.predicted.pred_away, 2);
    base.pred_total = round(rec.predicted.pred_total, 2);
    base.call = rec.bet.call;
    base.call_label = rec.bet.label;
    base.edge = round(rec.bet.edge, 2);
    base.live_call = true;
  } else if (phase === "second_half" || phase === "finished") {
    const rec = buildHalftimeRecommendation(odds, base.ht_home, base.ht_away);
    base.pred_ft_home = round(rec.predicted.pred_home, 2);
    base.pred_ft_away = round(rec.predicted.pred_away, 2);
    base.pred_total = round(rec.predicted.pred_total, 2);
    base.call = rec.bet.call;
    base.call_label = rec.bet.label;
    base.edge = round(rec.bet.edge, 2);
    base.call_note = "HT window passed — shown for tracking only";
  }

  return base;
}

function extractPremierLeagueMatches_(payload) {
  const leagues = payload?.leagues || [];
  const rows = [];
  for (const league of leagues) {
    const id = league.id || league.primaryId;
    if (id !== PREMIER_LEAGUE_ID) continue;
    for (const match of league.matches || []) {
      rows.push(match);
    }
  }
  return rows;
}

async function loadOdds_(env) {
  if (env.HT_BOARD) {
    const cached = await env.HT_BOARD.get(ODDS_CACHE_KEY, "json");
    if (cached?.fixtures) {
      const ageMs = Date.now() - Date.parse(cached.updated || 0);
      if (ageMs < 6 * 60 * 60 * 1000) return cached;
    }
  }

  const oddsUrl = env.ODDS_JSON_URL || DEFAULT_ODDS_URL;
  const response = await fetch(oddsUrl, {
    headers: { "User-Agent": "epl-halftime-bets/1.0" },
  });
  if (!response.ok) {
    throw new Error(`Failed to load odds.json (${response.status})`);
  }
  const payload = await response.json();
  if (env.HT_BOARD) {
    await env.HT_BOARD.put(ODDS_CACHE_KEY, JSON.stringify(payload));
  }
  return payload;
}

async function fotmobFetch_(url) {
  const response = await fetch(url, {
    headers: {
      "User-Agent": "epl-halftime-bets/1.0",
      Accept: "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(`FotMob ${response.status} for ${url}`);
  }
  return response.json();
}

function todayUtcYyyymmdd_() {
  return formatParts_(new Date());
}

function yesterdayUtcYyyymmdd_() {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - 1);
  return formatParts_(d);
}

function formatParts_(date) {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  return `${y}${m}${d}`;
}

function formatYyyymmdd_(yyyymmdd) {
  return yyyymmdd.replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3");
}

function corsHeaders_() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };
}

function json_(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      ...cors,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}
