/**
 * Cloudflare Worker serves live board data from FotMob.
 * Leave workerUrl empty to fall back to board.json (demo / GitHub Action).
 */
window.HT_BETS_CONFIG = {
  workerUrl: "https://epl-halftime-bets.hans-schumann.workers.dev",
  pollMs: 60000,
};
