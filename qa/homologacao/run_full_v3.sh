#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
REPORT_DIR="$ROOT/qa/homologacao/reports"
BROWSER_DIR="$ROOT/frontend/tests/__out__/homologacao-live"
mkdir -p "$REPORT_DIR" "$BROWSER_DIR"

readarray -t VALUES < <(python3 - <<'PY'
import base64, os, secrets
run = os.environ.get('GITHUB_RUN_ID', secrets.token_hex(6))
def password(): return 'Qa!' + secrets.token_urlsafe(22) + '9'
def totp(): return base64.b32encode(os.urandom(20)).decode().rstrip('=')
print(f'homolog.qa.{run}@depaulateixeira.adv.br')
print(password())
print(totp())
print(f'homolog.portal.{run}@depaulateixeira.adv.br')
print(password())
print(totp())
PY
)
export EJC_TEST_EMAIL="${VALUES[0]}"
export EJC_QA_EMAIL="$EJC_TEST_EMAIL"
export EJC_TEST_PASSWORD="${VALUES[1]}"
export EJC_QA_PASSWORD="$EJC_TEST_PASSWORD"
export EJC_TEST_TOTP_SECRET="${VALUES[2]}"
export EJC_QA_TOTP_SECRET="$EJC_TEST_TOTP_SECRET"
export EJC_PORTAL_EMAIL="${VALUES[3]}"
export EJC_PORTAL_PASSWORD="${VALUES[4]}"
export EJC_PORTAL_TOTP_SECRET="${VALUES[5]}"
export EJC_QA_PORTAL_MARKER="HOMOLOG-FICTICIO-PORTAL-${GITHUB_RUN_ID:-local}"
export EJC_BASE_URL="http://127.0.0.1:8000"
export EJC_FRONTEND_URL="http://127.0.0.1:8080"
export EJC_ALLOW_PRODUCTION_E2E="true"
export EJC_HAS_AI="true"
export EJC_QA_OUT="qa/homologacao/reports"
export SCREENSHOT_DIR="frontend/tests/__out__/homologacao-live"
export EJC_QA_BROWSER_REPORT="frontend/tests/__out__/homologacao-live/browser_homologacao_report.json"
export EJC_AI_REPORT="qa/homologacao/reports/ia_peca_protocolavel_report.json"
for secret in "$EJC_TEST_PASSWORD" "$EJC_TEST_TOTP_SECRET" "$EJC_PORTAL_PASSWORD" "$EJC_PORTAL_TOTP_SECRET"; do
  echo "::add-mask::$secret"
done

cleanup() {
  set +e
  MARKERS=$(python3 - <<'PY'
import json, os
from pathlib import Path
marks=[os.getenv('EJC_QA_PORTAL_MARKER','')]
for path, key in [
    (Path('qa/homologacao/reports/homologacao_report.json'), 'run_marker'),
    (Path('qa/homologacao/reports/ia_peca_protocolavel_report.json'), 'marker'),
]:
    try:
        value=json.loads(path.read_text(encoding='utf-8')).get(key)
        if value: marks.append(value)
    except Exception: pass
print(','.join(x for x in marks if x))
PY
)
  docker cp qa/homologacao/cleanup_prod_qa_data.py ejc_backend:/tmp/cleanup_prod_qa_data.py >/dev/null 2>&1
  if [[ -n "$MARKERS" ]]; then
    docker exec -e EJC_QA_MARKERS="$MARKERS" ejc_backend python /tmp/cleanup_prod_qa_data.py || true
  fi
  docker exec \
    -e EJC_QA_EMAIL="$EJC_QA_EMAIL" \
    -e EJC_PORTAL_EMAIL="$EJC_PORTAL_EMAIL" \
    ejc_backend python /tmp/temp_prod_qa_user.py desativar || true
}
trap cleanup EXIT

# Prova do ambiente publicado.
docker inspect -f '{{.State.Health.Status}}' ejc_backend
ndocker_status=$(docker inspect -f '{{.State.Status}}' ejc_frontend)
echo "frontend=$ndocker_status"
curl -fsS --max-time 15 "$EJC_BASE_URL/api/health" | tee "$REPORT_DIR/health_producao.json"
curl -fsSI --max-time 15 "$EJC_FRONTEND_URL/login" | tee "$REPORT_DIR/frontend_headers.txt"

