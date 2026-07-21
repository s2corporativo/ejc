#!/usr/bin/env bash
# EJC — wrapper operacional do backup nativo cifrado.
#
# Este arquivo existia antes do serviço atual e fazia pg_dump/tar + rclone em
# claro. Esse caminho foi removido: banco e documentos contêm PII e nunca podem
# sair da VPS ou permanecer em retenção local sem cifragem.
#
# O serviço canônico executa pg_dump -Fc + uploads, cifra ambos com Fernet antes
# do upload, usa credencial dedicada, rotaciona somente o prefixo EJC e persiste
# estado/auditoria. O wrapper é mantido para cron e deploys antigos continuarem
# chamando o nome conhecido sem duplicar a implementação.
set -euo pipefail

APP_CONTAINER="${APP_CONTAINER:-ejc_backend}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[backup] Docker não encontrado." >&2
  exit 2
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$APP_CONTAINER"; then
  echo "[backup] Container $APP_CONTAINER não está em execução." >&2
  exit 2
fi

# O programa é enviado por STDIN, sem chave, senha ou token no argv. O container
# carrega as configurações do próprio ambiente. Status parcial também bloqueia o
# deploy: a prova pré-deploy precisa conter banco E uploads.
docker exec -i "$APP_CONTAINER" python - <<'PY'
from __future__ import annotations

import asyncio
import json

from app.core.database import AsyncSessionLocal
from app.services.backup_service import executar_backup


async def main() -> int:
    async with AsyncSessionLocal() as db:
        result = await executar_backup(
            db,
            origem="pre_deploy",
            usuario_id=None,
            usuario_role="sistema",
        )
    safe = {
        "ok": bool(result.get("ok")),
        "status": result.get("status"),
        "origem": result.get("origem"),
        "avisos": result.get("avisos") or [],
        "artefatos": [
            {
                "nome": item.get("nome"),
                "bytes_original": item.get("bytes_original"),
                "bytes_cifrado": item.get("bytes_cifrado"),
                "drive_file_id": item.get("drive_file_id"),
            }
            for item in (result.get("artefatos") or [])
        ],
        "duracao_segundos": result.get("duracao_segundos"),
        "erro": result.get("erro"),
    }
    print(json.dumps(safe, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "sucesso" else 1


raise SystemExit(asyncio.run(main()))
PY
