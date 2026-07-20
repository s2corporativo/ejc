#!/usr/bin/env bash
# ── EJC — Ativar e comprovar o backup diário → Google Drive ───────────────────
#
# Idempotente e seguro para produção. Este script:
#   1) preserva o .env antes da primeira alteração;
#   2) garante BACKUP_ENABLED=true, pasta, horário e retenção;
#   3) gera a chave Fernet somente se estiver ausente (nunca troca chave válida);
#   4) RECRIA o container backend para recarregar o env_file;
#   5) comprova o backup de banco + uploads no Drive quando necessário.
#
# Importante: `docker compose restart` NÃO recarrega alterações do env_file.
# Por isso usamos `up -d --force-recreate --no-deps backend`.
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
# Pasta "Backup BD" no Google Drive.
FOLDER_ID="${BACKUP_DRIVE_FOLDER_ID:-1HBh66E4NfZtz3V_Zdln7N_g2iFSoOE9c}"
HORA_UTC="${BACKUP_HORA_UTC:-05:00}"
RETENCAO_DIAS="${BACKUP_RETENCAO_DIAS:-14}"
FORCE_BACKUP_TEST="${FORCE_BACKUP_TEST:-0}"
MAX_AGE_HOURS="${BACKUP_VERIFY_MAX_AGE_HOURS:-20}"

log() { printf '[ativar-backup] %s\n' "$*"; }
die() { printf '[ativar-backup] ERRO: %s\n' "$*" >&2; exit 1; }

[ -f "$ENV_FILE" ] || die "$ENV_FILE não encontrado — rode na raiz do deploy (ex.: cd /opt/ejc)."
command -v docker >/dev/null 2>&1 || die "docker não encontrado."
docker exec "$APP_CONTAINER" true 2>/dev/null || die "container $APP_CONTAINER não está no ar (docker ps)."

if docker compose version >/dev/null 2>&1; then
    DC=(docker compose)
else
    DC=(docker-compose)
fi

get_env_var() {
    local k="$1"
    grep -E "^${k}=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"'\r'
}

ENV_BACKED_UP=0
ENV_BAK=""
CHANGED=0

backup_env_once() {
    if [ "$ENV_BACKED_UP" = "0" ]; then
        ENV_BAK="${ENV_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
        cp "$ENV_FILE" "$ENV_BAK"
        chmod 600 "$ENV_BAK" 2>/dev/null || true
        ENV_BACKED_UP=1
        log "backup do .env → $ENV_BAK"
    fi
}

set_env_var() {
    local k="$1" v="$2" atual
    atual="$(get_env_var "$k")"
    if [ "$atual" = "$v" ]; then
        log "mantido: ${k}"
        return
    fi
    backup_env_once
    if grep -qE "^${k}=" "$ENV_FILE"; then
        sed -i "s|^${k}=.*|${k}=${v}|" "$ENV_FILE"
        log "atualizado: ${k}"
    else
        printf '%s=%s\n' "$k" "$v" >> "$ENV_FILE"
        log "adicionado: ${k}"
    fi
    CHANGED=1
}

# 1) Configuração não sensível.
set_env_var BACKUP_ENABLED "true"
set_env_var BACKUP_DRIVE_FOLDER_ID "$FOLDER_ID"
set_env_var BACKUP_HORA_UTC "$HORA_UTC"
set_env_var BACKUP_RETENCAO_DIAS "$RETENCAO_DIAS"

# 2) Chave Fernet exclusiva do backup — nunca sobrescrever chave existente.
KEY="$(get_env_var BACKUP_ENCRYPTION_KEY)"
if [ -z "$KEY" ] || printf '%s' "$KEY" | grep -qi '^TROCAR'; then
    backup_env_once
    log "gerando BACKUP_ENCRYPTION_KEY estável..."
    KEY="$(docker exec "$APP_CONTAINER" python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
    [ -n "$KEY" ] || die "falha ao gerar a chave Fernet."
    set_env_var BACKUP_ENCRYPTION_KEY "$KEY"
    log "chave gerada e gravada no .env (valor não exibido). Guarde cópia fora do VPS."
else
    log "BACKUP_ENCRYPTION_KEY já existe — mantida (não regenerada)."
fi

chmod 600 "$ENV_FILE" 2>/dev/null || true

# Valida formato sem imprimir o segredo.
if ! printf '%s' "$KEY" | docker exec -i "$APP_CONTAINER" \
    python -c 'import sys; from cryptography.fernet import Fernet; Fernet(sys.stdin.read().strip().encode())' \
    >/dev/null 2>&1; then
    die "BACKUP_ENCRYPTION_KEY inválida; nenhuma alteração automática de chave foi feita."
