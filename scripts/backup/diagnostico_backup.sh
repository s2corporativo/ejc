#!/usr/bin/env bash
# ── EJC — Diagnóstico do backup diário → Google Drive ─────────────────────────
#
# SOMENTE LEITURA. Roda no VPS (na raiz do deploy, ex.: /opt/ejc) e aponta por
# que a pasta do Drive pode estar vazia. NUNCA imprime segredos (chave/senha):
# só reporta "definida/ausente" e valores não-sensíveis (flags, ID de pasta).
#
# Uso:   bash scripts/backup/diagnostico_backup.sh
# Sai com código != 0 se encontrar problema que impeça o backup.
#
# Contexto: o backup nativo (backend/app/services/backup_service.py) só roda no
# agendamento se BACKUP_ENABLED=true; qualquer disparo exige BACKUP_ENCRYPTION_KEY
# (LGPD) + BACKUP_DRIVE_FOLDER_ID. Detalhes: RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md
set -uo pipefail   # sem -e de propósito: queremos rodar TODAS as checagens

DB_CONTAINER="${DB_CONTAINER:-ejc_db}"
APP_CONTAINER="${APP_CONTAINER:-ejc_backend}"
ENV_FILE="${ENV_FILE:-.env}"
# ID da pasta "Backup BD" verificada no Drive (dona: service account ejc-drive).
PASTA_ESPERADA="${PASTA_ESPERADA:-1HBh66E4NfZtz3V_Zdln7N_g2iFSoOE9c}"

PROBLEMAS=0
OK=0
APP_UP=0

sec()  { printf '\n=== %s ===\n' "$*"; }
info() { printf '  %s\n' "$*"; }
ok()   { printf '  [ OK ]  %s\n' "$*"; OK=$((OK + 1)); }
warn() { printf '  [AVISO] %s\n' "$*"; }
bad()  { printf '  [FALHA] %s\n' "$*"; PROBLEMAS=$((PROBLEMAS + 1)); }

# Lê UMA variável do .env sem "source" cru (evita executar o arquivo inteiro).
getenv() { # $1=nome
    [ -f "$ENV_FILE" ] || { printf ''; return; }
    grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"'"'"'\r'
}

printf 'EJC — Diagnóstico do backup diário → Google Drive\n'

# ── 1. .env ───────────────────────────────────────────────────────────────────
sec "1. Arquivo de configuração"
if [ -f "$ENV_FILE" ]; then
    ok "$ENV_FILE encontrado"
else
    bad "$ENV_FILE não encontrado — rode este script na raiz do deploy (ex.: cd /opt/ejc)"
fi

# ── 2. Variáveis do backup (segredos nunca impressos) ─────────────────────────
sec "2. Configuração do backup (.env)"
BACKUP_ENABLED_V="$(getenv BACKUP_ENABLED)"
case "$(printf '%s' "$BACKUP_ENABLED_V" | tr '[:upper:]' '[:lower:]')" in
    true | 1 | yes) ok "BACKUP_ENABLED=$BACKUP_ENABLED_V (agendamento diário LIGADO)" ;;
    "")             bad "BACKUP_ENABLED ausente → default é FALSE → o backup NUNCA roda. Defina BACKUP_ENABLED=true" ;;
    *)              bad "BACKUP_ENABLED=$BACKUP_ENABLED_V (DESLIGADO) → o backup não roda. Defina BACKUP_ENABLED=true" ;;
esac

KEY_V="$(getenv BACKUP_ENCRYPTION_KEY)"
if [ -z "$KEY_V" ] || printf '%s' "$KEY_V" | grep -qi '^trocar'; then
    bad "BACKUP_ENCRYPTION_KEY ausente/placeholder → o backup não sai do VPS (LGPD)"
else
    ok "BACKUP_ENCRYPTION_KEY definida (${#KEY_V} chars) — valor não exibido"
fi

FOLDER_V="$(getenv BACKUP_DRIVE_FOLDER_ID)"
if [ -z "$FOLDER_V" ]; then
    bad "BACKUP_DRIVE_FOLDER_ID vazio → o upload não tem pasta de destino"
elif [ "$FOLDER_V" = "$PASTA_ESPERADA" ]; then
    ok "BACKUP_DRIVE_FOLDER_ID=$FOLDER_V (bate com a pasta 'Backup BD' do Drive)"
else
    warn "BACKUP_DRIVE_FOLDER_ID=$FOLDER_V — confirme se é a pasta certa (a 'Backup BD' verificada é $PASTA_ESPERADA)"
fi

info "BACKUP_HORA_UTC=$(getenv BACKUP_HORA_UTC) (vazio = default 05:00)"
info "BACKUP_RETENCAO_DIAS=$(getenv BACKUP_RETENCAO_DIAS) (vazio = default 14)"

