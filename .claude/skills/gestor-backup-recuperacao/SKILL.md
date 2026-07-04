---
name: gestor-backup-recuperacao
description: >
  Implementa e gerencia estratégia de backup automatizado e recuperação de desastres para os sistemas EJC, Verde Limp e S2. Use SEMPRE que precisar configurar, automatizar ou executar backup: backup diário de PostgreSQL, backup de arquivos de upload, rotação automática de backups antigos, backup offsite (S3/Google Drive), restauração de banco em caso de falha, script de disaster recovery. Sem backup automatizado os sistemas correm risco crítico de perda de dados. Cobre: pg_dump agendado via cron, rsync de uploads, rotação por idade, alertas de falha por WhatsApp, restauração guiada. Acionado por: "backup sistema", "backup banco de dados", "pg_dump automático", "rotação de backup", "disaster recovery", "restaurar backup", "backup EJC", "backup PostgreSQL", "backup uploads", "perda de dados prevenção", "backup offsite", "cron backup".
---

# Gestor de Backup e Recuperação — EJC · Verde Limp · S2

## Contexto

```
DADOS CRÍTICOS:
  EJC:        PostgreSQL (casos, clientes, prazos, documentos)
  Verde Limp: SQLite ou PostgreSQL (contratos, OS, equipe)
  S2:         PostgreSQL (editais, propostas, contratos)
  Uploads:    PDFs de peças, documentos, fotos de OS

ESTRATÉGIA 3-2-1:
  3 cópias dos dados
  2 mídias diferentes (VPS local + offsite)
  1 cópia fora do local (S3, Google Drive ou segundo VPS)

FREQUÊNCIA:
  Banco: diário às 2h (retenção 30 dias)
  Uploads: diário às 3h (retenção 7 cópias)
  Semanal completo: domingo às 1h (retenção 12 semanas)
```

---

## 1. Script de Backup PostgreSQL

```bash
#!/bin/bash
# /opt/scripts/backup_postgres.sh

set -euo pipefail

# Configurações
DB_HOST="${DB_HOST:-localhost}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-ejc_db}"
BACKUP_DIR="/backups/postgres"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump"
LOG_FILE="/var/log/backup.log"

# Função de log
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"; }

# Criar diretório se não existir
mkdir -p "$BACKUP_DIR"

log "Iniciando backup: $DB_NAME"

# Executar pg_dump (formato custom — comprimido, restaurável)
if PGPASSWORD="$DB_PASS" pg_dump \
    -h "$DB_HOST" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -F c \
    -Z 9 \
    -f "$BACKUP_FILE" 2>> "$LOG_FILE"; then
    
    SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
    log "✅ Backup concluído: $BACKUP_FILE ($SIZE)"
    
    # Rotação: remover backups mais antigos que RETENTION_DAYS dias
    find "$BACKUP_DIR" -name "${DB_NAME}_*.dump" -mtime "+${RETENTION_DAYS}" -delete
    DELETED=$(find "$BACKUP_DIR" -name "${DB_NAME}_*.dump" -mtime "+${RETENTION_DAYS}" | wc -l)
    log "Rotação: ${DELETED} backups antigos removidos"
    
    # Verificar integridade do backup
    if PGPASSWORD="$DB_PASS" pg_restore --list "$BACKUP_FILE" > /dev/null 2>&1; then
        log "✅ Integridade verificada"
    else
        log "⚠️ Falha na verificação de integridade"
    fi
    
    # Upload offsite (opcional — S3 ou rclone para Google Drive)
    if command -v rclone &>/dev/null && [ -n "${RCLONE_REMOTE:-}" ]; then
        rclone copy "$BACKUP_FILE" "${RCLONE_REMOTE}/backups/postgres/" --log-file="$LOG_FILE"
        log "✅ Upload offsite concluído"
    fi
    
    # Notificar sucesso (apenas se WhatsApp configurado)
    if [ -n "${ZAPI_URL:-}" ]; then
        curl -s -X POST "${ZAPI_URL}/send-text" \
            -H "Client-Token: ${ZAPI_CLIENT_TOKEN}" \
            -d "{\"phone\":\"${WHATSAPP_ADMIN}\",\"message\":\"✅ Backup ${DB_NAME} concluído\\n${TIMESTAMP}\\nTamanho: ${SIZE}\"}" \
            >> "$LOG_FILE" 2>&1 || true
    fi
    
    exit 0
else
    log "❌ FALHA NO BACKUP: $DB_NAME"
    
    # Notificar falha — crítico
    if [ -n "${ZAPI_URL:-}" ]; then
        curl -s -X POST "${ZAPI_URL}/send-text" \
            -H "Client-Token: ${ZAPI_CLIENT_TOKEN}" \
            -d "{\"phone\":\"${WHATSAPP_ADMIN}\",\"message\":\"🔴 FALHA no backup ${DB_NAME}\\n${TIMESTAMP}\\nVerificar /var/log/backup.log\"}" \
            >> "$LOG_FILE" 2>&1 || true
    fi
    
    exit 1
fi
```

---

## 2. Backup de Uploads (arquivos)