fi

# 3) Confere se o container realmente recebeu o .env. Reiniciar não basta:
# Docker mantém o ambiente antigo; é obrigatório recriar o container.
CONTAINER_ENABLED="$(docker exec "$APP_CONTAINER" sh -c 'printf %s "${BACKUP_ENABLED:-}"' 2>/dev/null || true)"
CONTAINER_FOLDER="$(docker exec "$APP_CONTAINER" sh -c 'printf %s "${BACKUP_DRIVE_FOLDER_ID:-}"' 2>/dev/null || true)"
CONTAINER_KEY_PRESENT="$(docker exec "$APP_CONTAINER" sh -c 'test -n "${BACKUP_ENCRYPTION_KEY:-}" && printf 1 || printf 0' 2>/dev/null || printf 0)"
RECREATED=0

if [ "$CHANGED" = "1" ] || [ "${CONTAINER_ENABLED,,}" != "true" ] || \
   [ "$CONTAINER_FOLDER" != "$FOLDER_ID" ] || [ "$CONTAINER_KEY_PRESENT" != "1" ]; then
    log "recriando backend para carregar o .env atualizado..."
    "${DC[@]}" up -d --force-recreate --no-deps backend
    RECREATED=1
else
    log "backend já está com a configuração efetiva do backup."
fi

# Espera a aplicação, não apenas o processo do container.
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
[ "$BACKEND_OK" = "1" ] || die "backend não ficou saudável após carregar a configuração do backup."

# 4) Decide se precisa gerar uma nova prova. Configuração nova/recriada sempre
# exige teste. Caso contrário, um sucesso com menos de MAX_AGE_HOURS é suficiente
# para evitar backups extras em cada deploy.
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
    dt = state["last_run_at"]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600
    limite = float(os.getenv("BACKUP_VERIFY_MAX_AGE_HOURS", "20"))
    print("1" if age > limite else "0")
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
    log "há backup comprovado com menos de ${MAX_AGE_HOURS}h; novo teste integral dispensado."
else
    log "executando prova integral: banco + documentos → Google Drive..."
    if ! docker exec -i "$APP_CONTAINER" python - <<'PY'
import asyncio
import json

from app.core.database import AsyncSessionLocal
from app.services.backup_service import executar_backup

async def main() -> int:
    async with AsyncSessionLocal() as db:
        result = await executar_backup(db, origem="ativacao_deploy")

    artefatos = result.get("artefatos") or []
    nomes = [str(a.get("nome") or "") for a in artefatos]
    tem_banco = any(nome.endswith("_db.dump.enc") for nome in nomes)
    tem_uploads = any(nome.endswith("_uploads.tar.gz.enc") for nome in nomes)
    seguro = {
        "ok": result.get("ok"),
        "status": result.get("status"),
        "erro": result.get("erro"),
        "avisos": result.get("avisos") or [],
        "duracao_segundos": result.get("duracao_segundos"),
        "artefatos": [
            {
                "nome": a.get("nome"),
                "bytes_original": a.get("bytes_original"),
                "bytes_cifrado": a.get("bytes_cifrado"),
                "enviado_ao_drive": bool(a.get("drive_file_id")),
            }
            for a in artefatos
        ],
        "banco_presente": tem_banco,
        "uploads_presentes": tem_uploads,
    }
    print(json.dumps(seguro, ensure_ascii=False))

    # Exigência do EJC: sucesso integral, com banco e documentos. Status parcial
    # não é aceito como prova de ativação.
    return 0 if result.get("status") == "sucesso" and tem_banco and tem_uploads else 2

raise SystemExit(asyncio.run(main()))
PY
    then
        docker logs --tail 100 "$APP_CONTAINER" 2>&1 | grep -i -E 'backup|drive' || true
        die "a prova integral do backup falhou; confira credenciais/permissão de escrita da pasta e os logs acima."
    fi
    log "prova integral concluída: banco e uploads cifrados enviados ao Drive."
fi

cat <<EOF

[ativar-backup] Backup diário ATIVO.
  • Agenda: ${HORA_UTC} UTC (02:00 em Brasília quando UTC−3).
  • Destino: pasta "Backup BD" ($FOLDER_ID).
  • Retenção: ${RETENCAO_DIAS} dias.
  • Artefatos esperados: *_db.dump.enc e *_uploads.tar.gz.enc.
  • Status oficial: GET /admin/backup/status (admin/superadmin).
  • Diagnóstico: bash scripts/backup/diagnostico_backup.sh
EOF
