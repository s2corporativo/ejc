#!/usr/bin/env bash
# EJC/VPS — backup cifrado dos bancos das OUTRAS stacks da máquina.
#
# MOTIVO (levantamento de 27/07/2026): a VPS hospeda seis stacks de produção,
# mas só o EJC tinha rotina de backup (backend/app/services/backup_service.py +
# RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md). verdelimp e sistema-s2 rodam banco de
# clientes há semanas sem cópia nenhuma — risco maior que qualquer desorganização
# de diretório. Este script cobre essa lacuna com o MESMO contrato do EJC:
#
#   FAIL-CLOSED: sem BACKUP_ENCRYPTION_KEY o script RECUSA rodar. Dump de banco
#   de cliente não sai em claro; perder o backup é ruim, vazar é pior.
#
# Cifra com Fernet (mesma primitiva do EJC) via python3+cryptography, que já
# existe na VPS por causa do próprio EJC. Nada de senha em argv: a chave entra
# por variável de ambiente e o conteúdo trafega por stdin.
#
# Uso:
#   BACKUP_ENCRYPTION_KEY=... bash scripts/backup-stacks-vps.sh            # dry-run
#   BACKUP_ENCRYPTION_KEY=... bash scripts/backup-stacks-vps.sh --apply
#   RETENCAO_DIAS=30 BACKUP_DIR=/opt/backups/stacks ... --apply
#
# Restaurar (exemplo Postgres):
#   python3 -c "from cryptography.fernet import Fernet;import sys,os;\
#     sys.stdout.buffer.write(Fernet(os.environ['BACKUP_ENCRYPTION_KEY'].encode())\
#     .decrypt(open('arquivo.sql.fernet','rb').read()))" > dump.sql
#   docker exec -i <container> psql -U <user> -d <db> < dump.sql
set -euo pipefail

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

BACKUP_DIR="${BACKUP_DIR:-/opt/backups/stacks}"
RETENCAO_DIAS="${RETENCAO_DIAS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"

# container|engine|user_env|db_env — engine define o comando de dump.
# O EJC fica FORA de propósito: já tem rotina própria, cifrada e com offsite.
STACKS="${STACKS:-
verdelimp-db|postgres|POSTGRES_USER|POSTGRES_DB
sistema-s2-db|mysql|MYSQL_USER|MYSQL_DATABASE
deployment-db-1|mysql|MYSQL_USER|MYSQL_DATABASE
}"

titulo() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
erro()   { printf '\033[31m  ✗ %s\033[0m\n' "$1" >&2; }
ok()     { printf '  ✓ %s\n' "$1"; }

# ── Fail-closed: sem chave, não roda ─────────────────────────────────────────
if [ -z "${BACKUP_ENCRYPTION_KEY:-}" ]; then
  erro "BACKUP_ENCRYPTION_KEY ausente — o backup NÃO roda em claro."
  echo "    Gere uma chave (guarde FORA da VPS; sem ela o backup é irrecuperável):" >&2
  echo "    python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"" >&2
  exit 2
fi
python3 -c "
from cryptography.fernet import Fernet
import os, sys
try:
    Fernet(os.environ['BACKUP_ENCRYPTION_KEY'].encode())
except Exception as e:
    sys.exit(f'chave inválida: {e}')
" || { erro "BACKUP_ENCRYPTION_KEY não é uma chave Fernet válida."; exit 2; }

titulo "Contexto"
echo "  destino:   $BACKUP_DIR"
echo "  retenção:  $RETENCAO_DIAS dias"
echo "  modo:      $([ "$APPLY" = "1" ] && echo 'APLICAR' || echo 'dry-run (nada será gravado)')"

[ "$APPLY" = "1" ] && mkdir -p "$BACKUP_DIR"

