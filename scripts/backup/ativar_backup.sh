#!/usr/bin/env bash
# ── EJC — Ativar e comprovar o backup diário → Google Drive ───────────────────
#
# Idempotente e seguro para produção. Não cria chave criptográfica nem credencial:
# esses segredos precisam existir previamente no .env e ter cópia/custódia fora da
# VPS. O script altera somente parâmetros operacionais não sensíveis, recria o
# backend quando necessário e exige prova integral com identidade dedicada.
#
# Uso:
#   cd /opt/ejc && bash scripts/backup/ativar_backup.sh
#
# Opcionais:
#   FORCE_BACKUP_TEST=1             força novo backup mesmo com sucesso recente
#   BACKUP_VERIFY_MAX_AGE_HOURS=20  idade máxima para reutilizar prova recente
set -euo pipefail

APP_CONTAINER="${APP_CONTAINER:-ejc_backend}"
ENV_FILE="${ENV_FILE:-.env}"
FORCE_BACKUP_TEST="${FORCE_BACKUP_TEST:-0}"
MAX_AGE_HOURS="${BACKUP_VERIFY_MAX_AGE_HOURS:-20}"

log() { printf '[ativar-backup] %s\n' "$*"; }
die() { printf '[ativar-backup] ERRO: %s\n' "$*" >&2; exit 1; }

[ -f "$ENV_FILE" ] || die "$ENV_FILE não encontrado — rode na raiz do deploy."
command -v docker >/dev/null 2>&1 || die "docker não encontrado."
docker exec "$APP_CONTAINER" true 2>/dev/null || \
  die "container $APP_CONTAINER não está no ar."

if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
else
  DC=(docker-compose)
fi

get_env_var() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null \
    | tail -1 | cut -d= -f2- | tr -d '"'"'"'\r' || true
}

value_present() {
  local value
  value="$(get_env_var "$1")"
  [ -n "$value" ] && ! printf '%s' "$value" | grep -qi '^TROCAR'
}

FOLDER_ID="${BACKUP_DRIVE_FOLDER_ID:-$(get_env_var BACKUP_DRIVE_FOLDER_ID)}"
[ -n "$FOLDER_ID" ] || die \
  "BACKUP_DRIVE_FOLDER_ID ausente. Configure a pasta autorizada no .env."

HORA_UTC="${BACKUP_HORA_UTC:-$(get_env_var BACKUP_HORA_UTC)}"
HORA_UTC="${HORA_UTC:-05:00}"
RETENCAO_DIAS="${BACKUP_RETENCAO_DIAS:-$(get_env_var BACKUP_RETENCAO_DIAS)}"
RETENCAO_DIAS="${RETENCAO_DIAS:-14}"

AUTH_MODE="${BACKUP_GOOGLE_DRIVE_AUTH_MODE:-$(get_env_var BACKUP_GOOGLE_DRIVE_AUTH_MODE)}"
AUTH_MODE="${AUTH_MODE:-auto}"
AUTH_MODE="${AUTH_MODE,,}"
case "$AUTH_MODE" in
  auto|oauth|service_account) ;;
  inherit) die "BACKUP_GOOGLE_DRIVE_AUTH_MODE=inherit é proibido para o backup." ;;
  *) die "BACKUP_GOOGLE_DRIVE_AUTH_MODE inválido: use auto, oauth ou service_account." ;;
esac

SA_READY=0
OAUTH_READY=0
if value_present BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE || \
   value_present BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON; then
  SA_READY=1
fi
if value_present BACKUP_GOOGLE_DRIVE_OAUTH_USER_FILE || \
   value_present BACKUP_GOOGLE_DRIVE_OAUTH_USER_JSON; then
  OAUTH_READY=1
elif value_present BACKUP_GOOGLE_DRIVE_OAUTH_CLIENT_ID && \
     value_present BACKUP_GOOGLE_DRIVE_OAUTH_CLIENT_SECRET && \
     value_present BACKUP_GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN; then
  OAUTH_READY=1
fi

case "$AUTH_MODE" in
  service_account)
    [ "$SA_READY" = "1" ] || die "credencial service account exclusiva ausente."
    ;;
  oauth)
    [ "$OAUTH_READY" = "1" ] || die "credencial OAuth exclusiva ausente ou incompleta."
    ;;
  auto)
    [ "$SA_READY" = "1" ] || [ "$OAUTH_READY" = "1" ] || \
      die "nenhuma credencial exclusiva BACKUP_GOOGLE_DRIVE_* foi configurada."
    ;;
