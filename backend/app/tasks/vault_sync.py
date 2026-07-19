# ── app/tasks/vault_sync.py ──────────────────────────────────────────────────
# Ressincronização do Cofre de Credenciais no worker Celery (PR-2).
#
# O worker é um PROCESSO separado da API: o overlay aplicado no lifespan do
# FastAPI não chega até ele. Aqui um handler de `task_prerun` faz uma checagem
# BARATA (TTL em memória, sem I/O dentro do TTL) do token de versão do cofre
# antes de cada task; mudou → reaplica o overlay no singleton Settings DESTE
# processo, numa sessão de banco própria (mesmo padrão asyncio.run +
# engine.dispose de rag_tasks — loop novo por chamada não pode deixar pool
# preso a loop morto).
#
# Falha SILENCIOSA com log: sincronizar o cofre nunca pode quebrar a task do
# usuário (ela roda com os valores atuais — no pior caso, os do .env).
from __future__ import annotations

import asyncio
import logging
import time

from celery.signals import task_prerun

logger = logging.getLogger("ejc.tasks.vault_sync")

# TTL da checagem de versão (plano exige ≤ 60s).
SYNC_TTL_SEGUNDOS = 45.0

# Estado do processo worker (cada processo tem o seu — é o objetivo).
_estado: dict = {"proxima_checagem": 0.0, "versao": None}


async def _verificar_e_aplicar() -> None:
    """Compara o token de versão do cofre e reaplica o overlay se mudou."""
    from app.core.database import AsyncSessionLocal, engine
    from app.services import credential_vault_service

    try:
        async with AsyncSessionLocal() as db:
            versao = await credential_vault_service.versao_atual(db)
            if versao != _estado["versao"]:
                campos = await credential_vault_service.aplicar_overlay(db)
                _estado["versao"] = versao
                logger.info(
                    "[cofre] worker ressincronizado: overlay em %d campo(s)",
                    len(campos),
                )
    finally:
        # asyncio.run cria loop novo a cada sync — pool do engine não pode
        # sobreviver preso a um loop morto (padrão de rag_tasks).
        await engine.dispose()


@task_prerun.connect
def sincronizar_cofre(**_kwargs) -> None:
    """Antes de cada task: checagem barata com TTL; nunca propaga exceção."""
    agora = time.monotonic()
    if agora < _estado["proxima_checagem"]:
        return
    _estado["proxima_checagem"] = agora + SYNC_TTL_SEGUNDOS
    try:
        asyncio.run(_verificar_e_aplicar())
    except Exception as e:  # noqa: BLE001 — sync nunca derruba a task do usuário
        from app.core.log_sanitizer import safe_exception_log
        logger.warning("[cofre] sync do worker falhou (seguindo com valores "
                       "atuais)", extra=safe_exception_log(e))