# Cifra stdin → arquivo, sem passar segredo por argv nem gravar texto claro.
cifrar_para() {
  python3 -c "
from cryptography.fernet import Fernet
import os, sys
dados = sys.stdin.buffer.read()
if not dados:
    sys.exit('dump vazio — abortado')
open(sys.argv[1], 'wb').write(Fernet(os.environ['BACKUP_ENCRYPTION_KEY'].encode()).encrypt(dados))
" "$1"
}

falhas=0
titulo "Bancos"
printf '%s\n' "$STACKS" | while IFS='|' read -r container engine user_env db_env; do
  [ -n "${container:-}" ] || continue

  if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$container"; then
    echo "  – $container: container ausente (stack não instalada aqui) — ignorado"
    continue
  fi

  # Credenciais vêm do ambiente do PRÓPRIO container: nada fica no script.
  usuario="$(docker exec "$container" printenv "$user_env" 2>/dev/null || true)"
  banco="$(docker exec "$container" printenv "$db_env" 2>/dev/null || true)"
  if [ -z "$usuario" ] || [ -z "$banco" ]; then
    erro "$container: não achei $user_env/$db_env no ambiente do container"
    falhas=$((falhas + 1))
    continue
  fi

  destino="$BACKUP_DIR/${container}-${banco}-${STAMP}.sql.fernet"
  case "$engine" in
    postgres) cmd=(docker exec "$container" pg_dump -U "$usuario" -d "$banco") ;;
    mysql)    cmd=(docker exec "$container" sh -c "exec mysqldump -u \"$usuario\" -p\"\$MYSQL_PASSWORD\" --single-transaction --routines \"$banco\"") ;;
    *)        erro "$container: engine desconhecida '$engine'"; falhas=$((falhas + 1)); continue ;;
  esac

  if [ "$APPLY" != "1" ]; then
    echo "  [dry-run] $container ($engine) → $(basename "$destino")"
    continue
  fi

  if "${cmd[@]}" 2>/dev/null | cifrar_para "$destino"; then
    ok "$container → $(basename "$destino") ($(du -h "$destino" | cut -f1))"
  else
    erro "$container: dump falhou — VERIFIQUE (backup deste banco NÃO existe)"
    rm -f "$destino"
    falhas=$((falhas + 1))
  fi
done

# ── Retenção ─────────────────────────────────────────────────────────────────
titulo "Retenção (> $RETENCAO_DIAS dias)"
if [ "$APPLY" = "1" ]; then
  antigos="$(find "$BACKUP_DIR" -maxdepth 1 -name '*.sql.fernet' -mtime "+$RETENCAO_DIAS" 2>/dev/null | wc -l)"
  find "$BACKUP_DIR" -maxdepth 1 -name '*.sql.fernet' -mtime "+$RETENCAO_DIAS" -delete 2>/dev/null || true
  ok "$antigos arquivo(s) além da retenção removido(s)"
  echo
  ls -lh "$BACKUP_DIR" 2>/dev/null | tail -8
else
  echo "  [dry-run] removeria .sql.fernet com mais de $RETENCAO_DIAS dias"
fi

cat <<'NOTA'

PENDÊNCIAS CONSCIENTES (este script é o piso, não o teto):
  • OFFSITE: os arquivos ficam na MESMA máquina. Perda do VPS = perda do backup.
    O EJC já envia para o Drive via rclone; replicar isso aqui é o próximo passo.
  • RESTORE TESTADO: backup sem restore provado é esperança, não continuidade.
    Teste periodicamente restaurando em banco vazio (é o que o gate de CI do
    EJC faz — vale estender às demais stacks).
  • A CHAVE: guarde BACKUP_ENCRYPTION_KEY FORA da VPS. Sem ela, estes arquivos
    são lixo cifrado; com ela junto do backup, a cifra não protege de nada.

Agendar diariamente (após o backup do EJC, que roda 02:00):
  sudo crontab -e
  30 2 * * * BACKUP_ENCRYPTION_KEY=... bash /opt/ejc/scripts/backup-stacks-vps.sh --apply >> /var/log/backup-stacks.log 2>&1
NOTA

exit 0