esac

KEY="$(get_env_var BACKUP_ENCRYPTION_KEY)"
if [ -z "$KEY" ] || printf '%s' "$KEY" | grep -qi '^TROCAR'; then
  die "BACKUP_ENCRYPTION_KEY ausente. Gere uma chave Fernet, guarde cópia fora da VPS e somente então configure o .env."
fi

if ! printf '%s' "$KEY" | docker exec -i "$APP_CONTAINER" \
  python -c 'import sys; from cryptography.fernet import Fernet; Fernet(sys.stdin.read().strip().encode())' \
  >/dev/null 2>&1; then
  die "BACKUP_ENCRYPTION_KEY inválida; nenhuma troca automática foi realizada."
fi

ENV_BACKED_UP=0
ENV_BAK=""
CHANGED=0

backup_env_once() {
  if [ "$ENV_BACKED_UP" = "0" ]; then
    ENV_BAK="${ENV_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
    cp "$ENV_FILE" "$ENV_BAK"
    chmod 600 "$ENV_BAK" 2>/dev/null || true
    ENV_BACKED_UP=1
    log "cópia transitória do .env criada para rollback local."
  fi
}

set_env_var() {
  local key="$1" value="$2" current
  current="$(get_env_var "$key")"
  if [ "$current" = "$value" ]; then
    log "mantido: ${key}"
    return
  fi
  backup_env_once
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
  log "atualizado: ${key}"
  CHANGED=1
}

# Somente parâmetros não sensíveis são ajustados automaticamente.
set_env_var BACKUP_ENABLED "true"
set_env_var BACKUP_DRIVE_FOLDER_ID "$FOLDER_ID"
set_env_var BACKUP_HORA_UTC "$HORA_UTC"
set_env_var BACKUP_RETENCAO_DIAS "$RETENCAO_DIAS"
chmod 600 "$ENV_FILE" 2>/dev/null || true

CONTAINER_ENABLED="$(docker exec "$APP_CONTAINER" sh -c 'printf %s "${BACKUP_ENABLED:-}"' 2>/dev/null || true)"
CONTAINER_FOLDER="$(docker exec "$APP_CONTAINER" sh -c 'printf %s "${BACKUP_DRIVE_FOLDER_ID:-}"' 2>/dev/null || true)"
CONTAINER_KEY_PRESENT="$(docker exec "$APP_CONTAINER" sh -c 'test -n "${BACKUP_ENCRYPTION_KEY:-}" && printf 1 || printf 0' 2>/dev/null || printf 0)"
CONTAINER_DEDICATED="$(docker exec "$APP_CONTAINER" python - <<'PY' 2>/dev/null || true
from app.services.backup_drive_auth import auth_status
status = auth_status()
print("1" if status.get("credencial_dedicada_configurada") and status.get("auth_mode") != "inherit" else "0")
PY
)"
RECREATED=0

if [ "$CHANGED" = "1" ] || [ "${CONTAINER_ENABLED,,}" != "true" ] || \
   [ "$CONTAINER_FOLDER" != "$FOLDER_ID" ] || [ "$CONTAINER_KEY_PRESENT" != "1" ] || \
   [ "$CONTAINER_DEDICATED" != "1" ]; then
  log "recriando backend para carregar a configuração efetiva..."
  "${DC[@]}" up -d --force-recreate --no-deps backend
  RECREATED=1
else
  log "backend já está com a configuração efetiva do backup."
fi

log "aguardando health-check do backend..."
BACKEND_OK=0
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 || \
     docker exec "$APP_CONTAINER" curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    BACKEND_OK=1
    break
  fi
  sleep 2
done
[ "$BACKEND_OK" = "1" ] || die "backend não ficou saudável após carregar a configuração."

# Validação efetiva no processo recém-carregado, sem expor valores.
docker exec -i "$APP_CONTAINER" python - <<'PY'
import json
from app.services.backup_service import configuracao_status

status = configuracao_status()
required = (
    "enabled",
    "chave_configurada",
    "pasta_configurada",
    "credencial_drive_configurada",
    "credencial_dedicada_configurada",
    "pg_dump_disponivel",
)
problems = [field for field in required if not bool(status.get(field))]
if status.get("auth_mode") == "inherit":
    problems.append("auth_mode_inherit")
