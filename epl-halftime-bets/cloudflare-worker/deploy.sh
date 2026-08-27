#!/usr/bin/env bash
# Deploy Cloudflare Worker for live HT board.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKER_DIR="$ROOT/cloudflare-worker"

cd "$WORKER_DIR"

if [[ ! -d node_modules ]]; then
  npm install
fi

if ! grep -q 'id = "' wrangler.toml 2>/dev/null; then
  echo "KV namespace not configured in wrangler.toml."
  echo "Run:"
  echo "  npx wrangler kv namespace create HT_BOARD"
  echo "Then uncomment [[kv_namespaces]] in wrangler.toml and paste the id."
  echo ""
  echo "Deploying without KV (no cache, slower refresh)..."
fi

npx wrangler deploy

echo ""
echo "Next: set workerUrl in ../config.js to your workers.dev URL, then commit and push."
