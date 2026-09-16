#!/usr/bin/env bash
# EJC — wrapper operacional do backup nativo cifrado para pré-deploy.
#
# Contrato atual: `local_ok=true` + `local_persistido=true` nos artefatos prova
# que banco/uploads cifrados foram persistidos e fsyncados no BACKUP_DIR.
# Durante o PRIMEIRO deploy desta mudança, porém, o wrapper novo pode executar
# contra a imagem backend anterior (que ainda não emite `local_persistido`).
# Nesse bootstrap o gate aceita somente o contrato legado MAIS ESTRITO:
# par cifrado gerado + offsite_ok=true. Depois do recreate, o contrato local
# persistente passa a ser obrigatório e o offsite só bloqueia quando a política
# BACKUP_OFFSITE_OBRIGATORIO=true.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ejc}"
APP_CONTAINER="${APP_CONTAINER:-ejc_backend}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[backup] Docker não encontrado." >&2
  exit 2
fi

# `docker ps` também lista containers em restart loop. Nessa condição `docker
# exec` é recusado e o backup pré-deploy ficava bloqueado justamente durante
# recuperação de incidentes. Só usa exec quando o estado é efetivamente
# `running`; qualquer outro estado cai para a imagem existente em container
# efêmero, sem alterar o runtime defeituoso.
BACKEND_STATE="$(docker inspect -f '{{.State.Status}}' "$APP_CONTAINER" 2>/dev/null || true)"
if [ "$BACKEND_STATE" = "running" ]; then
  runner=(docker exec -i "$APP_CONTAINER" python -)
else
  [ -d "$APP_DIR" ] || {
    echo "[backup] APP_DIR inexistente: $APP_DIR" >&2
    exit 2
  }
  cd "$APP_DIR"
  docker compose config >/dev/null
  runner=(docker compose run --rm --no-deps -T backend python -)
  echo "[backup] Backend indisponível para exec (estado: ${BACKEND_STATE:-ausente}); usando imagem existente em container efêmero." >&2
fi

"${runner[@]}" <<'PY'
from __future__ import annotations

import asyncio
import json

from app.core.database import AsyncSessionLocal
from app.services import backup_execution_service
from app.services import backup_service


def _safe_artifact(item: dict) -> dict:
    safe = {
        "nome": item.get("nome"),
        "bytes_original": item.get("bytes_original"),
        "bytes_cifrado": item.get("bytes_cifrado"),
    }
    # A PRESENÇA da chave faz parte do handshake de versão. Não sintetize
    # `False` quando ela não existe, senão o primeiro deploy não consegue
    # distinguir o motor legado do contrato persistente novo.
    if "local_persistido" in item:
        safe["local_persistido"] = bool(item.get("local_persistido"))
    return safe


async def main() -> int:
    config = backup_service.configuracao_status()
    auth_mode = str(config.get("auth_mode") or "")
    destino = str(config.get("destino") or "gdrive")

    problems: list[str] = []
    required_local = {
        "enabled": "agendamento desabilitado",
        "chave_configurada": "chave de criptografia ausente",
        "pg_dump_disponivel": "pg_dump indisponível",
    }
    for field, message in required_local.items():
        if not bool(config.get(field)):
            problems.append(message)

    offsite_required = bool(config.get("offsite_obrigatorio"))

    # O destino externo só é pré-condição de CONFIGURAÇÃO no contrato novo
    # quando a política o torna obrigatório. No bootstrap legado ele será
    # exigido depois como PROVA (offsite_ok=true), independentemente da flag.
    if offsite_required and destino == "rclone":
        if not bool(config.get("rclone_remote_configurado")):
            problems.append("remote rclone ausente (BACKUP_RCLONE_REMOTE)")
        if not bool(config.get("rclone_disponivel")):
            problems.append("binário rclone indisponível")
    elif offsite_required:
        if not bool(config.get("pasta_configurada")):
            problems.append("pasta de destino ausente")
        if not bool(config.get("credencial_dedicada_configurada")):
            problems.append("credencial exclusiva ausente")
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
                    "destino": destino,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1

    async with AsyncSessionLocal() as db:
        result = await backup_execution_service.executar_backup_exclusivo(
            db,
            origem="pre_deploy",
            usuario_id=None,
            usuario_role="sistema",
        )

    artifacts = [_safe_artifact(item) for item in (result.get("artefatos") or [])]
    names = [str(item.get("nome") or "") for item in artifacts]
    has_db = any(name.endswith("_db.dump.enc") for name in names)
    has_uploads = any(name.endswith("_uploads.tar.gz.enc") for name in names)
    encrypted_pair = has_db and has_uploads
    offsite_ok = bool(result.get("offsite_ok"))
    offsite_erro = str(result.get("offsite_erro") or "") or None

    # Handshake do contrato: motores novos marcam explicitamente cada artefato.
    # Se a chave não existe em TODOS os itens, estamos no primeiro deploy sobre
    # runtime legado e aceitamos somente a prova histórica mais forte: offsite.
    persistent_contract = bool(artifacts) and all(
        "local_persistido" in item for item in artifacts
    )
    local_persisted = (
        persistent_contract
        and bool(result.get("local_ok"))
        and encrypted_pair
        and all(bool(item.get("local_persistido")) for item in artifacts)
    )

    if persistent_contract:
        contract = "local_persistente_v1"
        complete = (
            bool(result.get("ok"))
            and local_persisted
            and (offsite_ok or not offsite_required)
        )
    else:
        # Compatibilidade de CUTOVER somente. O motor antigo usa
        # TemporaryDirectory; portanto `local_ok` NÃO é retenção recuperável.
        # Exigir offsite_ok=true impede que a compatibilidade relaxe o gate.
        contract = "bootstrap_legado_offsite_estrito"
        complete = bool(result.get("ok")) and encrypted_pair and offsite_ok

    safe = {
        "ok": complete,
        "status": result.get("status"),
        "origem": result.get("origem"),
        "avisos": result.get("avisos") or [],
        "artefatos": artifacts,
        "duracao_segundos": result.get("duracao_segundos"),
        "banco_cifrado": has_db,
        "uploads_cifrados": has_uploads,
        "artefatos_cifrados_gerados": encrypted_pair,
        "artefatos_cifrados_persistidos": local_persisted,
        "backup_contract": contract,
        "local_ok": bool(result.get("local_ok")),
        "offsite_required": offsite_required,
        "credencial_dedicada": bool(config.get("credencial_dedicada_configurada")),
        "auth_mode": auth_mode,
        "destino": destino,
        "offsite_ok": offsite_ok,
        "offsite_erro": offsite_erro,
    }
    print(json.dumps(safe, ensure_ascii=False, sort_keys=True))
    return 0 if complete else 1


raise SystemExit(asyncio.run(main()))
PY
