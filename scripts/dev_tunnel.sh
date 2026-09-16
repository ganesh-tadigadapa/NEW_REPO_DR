#!/usr/bin/env bash
# Give Twilio an HTTPS URL for this machine, for a local demo.
#
# Twilio does not accept a file upload. It fetches the media itself, from its own
# network, so the PDF has to sit behind a URL that the public internet can reach.
# On a laptop that means a tunnel. This starts a Cloudflare quick tunnel (no account,
# no config) and writes the https URL it prints into .env as PUBLIC_BASE_URL.
#
# What this exposes, and what it does not:
#
#   Every route on :8080 becomes reachable while this runs. The report PDFs are NOT
#   browsable because of it — /v1/reports/media/{id}.pdf requires an HMAC signature
#   over that one scan id plus an expiry (REPORT_MEDIA_TTL_SECONDS, default 15 min),
#   minted only when an authenticated patient sends their own report. Everything else
#   still requires a session token. But this is a demo tool: stop it when you are done,
#   and do not leave it running unattended.
#
# Usage:  scripts/dev_tunnel.sh [port]     (default 8080)
#         Ctrl-C to stop. Re-run to get a fresh URL.
set -euo pipefail

PORT="${1:-8080}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
LOG="$(mktemp -t dr-tunnel)"

command -v cloudflared >/dev/null || {
  echo "cloudflared is not installed.  brew install cloudflared" >&2; exit 1; }

curl -fsS -o /dev/null "http://localhost:$PORT/health" 2>/dev/null \
  || echo "warning: nothing is answering on :$PORT yet — start the API (make api)" >&2

echo "starting Cloudflare quick tunnel -> http://localhost:$PORT"
cloudflared tunnel --url "http://localhost:$PORT" --no-autoupdate >"$LOG" 2>&1 &
TUNNEL_PID=$!
trap 'kill "$TUNNEL_PID" 2>/dev/null || true; echo; echo "tunnel stopped."' EXIT INT TERM

URL=""
for _ in $(seq 1 40); do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)"
  [ -n "$URL" ] && break
  kill -0 "$TUNNEL_PID" 2>/dev/null || { echo "cloudflared exited:" >&2; cat "$LOG" >&2; exit 1; }
  sleep 1
done
[ -n "$URL" ] || { echo "no tunnel URL after 40s:" >&2; cat "$LOG" >&2; exit 1; }

# Replace PUBLIC_BASE_URL in place if present, otherwise append it.
if grep -q '^PUBLIC_BASE_URL=' "$ENV_FILE" 2>/dev/null; then
  tmp="$(mktemp)"; sed "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=$URL|" "$ENV_FILE" >"$tmp"
  cat "$tmp" >"$ENV_FILE"; rm -f "$tmp"
else
  printf '\nPUBLIC_BASE_URL=%s\n' "$URL" >>"$ENV_FILE"
fi

cat <<MSG

  PUBLIC_BASE_URL=$URL   (written to .env)

  RESTART THE API so it picks this up, then check:
      scripts/check_whatsapp.py

  Leave this terminal open — the URL dies with it.
MSG
wait "$TUNNEL_PID"
