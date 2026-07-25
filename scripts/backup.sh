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
import sys

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
    destino = str(config.get("destino") or "gdrive")
    offsite_obrigatorio = bool(config.get("offsite_obrigatorio"))

    # Gate LOCAL: sem isto não existe prova cifrada — bloqueia SEMPRE.
    problems: list[str] = []
    required_local = {
        "enabled": "agendamento desabilitado",
        "chave_configurada": "chave de criptografia ausente",
        "pg_dump_disponivel": "pg_dump indisponível",
    }
    for field, message in required_local.items():
        if not bool(config.get(field)):
            problems.append(message)

    # Gate OFFSITE: só bloqueia com BACKUP_OFFSITE_OBRIGATORIO=true; caso
    # contrário problemas de destino viram aviso (a prova local sustenta o
    # deploy) e a execução abaixo registra a falha offsite como "parcial".
    offsite_problems: list[str] = []
    if destino == "rclone":
        if not bool(config.get("rclone_remote_configurado")):
            offsite_problems.append("remote rclone ausente (BACKUP_RCLONE_REMOTE)")
        if not bool(config.get("rclone_disponivel")):
            offsite_problems.append("binário rclone indisponível")
    else:
        if not bool(config.get("pasta_configurada")):
            offsite_problems.append("pasta de destino ausente")
        if not bool(config.get("credencial_dedicada_configurada")):
            offsite_problems.append("credencial exclusiva ausente")
        if auth_mode == "inherit":
            offsite_problems.append("modo inherit não atende à segregação de credenciais")
    if offsite_obrigatorio:
        problems.extend(offsite_problems)

    if problems:
        print(
            json.dumps(
                {
                    "ok": False,
                    "status": "configuracao_insegura",
                    "problemas": problems,
                    "auth_mode": auth_mode or "indisponível",
                    "destino": destino,
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
    local_ok = bool(result.get("local_ok")) and has_db and has_uploads
    offsite_ok = bool(result.get("offsite_ok"))
    offsite_erro = str(result.get("offsite_erro") or "") or None
    # Gate do deploy: exige a prova LOCAL completa (banco + uploads cifrados)
    # e respeita o resultado do serviço ("parcial" por offsite falho continua
    # ok=True quando BACKUP_OFFSITE_OBRIGATORIO=false).
    complete = bool(result.get("ok")) and local_ok

    safe = {
        "ok": complete,
        "status": result.get("status"),
        "origem": result.get("origem"),
        "avisos": result.get("avisos") or [],
        "artefatos": artifacts,
        "duracao_segundos": result.get("duracao_segundos"),
        "banco_cifrado": has_db,
        "uploads_cifrados": has_uploads,
        "credencial_dedicada": bool(config.get("credencial_dedicada_configurada")),
        "auth_mode": auth_mode,
        "destino": destino,
        "local_ok": local_ok,
        "offsite_ok": offsite_ok,
        "offsite_erro": offsite_erro,
    }
    if complete and not offsite_ok:
        print(
            f"AVISO GRAVE: backup offsite falhou (destino {destino}): "
            f"{offsite_erro or 'erro não informado'} — deploy prossegue com "
            "prova local; corrija o destino offsite",
            file=sys.stderr,
        )
    print(json.dumps(safe, ensure_ascii=False, sort_keys=True))
    return 0 if complete else 1


raise SystemExit(asyncio.run(main()))
PY
