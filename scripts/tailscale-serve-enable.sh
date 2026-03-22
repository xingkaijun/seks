#!/usr/bin/env bash
set -euo pipefail

# Expose SEKS API to your tailnet via Tailscale Serve (NOT public internet).
#
# Default: publish https://<this-hostname> (tailnet TLS) -> http://127.0.0.1:18080
#
# Usage:
#   ./scripts/tailscale-serve-enable.sh            # https on 443
#   ./scripts/tailscale-serve-enable.sh 8443       # https on 8443
#   ./scripts/tailscale-serve-enable.sh 443 http://127.0.0.1:18080

HTTPS_PORT="${1:-443}"
UPSTREAM="${2:-http://127.0.0.1:18080}"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "tailscale not found. Install Tailscale first." >&2
  exit 1
fi

# Serve requires root on most Linux installs.
sudo tailscale serve --bg --https="${HTTPS_PORT}" "${UPSTREAM}"

echo "\nTailscale Serve status:"
sudo tailscale serve status
