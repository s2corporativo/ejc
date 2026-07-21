#!/usr/bin/env python3
"""Sonda somente-leitura da saúde do backup nativo do EJC.

Pode ser enviada por STDIN ao Python do container de produção:
    docker exec -i ejc_backend python - < scripts/backup/check_backup_health.py

A saída é JSON sem segredos; o exit code é 0 somente quando configuração,
recência, status e artefatos de banco/uploads estão íntegros.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any


def _datetime_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def avaliar_saude_backup(
    configuracao: dict[str, Any],
    estado: dict[str, Any] | None,
    *,
    agora: datetime | None = None,
    max_age_hours: float = 30.0,
) -> dict[str, Any]:
    agora = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    problemas: list[str] = []

    obrigatorios = {
        "enabled": "agendamento desabilitado",
        "chave_configurada": "chave de criptografia ausente",
        "pasta_configurada": "pasta de destino ausente",
        "credencial_drive_configurada": "credencial de escrita do Drive ausente",
        "pg_dump_disponivel": "pg_dump indisponível",
    }
    for campo, mensagem in obrigatorios.items():
        if not bool(configuracao.get(campo)):
            problemas.append(mensagem)

    status = None
    last_run = None
    age_hours = None
    artefatos: list[dict[str, Any]] = []

    if not estado:
        problemas.append("nenhuma execução de backup registrada")
    else:
        status = estado.get("last_status")
        if status != "sucesso":
            problemas.append(f"último status não é sucesso: {status or 'ausente'}")

        last_run = _datetime_utc(estado.get("last_run_at"))
        if last_run is None:
            problemas.append("data da última execução ausente ou inválida")
        else:
            age_hours = round((agora - last_run).total_seconds() / 3600, 2)
            if age_hours < -0.1:
                problemas.append("data da última execução está no futuro")
            elif age_hours > max_age_hours:
                problemas.append(
                    f"backup atrasado: {age_hours}h sem sucesso "
                    f"(limite {max_age_hours}h)"
                )

        detalhes = estado.get("detalhes")
        if isinstance(detalhes, str):
            try:
                detalhes = json.loads(detalhes)
            except json.JSONDecodeError:
                detalhes = None
        if isinstance(detalhes, list):
            artefatos = [item for item in detalhes if isinstance(item, dict)]

        nomes = [str(item.get("nome") or "") for item in artefatos]
        if not any("_db.dump.enc" in nome for nome in nomes):
            problemas.append("artefato cifrado do banco ausente")
        if not any("_uploads.tar.gz.enc" in nome for nome in nomes):
            problemas.append("artefato cifrado dos uploads ausente")

    return {
        "ok": not problemas,
        "verificado_em": agora.isoformat(),
        "max_age_hours": max_age_hours,
        "last_run_at": last_run.isoformat() if last_run else None,
        "age_hours": age_hours,
        "last_status": status,
        "artefatos": [
            {
                "nome": item.get("nome"),
                "bytes_original": item.get("bytes_original"),
                "bytes_cifrado": item.get("bytes_cifrado"),
            }
            for item in artefatos
        ],
        "configuracao": {
            campo: bool(configuracao.get(campo)) for campo in obrigatorios
        },
        "problemas": problemas,
    }


async def _coletar() -> tuple[dict[str, Any], dict[str, Any] | None]:
    from app.core.database import AsyncSessionLocal
    from app.services import backup_service

    async with AsyncSessionLocal() as db:
        estado = await backup_service.obter_estado(db)
    return backup_service.configuracao_status(), estado


async def _main() -> int:
    try:
        max_age = float(os.getenv("BACKUP_MAX_AGE_HOURS", "30"))
    except ValueError:
        max_age = 30.0
    try:
        configuracao, estado = await _coletar()
        resultado = avaliar_saude_backup(
            configuracao,
            estado,
            max_age_hours=max_age,
        )
    except Exception as exc:
        resultado = {
            "ok": False,
            "verificado_em": datetime.now(timezone.utc).isoformat(),
            "problemas": [f"sonda indisponível: {type(exc).__name__}: {str(exc)[:300]}"],
        }
    print(json.dumps(resultado, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if resultado.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
