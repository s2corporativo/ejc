#!/usr/bin/env bash
# EJC — wrapper operacional do backup nativo cifrado.
#
# O fluxo legado de pg_dump/tar + rclone em claro foi removido. Banco, uploads e
# documentos contêm PII e não podem sair da VPS nem permanecer em retenção local
# sem criptografia. A implementação canônica vive em backup_service.py.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
APP_CONTAINER="${APP_CONTAINER:-ejc_backend}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[backup] Docker não encontrado." >&2
  exit 2
fi

# O programa é enviado por STDIN: chave, senha e tokens nunca entram no argv.
# Com a API saudável, reutiliza-se a imagem em produção. Em crash-loop/container
# parado, usa-se um container efêmero da imagem anterior, com o mesmo env_file e
# volumes, para que um deploy corretivo ainda tenha prova pré-deploy.
if docker ps --format '{{.Names}}' | grep -qx "$APP_CONTAINER"; then
  runner=(docker exec -i "$APP_CONTAINER" python -)
else
  [ -d "$APP_DIR" ] || {
    echo "[backup] APP_DIR inexistente: $APP_DIR" >&2
    exit 2
  }
  cd "$APP_DIR"
  docker compose config >/dev/null
  runner=(docker compose run --rm --no-deps -T backend python -)
  echo "[backup] Backend parado; usando imagem anterior em container efêmero." >&2
fi

"${runner[@]}" <<'PY'
from __future__ import annotations

import asyncio
import json

from app.core.database import AsyncSessionLocal
from app.services import backup_service


def _safe_artifact(item: dict) -> dict:
    return {
        "nome": item.get("nome"),
        "bytes_original": item.get("bytes_original"),
        "bytes_cifrado": item.get("bytes_cifrado"),
    }


async def main() -> int:
    config = backup_service.configuracao_status()
    auth_mode = str(config.get("auth_mode") or "")
    problems: list[str] = []
    required = {
        "enabled": "agendamento desabilitado",
        "chave_configurada": "chave de criptografia ausente",
        "pasta_configurada": "pasta de destino ausente",
        "credencial_dedicada_configurada": "credencial exclusiva ausente",
        "pg_dump_disponivel": "pg_dump indisponível",
    }
    for field, message in required.items():
        if not bool(config.get(field)):
            problems.append(message)
    if auth_mode == "inherit":
        problems.append("modo inherit não atende à segregação de credenciais")

    if problems:
        print(
            json.dumps(
                {
                    "ok": False,
                    "status": "configuracao_insegura",
                    "problemas": problems,
                    "auth_mode": auth_mode or "indisponível",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1

    async with AsyncSessionLocal() as db:
        result = await backup_service.executar_backup(
            db,
            origem="pre_deploy",
            usuario_id=None,
            usuario_role="sistema",
        )

    artifacts = [_safe_artifact(item) for item in (result.get("artefatos") or [])]
    names = [str(item.get("nome") or "") for item in artifacts]
    has_db = any(name.endswith("_db.dump.enc") for name in names)
    has_uploads = any(name.endswith("_uploads.tar.gz.enc") for name in names)
    complete = result.get("status") == "sucesso" and has_db and has_uploads

    safe = {
        "ok": complete,
        "status": result.get("status"),
        "origem": result.get("origem"),
        "avisos": result.get("avisos") or [],
        "artefatos": artifacts,
        "duracao_segundos": result.get("duracao_segundos"),
        "banco_cifrado": has_db,
        "uploads_cifrados": has_uploads,
        "credencial_dedicada": True,
        "auth_mode": auth_mode,
    }
    print(json.dumps(safe, ensure_ascii=False, sort_keys=True))
    return 0 if complete else 1


raise SystemExit(asyncio.run(main()))
PY
