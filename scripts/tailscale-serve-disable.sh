#!/usr/bin/env bash
set -euo pipefail

# Disable Tailscale Serve handlers for this node.

if ! command -v tailscale >/dev/null 2>&1; then
  echo "tailscale not found." >&2
  exit 1
fi

sudo tailscale serve reset

echo "\nTailscale Serve reset. Current status:"
sudo tailscale serve status || true