```bash
#!/bin/bash
# /opt/scripts/backup_uploads.sh

UPLOADS_DIR="/opt/ejc/uploads"
BACKUP_DIR="/backups/uploads"
TIMESTAMP=$(date +%Y%m%d)
BACKUP_FILE="${BACKUP_DIR}/uploads_${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

# Compactar uploads do dia
tar -czf "$BACKUP_FILE" -C "$(dirname $UPLOADS_DIR)" "$(basename $UPLOADS_DIR)" 2>/dev/null
SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo "[$(date)] Backup uploads: $BACKUP_FILE ($SIZE)" >> /var/log/backup.log

# Manter apenas 7 backups de uploads
ls -t "${BACKUP_DIR}"/uploads_*.tar.gz | tail -n +8 | xargs rm -f 2>/dev/null || true

# Sincronizar com offsite (incremental — mais eficiente)
if command -v rclone &>/dev/null && [ -n "${RCLONE_REMOTE:-}" ]; then
    rclone sync "$UPLOADS_DIR" "${RCLONE_REMOTE}/backups/uploads/" --log-level INFO
fi
```

---

## 3. Via Docker (sem acesso direto ao host)

```bash
#!/bin/bash
# Backup PostgreSQL via container Docker
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="/backups/ejc_${TIMESTAMP}.dump"

docker-compose -f /opt/ejc/docker-compose.yml exec -T db \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c -Z 9 \
    > "$BACKUP_FILE"

echo "Backup: $BACKUP_FILE ($(du -sh $BACKUP_FILE | cut -f1))"
```

---

## 4. Agendamento via Cron

```bash
# Adicionar ao cron: crontab -e
# Backup diário do banco — 2h da manhã
0 2 * * * /opt/scripts/backup_postgres.sh >> /var/log/backup_cron.log 2>&1

# Backup uploads — 3h da manhã
0 3 * * * /opt/scripts/backup_uploads.sh >> /var/log/backup_cron.log 2>&1

# Backup semanal completo (domingo 1h) — retém 12 semanas
0 1 * * 0 RETENTION_DAYS=84 /opt/scripts/backup_postgres.sh >> /var/log/backup_cron.log 2>&1
```

---

## 5. Protocolo de Restauração

```bash
# ─── RESTAURAR BANCO POSTGRESQL ───────────────────────────────────────
# 1. Identificar backup mais recente
ls -lht /backups/postgres/ | head -5

# 2. Parar serviço (evitar escritas durante restauração)
docker-compose stop backend

# 3. Dropar e recriar banco (CUIDADO: irreversível)
docker-compose exec db psql -U postgres -c "DROP DATABASE ejc_db;"
docker-compose exec db psql -U postgres -c "CREATE DATABASE ejc_db OWNER ejc_user;"

# 4. Restaurar
PGPASSWORD="$DB_PASS" pg_restore \
    -h localhost -U "$DB_USER" -d "$DB_NAME" \
    --clean --if-exists \
    /backups/postgres/ejc_db_20260521_020000.dump

# 5. Verificar integridade
docker-compose exec db psql -U "$DB_USER" -d "$DB_NAME" \
    -c "SELECT COUNT(*) FROM clients; SELECT COUNT(*) FROM cases; SELECT COUNT(*) FROM deadlines;"

# 6. Reiniciar serviço
docker-compose start backend

# ─── RESTAURAR UPLOADS ────────────────────────────────────────────────
tar -xzf /backups/uploads/uploads_20260521.tar.gz -C /opt/ejc/
```

---

## 6. Verificação de Backups (script de auditoria)

```bash
#!/bin/bash
# /opt/scripts/check_backups.sh — executar diariamente para verificar saúde dos backups

BACKUP_DIR="/backups/postgres"
MAX_AGE_HOURS=25  # Backup deve ter menos de 25h (margem para atraso)
ALERT_PHONE="${WHATSAPP_ADMIN}"

latest=$(ls -t "${BACKUP_DIR}"/*.dump 2>/dev/null | head -1)

if [ -z "$latest" ]; then
    MSG="🔴 CRÍTICO: Nenhum backup encontrado em $BACKUP_DIR"
    echo "$MSG"
    # Enviar alerta WhatsApp
elif [ $(( ($(date +%s) - $(stat -c %Y "$latest")) / 3600 )) -gt $MAX_AGE_HOURS ]; then
    AGE=$(( ($(date +%s) - $(stat -c %Y "$latest")) / 3600 ))
    MSG="⚠️ Backup desatualizado: último há ${AGE}h ($latest)"
    echo "$MSG"
else
    SIZE=$(du -sh "$latest" | cut -f1)
    echo "✅ Backup OK: $latest ($SIZE)"
fi
```

---

## 7. Variáveis de Ambiente

```env
# Banco
DB_HOST=localhost
DB_USER=ejc_user
DB_PASS=SENHA_BANCO
DB_NAME=ejc_db

# Offsite (rclone configurado previamente)
RCLONE_REMOTE=gdrive  # ou s3:meu-bucket

# Notificações
ZAPI_URL=https://api.z-api.io/instances/INST/token/TOKEN
ZAPI_CLIENT_TOKEN=CLIENT_TOKEN
WHATSAPP_ADMIN=5531999074546
```
