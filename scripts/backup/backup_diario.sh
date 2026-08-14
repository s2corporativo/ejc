#!/usr/bin/env bash
# Compatibility shim do antigo cron diário.
#
# O fluxo histórico gravava dump do PostgreSQL e uploads/GED em claro no host,
# o que é incompatível com a política LGPD atual do EJC. Este arquivo permanece
# apenas para não quebrar crontabs antigos: toda execução delega ao wrapper
# cifrado/exclusivo `scripts/backup.sh`.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

printf '[backup-diario] compatibilidade: delegando ao motor cifrado/exclusivo.\n' >&2
printf '[backup-diario] remova crons legados após confirmar o scheduler canônico.\n' >&2

BACKUP_ORIGEM=agendado exec bash "$ROOT/scripts/backup.sh"