print(json.dumps({
    "ok": not problems,
    "auth_mode": status.get("auth_mode"),
    "credencial_dedicada": bool(status.get("credencial_dedicada_configurada")),
    "problemas": problems,
}, ensure_ascii=False, sort_keys=True))
raise SystemExit(0 if not problems else 1)
PY

NEED_TEST=0
if [ "$FORCE_BACKUP_TEST" = "1" ] || [ "$CHANGED" = "1" ] || [ "$RECREATED" = "1" ]; then
  NEED_TEST=1
else
  if STATE_NEEDS_TEST="$(docker exec -e BACKUP_VERIFY_MAX_AGE_HOURS="$MAX_AGE_HOURS" -i "$APP_CONTAINER" python - <<'PY'
import asyncio
import os
from datetime import datetime, timezone

from app.core.database import AsyncSessionLocal
from app.services.backup_service import obter_estado

async def main() -> int:
    try:
        async with AsyncSessionLocal() as db:
            state = await obter_estado(db)
    except Exception:
        print("1")
        return 0
    if not state or state.get("last_status") != "sucesso" or not state.get("last_run_at"):
        print("1")
        return 0
    details = state.get("detalhes") or []
    names = [str(item.get("nome") or "") for item in details if isinstance(item, dict)]
    if not any(name.endswith("_db.dump.enc") for name in names) or not any(
        name.endswith("_uploads.tar.gz.enc") for name in names
    ):
        print("1")
        return 0
    dt = state["last_run_at"]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600
    limit = float(os.getenv("BACKUP_VERIFY_MAX_AGE_HOURS", "20"))
    print("1" if age > limit else "0")
    return 0

raise SystemExit(asyncio.run(main()))
PY
)"; then
    [ "$STATE_NEEDS_TEST" = "1" ] && NEED_TEST=1
  else
    NEED_TEST=1
  fi
fi

if [ "$NEED_TEST" = "0" ]; then
  log "há prova integral com menos de ${MAX_AGE_HOURS}h; novo backup dispensado."
else
  log "executando prova integral com identidade dedicada..."
  if ! docker exec -i "$APP_CONTAINER" python - <<'PY'
import asyncio
import json

from app.core.database import AsyncSessionLocal
from app.services import backup_service

async def main() -> int:
    config = backup_service.configuracao_status()
    if not config.get("credencial_dedicada_configurada") or config.get("auth_mode") == "inherit":
        print(json.dumps({"ok": False, "status": "credencial_nao_dedicada"}))
        return 2
    async with AsyncSessionLocal() as db:
        result = await backup_service.executar_backup(db, origem="ativacao_deploy")
    artifacts = result.get("artefatos") or []
    names = [str(item.get("nome") or "") for item in artifacts]
    has_db = any(name.endswith("_db.dump.enc") for name in names)
    has_uploads = any(name.endswith("_uploads.tar.gz.enc") for name in names)
    complete = result.get("status") == "sucesso" and has_db and has_uploads
    print(json.dumps({
        "ok": complete,
        "status": result.get("status"),
        "auth_mode": config.get("auth_mode"),
        "credencial_dedicada": True,
        "artefatos": [
            {
                "nome": item.get("nome"),
                "bytes_original": item.get("bytes_original"),
                "bytes_cifrado": item.get("bytes_cifrado"),
            }
            for item in artifacts
        ],
        "banco_presente": has_db,
        "uploads_presentes": has_uploads,
    }, ensure_ascii=False, sort_keys=True))
    return 0 if complete else 2

raise SystemExit(asyncio.run(main()))
PY
  then
    die "a prova integral falhou; investigue localmente os logs do serviço de backup."
  fi
  log "prova integral concluída: banco e uploads cifrados enviados com identidade dedicada."
fi

# A cópia transitória só permanece se o script falhar antes deste ponto.
if [ "$ENV_BACKED_UP" = "1" ] && [ -n "$ENV_BAK" ]; then
  rm -f "$ENV_BAK"
  log "cópia transitória do .env removida após sucesso."
fi

cat <<EOF

[ativar-backup] Backup diário ATIVO.
  • Agenda: ${HORA_UTC} UTC.
  • Destino: BACKUP_DRIVE_FOLDER_ID configurado (valor omitido).
  • Retenção: ${RETENCAO_DIAS} dias.
  • Identidade: credencial exclusiva BACKUP_GOOGLE_DRIVE_*.
  • Artefatos obrigatórios: *_db.dump.enc e *_uploads.tar.gz.enc.
  • Status oficial: GET /admin/backup/status (admin/superadmin).
EOF
