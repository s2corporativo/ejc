#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/opt/ejc}"
STATE_DIR="${EJC_OBSERVABILITY_STATE_DIR:-/var/lib/ejc-observability}"
EVIDENCE_DIR="${EJC_RELEASE_EVIDENCE_DIR:-/var/lib/ejc-release-evidence}"
mkdir -p "$STATE_DIR" "$EVIDENCE_DIR"
chmod 700 "$STATE_DIR" "$EVIDENCE_DIR"
SHA="$(cat "$APP_DIR/.deployed_sha")"
REPORT="$EVIDENCE_DIR/${SHA}.json"
python3 "$APP_DIR/scripts/release_evidence.py" --sha "$SHA" --output "$REPORT"
cp -- "$REPORT" "$STATE_DIR/latest.json"
chmod 600 "$STATE_DIR/latest.json" "$REPORT"
