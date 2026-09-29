#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/opt/ejc}"
STATE_DIR="${EJC_OBSERVABILITY_STATE_DIR:-/var/lib/ejc-observability}"
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"
SHA="$(cat "$APP_DIR/.deployed_sha")"
python3 "$APP_DIR/scripts/release_evidence.py" --sha "$SHA" --output "$STATE_DIR/latest.json"