# ── 3. Containers ─────────────────────────────────────────────────────────────
sec "3. Containers Docker"
if command -v docker >/dev/null 2>&1; then
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$APP_CONTAINER"; then
        ok "container $APP_CONTAINER no ar"
        APP_UP=1
    else
        bad "container $APP_CONTAINER não está no ar → scheduler não roda o backup"
    fi
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$DB_CONTAINER"; then
        ok "container $DB_CONTAINER no ar"
    else
        bad "container $DB_CONTAINER não está no ar → pg_dump não tem banco"
    fi
else
    warn "docker não encontrado — pulando checagens de container/pg_dump/uploads"
fi

# ── 4. pg_dump no container do backend ────────────────────────────────────────
sec "4. Binário pg_dump (no $APP_CONTAINER)"
if [ "$APP_UP" = 1 ]; then
    if docker exec "$APP_CONTAINER" sh -c 'command -v pg_dump' >/dev/null 2>&1; then
        ok "pg_dump presente"
    else
        bad "pg_dump AUSENTE no $APP_CONTAINER — instale postgresql-client na imagem do backend"
    fi
else
    info "pulado (container do backend indisponível)"
fi

# ── 5. Uploads / documentos gerados ───────────────────────────────────────────
sec "5. Documentos gerados (UPLOAD_DIR)"
UPDIR="$(getenv UPLOAD_DIR)"
UPDIR="${UPDIR:-/app/uploads}"
if [ "$APP_UP" = 1 ]; then
    if docker exec "$APP_CONTAINER" sh -c "test -d '$UPDIR'" 2>/dev/null; then
        N="$(docker exec "$APP_CONTAINER" sh -c "find '$UPDIR' -type f 2>/dev/null | wc -l" | tr -d ' ')"
        SZ="$(docker exec "$APP_CONTAINER" sh -c "du -sh '$UPDIR' 2>/dev/null | cut -f1")"
        ok "UPLOAD_DIR=$UPDIR ($N arquivos, ${SZ:-?}) — entra no backup de uploads"
    else
        warn "UPLOAD_DIR=$UPDIR não existe no $APP_CONTAINER"
    fi
else
    info "pulado (container do backend indisponível)"
fi

# ── 6. Validade da chave Fernet (sem expor o valor) ───────────────────────────
sec "6. Chave de criptografia"
if [ -n "$KEY_V" ] && [ "$APP_UP" = 1 ]; then
    # chave via STDIN — nunca no argv (não aparece em `ps`).
    if printf '%s' "$KEY_V" | docker exec -i "$APP_CONTAINER" \
        python -c 'import sys;from cryptography.fernet import Fernet;Fernet(sys.stdin.read().strip().encode())' >/dev/null 2>&1; then
        ok "BACKUP_ENCRYPTION_KEY é uma chave Fernet válida"
    else
        bad "BACKUP_ENCRYPTION_KEY inválida (precisa ser chave Fernet: 32 bytes url-safe base64)"
    fi
else
    info "pulado (sem chave definida ou container indisponível)"
fi

# ── 7. Status oficial (autenticado) — como ver ────────────────────────────────
sec "7. Status oficial do backup"
info "O veredito completo está em GET /admin/backup/status (requer login admin):"
info "  - configuracao.{enabled,chave_configurada,pasta_configurada,pg_dump_disponivel}"
info "  - ultimo_resultado  → vazio = nunca rodou; com erro = rodou e falhou"
info "  - proximo_agendamento"
info "Pela API (troque HOST e o token de um admin):"
info "  curl -s -H 'Authorization: Bearer <TOKEN_ADMIN>' https://<HOST>/admin/backup/status | python3 -m json.tool"

# ── Resumo ────────────────────────────────────────────────────────────────────
sec "Resumo"
info "OK: $OK   Problemas: $PROBLEMAS"
if [ "$PROBLEMAS" -gt 0 ]; then
    cat <<EOF

Correção provável (ver RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md):
  1) Gerar a chave Fernet (GUARDE-A FORA do VPS):
       python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
  2) No $ENV_FILE:
       BACKUP_ENABLED=true
       BACKUP_ENCRYPTION_KEY=<a chave gerada>
       BACKUP_DRIVE_FOLDER_ID=$PASTA_ESPERADA
  3) docker compose restart backend
  4) Disparar teste (admin): POST /admin/backup/executar
     e confirmar na pasta 'Backup BD' os arquivos ejc_backup_<hoje>_db.enc e _uploads.enc
EOF
    exit 1
fi

info "Configuração aparenta OK. Se a pasta segue vazia, veja ultimo_resultado em"
info "/admin/backup/status e os logs do backend (docker logs $APP_CONTAINER | grep -i backup)."
exit 0
