#!/usr/bin/env bash
# ── EJC — Ativar o backup diário → Google Drive (idempotente) ─────────────────
#
# Faz TUDO de uma vez, no VPS (na raiz do deploy, ex.: /opt/ejc):
#   1) faz backup do .env atual (.env.bak.<timestamp>);
#   2) garante BACKUP_ENABLED=true e BACKUP_DRIVE_FOLDER_ID no .env;
#   3) gera a BACKUP_ENCRYPTION_KEY se ainda não existir (mantém a atual se já há —
#      trocar a chave inutiliza backups anteriores);
#   4) reinicia o backend para o agendador pegar a config;
#   5) dispara um backup de teste e mostra o resultado nos logs.
#
# Uso:   cd /opt/ejc && bash scripts/backup/ativar_backup.sh
# Rode UMA vez. Depois disso o backup roda sozinho todo dia (BACKUP_HORA_UTC).
# Ver RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md e scripts/backup/diagnostico_backup.sh
set -euo pipefail

APP_CONTAINER="${APP_CONTAINER:-ejc_backend}"
ENV_FILE="${ENV_FILE:-.env}"
# Pasta "Backup BD" verificada no Drive (dona: service account ejc-drive).
FOLDER_ID="${BACKUP_DRIVE_FOLDER_ID:-1HBh66E4NfZtz3V_Zdln7N_g2iFSoOE9c}"

log() { printf '[ativar-backup] %s\n' "$*"; }
die() { printf '[ativar-backup] ERRO: %s\n' "$*" >&2; exit 1; }

[ -f "$ENV_FILE" ] || die "$ENV_FILE não encontrado — rode na raiz do deploy (ex.: cd /opt/ejc)."
command -v docker >/dev/null 2>&1 || die "docker não encontrado."
docker exec "$APP_CONTAINER" true 2>/dev/null || die "container $APP_CONTAINER não está no ar (docker ps)."

# docker compose (v2) ou docker-compose (v1)
if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi

# Escreve/atualiza uma variável no .env sem duplicar (| como delimitador: chaves
# Fernet usam - _ = mas nunca |).
set_env_var() {
    local k="$1" v="$2"
    if grep -qE "^${k}=" "$ENV_FILE"; then
        sed -i "s|^${k}=.*|${k}=${v}|" "$ENV_FILE"
        log "atualizado: ${k}"
    else
        printf '%s=%s\n' "$k" "$v" >> "$ENV_FILE"
        log "adicionado: ${k}"
    fi
}

# 1) Backup do .env
BAK=".env.bak.$(date +%Y%m%d_%H%M%S)"
cp "$ENV_FILE" "$BAK"
log "backup do .env → $BAK"

# 2) Flags
set_env_var BACKUP_ENABLED "true"
set_env_var BACKUP_DRIVE_FOLDER_ID "$FOLDER_ID"

# 3) Chave Fernet — só gera se ainda não houver (não sobrescreve a existente)
if grep -qE '^BACKUP_ENCRYPTION_KEY=.+' "$ENV_FILE"; then
    log "BACKUP_ENCRYPTION_KEY já existe — mantida (não regenerada)."
else
    log "gerando BACKUP_ENCRYPTION_KEY..."
    KEY="$(docker exec "$APP_CONTAINER" python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
    [ -n "$KEY" ] || die "falha ao gerar a chave Fernet."
    set_env_var BACKUP_ENCRYPTION_KEY "$KEY"
    log "chave gerada. GUARDE-A fora do VPS (ver com: grep '^BACKUP_ENCRYPTION_KEY=' $ENV_FILE)."
fi

# 4) Reiniciar o backend e esperar subir
log "reiniciando o backend ($DC restart backend)..."
$DC restart backend
log "aguardando o backend responder..."
for _ in $(seq 1 30); do
    docker exec "$APP_CONTAINER" true 2>/dev/null && break
    sleep 2
done
sleep 3  # margem para o app terminar de importar

# 5) Disparar backup de teste (mesma rotina do agendamento diário)
log "disparando backup de teste (pode levar de segundos a minutos)..."
docker exec "$APP_CONTAINER" python -c "import asyncio; from app.services import backup_service; asyncio.run(backup_service.executar_backup_background(origem='manual'))" \
    || log "AVISO: o disparo retornou erro — veja os logs abaixo."

log "─── últimos logs de backup ───"
docker logs --tail 60 "$APP_CONTAINER" 2>&1 | grep -i -E 'backup|drive' || log "(sem linhas de backup nos logs — verifique docker logs $APP_CONTAINER)"

cat <<EOF

[ativar-backup] Concluído.
  • Confira a pasta "Backup BD" no Google Drive: deve aparecer
    ejc_backup_<hoje>_db.enc e ejc_backup_<hoje>_uploads.enc.
  • Status oficial: GET /admin/backup/status (logado como admin).
  • Diagnóstico a qualquer momento: bash scripts/backup/diagnostico_backup.sh
  • Se algo falhou, o .env anterior está salvo em: $BAK
EOF