# Usuários temporários staff + Portal.
docker cp qa/homologacao/temp_prod_qa_user.py ejc_backend:/tmp/temp_prod_qa_user.py
docker exec \
  -e EJC_QA_EMAIL="$EJC_QA_EMAIL" \
  -e EJC_QA_PASSWORD="$EJC_QA_PASSWORD" \
  -e EJC_QA_TOTP_SECRET="$EJC_QA_TOTP_SECRET" \
  -e EJC_PORTAL_EMAIL="$EJC_PORTAL_EMAIL" \
  -e EJC_PORTAL_PASSWORD="$EJC_PORTAL_PASSWORD" \
  -e EJC_PORTAL_TOTP_SECRET="$EJC_PORTAL_TOTP_SECRET" \
  -e EJC_QA_PORTAL_MARKER="$EJC_QA_PORTAL_MARKER" \
  ejc_backend python /tmp/temp_prod_qa_user.py criar

VENV="/tmp/ejc-qa-${GITHUB_RUN_ID:-local}"
python3 -m venv "$VENV"
source "$VENV/bin/activate"
pip install --disable-pip-version-check -q httpx==0.27.2 pyotp==2.9.0

set +e
python qa/homologacao/run_homologacao_totp.py 2>&1 | tee "$REPORT_DIR/homologacao_console.txt"
API_EXIT=${PIPESTATUS[0]}
python qa/homologacao/run_ia_peca_protocolavel_v2.py 2>&1 | tee "$REPORT_DIR/ia_peca_console.txt"
AI_EXIT=${PIPESTATUS[0]}
set -e

cd "$ROOT/frontend"
npm ci
npm install --no-save --package-lock=false playwright@1.56.1
npx playwright install --with-deps chromium
set +e
node tests/homologacao-completa-live-v2.mjs 2>&1 | tee "$REPORT_DIR/browser_console.txt"
BROWSER_EXIT=${PIPESTATUS[0]}
set -e
cd "$ROOT"

python3 - <<'PY'
import json
from pathlib import Path
paths = {
    'api': Path('qa/homologacao/reports/homologacao_report.json'),
    'ia': Path('qa/homologacao/reports/ia_peca_protocolavel_report.json'),
    'browser': Path('frontend/tests/__out__/homologacao-live/browser_homologacao_report.json'),
    'health': Path('qa/homologacao/reports/health_producao.json'),
}
out={'arquivos':{}, 'conclusao':'EXECUTADA'}
for name, path in paths.items():
    if path.exists():
        try: out['arquivos'][name]=json.loads(path.read_text(encoding='utf-8'))
        except Exception: out['arquivos'][name]={'texto':path.read_text(encoding='utf-8',errors='replace')[:3000]}
    else:
        out['arquivos'][name]={'ausente':True,'path':str(path)}
        out['conclusao']='INCOMPLETA'
Path('qa/homologacao/reports/homologacao_completa_consolidada.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
PY

python3 - "$API_EXIT" "$AI_EXIT" "$BROWSER_EXIT" <<'PY'
import json, sys
from pathlib import Path
api_exit, ai_exit, browser_exit=map(int,sys.argv[1:])
failures=[]
for code,name in [(api_exit,'executor H01-H15'),(ai_exit,'executor IA'),(browser_exit,'executor navegador')]:
    if code: failures.append(f'{name}: exit {code}')
api=Path('qa/homologacao/reports/homologacao_report.json')
ia=Path('qa/homologacao/reports/ia_peca_protocolavel_report.json')
browser=Path('frontend/tests/__out__/homologacao-live/browser_homologacao_report.json')
if api.exists():
    r=json.loads(api.read_text())
    if r.get('resumo',{}).get('FALHA',0): failures.append(f"H01-H15: {r['resumo']['FALHA']} cenário(s) com falha")
else: failures.append('relatório H01-H15 ausente')
if ia.exists():
    r=json.loads(ia.read_text())
    if r.get('resultado')!='PRONTA_PARA_REVISAO_E_PROTOCOLO': failures.append(f"IA: {r.get('resultado')}")
else: failures.append('relatório IA ausente')
if browser.exists():
    r=json.loads(browser.read_text()); s=r.get('summary',{})
    if s.get('routes_broken',0): failures.append(f"UI: {s['routes_broken']} rota(s) quebrada(s)")
    if s.get('page_errors',0): failures.append(f"UI: {s['page_errors']} erro(s) JS")
    if s.get('responsive_failures',0): failures.append(f"UI: {s['responsive_failures']} falha(s) responsivas")
    if s.get('accessibility_issues',0): failures.append(f"UI: {s['accessibility_issues']} falha(s) de acessibilidade")
else: failures.append('relatório navegador ausente')
if failures:
    print('HOMOLOGAÇÃO REPROVADA/COM RESSALVAS:')
    for item in failures: print(' -',item)
    raise SystemExit(1)
print('HOMOLOGAÇÃO APROVADA nos gates automatizados.')
PY
