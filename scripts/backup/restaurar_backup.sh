#!/usr/bin/env bash
# Restore legado DESATIVADO.
#
# O formato histórico usava `ejc_db_*.dump` e `ejc_uploads_*.tar.gz` em claro.
# Esses artefatos não atendem à política atual de confidencialidade/LGPD do EJC.
# Restauração produtiva deve partir de artefatos CIFRADOS validados, em janela
# controlada, com backup prévio e rollback documentado.
set -euo pipefail

cat >&2 <<'EOF'
ABORTADO: o restore legado de dump/uploads em claro foi desativado.

Motivo:
- o formato histórico mantém dados jurídicos/PII sem criptografia em repouso;
- o script executava operação destrutiva sobre banco/uploads de produção;
- ele não é compatível com o motor cifrado atual.

Para validação de continuidade NÃO destrutiva da produção, use apenas:
  RESTORE_DRILL_ALLOW=1 python scripts/backup/restore_drill.py

Esse drill cria banco temporário aleatório, gera dump, cifra/decifra e valida a
restauração sem substituir o banco produtivo.

Restauração PRODUTIVA a partir de artefato cifrado continua bloqueada até o
runbook/restore cifrado controlado ser homologado. Não converta manualmente
backups para claro em diretórios persistentes.
EOF

exit 2
