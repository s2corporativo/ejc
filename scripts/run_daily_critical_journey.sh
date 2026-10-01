#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
ENV_FILE="${EJC_CRITICAL_JOURNEY_ENV:-/etc/ejc/critical-journey.env}"
REPORT_DIR="${EJC_MAINT_REPORT_DIR:-/var/lib/ejc-maintenance}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT="$REPORT_DIR/critical-journey-$STAMP.json"
LATEST="$REPORT_DIR/critical-journey-latest.json"
mkdir -p "$REPORT_DIR"

if [ ! -f "$ENV_FILE" ]; then
  printf '{"status":"skipped","reason":"dedicated_credentials_missing","generated_at":"%s"}\n' "$(date -u +%FT%TZ)" > "$REPORT"
  chmod 600 "$REPORT"
  cp -f "$REPORT" "$LATEST"
  chmod 600 "$LATEST"
  echo "critical journey: SKIPPED — dedicated credential file absent"
  exit 0
fi

# shellcheck disable=SC1090
set -a
. "$ENV_FILE"
set +a

: "${EJC_TEST_EMAIL:?EJC_TEST_EMAIL ausente em $ENV_FILE}"
: "${EJC_TEST_PASSWORD:?EJC_TEST_PASSWORD ausente em $ENV_FILE}"

export EJC_BASE_URL="${EJC_BASE_URL:-https://ejc.depaulateixeira.adv.br}"
export EJC_ALLOW_PRODUCTION_E2E=true
export EJC_E2E_CLEANUP=true
export EJC_E2E_STRICT=true
export EJC_CASE_CREATION_MODE=manual
SOURCE_REPORT="$APP_DIR/qa/e2e/reports/e2e_fictitious_report.json"
rm -f -- "$SOURCE_REPORT"

cd "$APP_DIR/qa/e2e"
python3 run_case_journey.py
test -s "$SOURCE_REPORT"
cp -f "$SOURCE_REPORT" "$REPORT"
cp -f "$REPORT" "$LATEST"
chmod 600 "$REPORT" "$LATEST"
echo "critical journey: OK — $REPORT"
