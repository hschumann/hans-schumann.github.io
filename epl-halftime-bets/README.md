# EPL Halftime Over/Under — MVP

Research tool: at halftime, recommend **OVER**, **UNDER**, or **NO BET** vs 2.5 goals.

## Quick start (demo, no Worker)

```bash
cd EPL_model
python3 scripts/snapshot_pregame_odds.py
python3 scripts/build_demo_board.py

# Open locally
open ../epl-halftime-bets/index.html
# or: python3 -m http.server 8000  (from repo root)
```

The page loads `board.json` when `config.js` has an empty `workerUrl`.

## Live board (GitHub Action — no Cloudflare)

Two workflows in `.github/workflows/`:

- **epl-odds-snapshot.yml** — refreshes `odds.json` weekly (and on Football-Data updates)
- **epl-live-board.yml** — refreshes `board.json` every 15 min on Sat/Sun

Run locally anytime:

```bash
cd EPL_model
python3 scripts/snapshot_pregame_odds.py
python3 scripts/build_live_board.py
```

Push `odds.json` and `board.json` to GitHub Pages. The page polls `board.json` every 60s.

## Live mode (Cloudflare Worker — lower latency)

```bash
cd epl-halftime-bets/cloudflare-worker
./deploy.sh
# or: npm install && npx wrangler deploy
```

Optional KV cache (recommended):

```bash
npx wrangler kv namespace create HT_BOARD
# paste id into wrangler.toml under [[kv_namespaces]]
npx wrangler deploy
```

Set in `epl-halftime-bets/config.js`:

```js
window.HT_BETS_CONFIG = {
  workerUrl: "https://epl-halftime-bets.<your-subdomain>.workers.dev",
  pollMs: 60000,
};
```

The Worker fetches `odds.json` from GitHub Pages and polls FotMob every 2 minutes (cron).
**Live calls only appear during the halftime window** (`phase === "halftime"`).

## Decision rule

- `pred_total = HT_home + HT_away + E[2H home] + E[2H away]`
- `pred_total >= 3.0` → OVER  
- `pred_total <= 2.0` → UNDER  
- otherwise → NO BET  

Not betting advice.
