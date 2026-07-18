# ── app/routers/ia_agente.py ─────────────────────────────────────────────────
# MÓDULO AGÊNTICO DE IA — endpoint SSE. A IA opera como agente com loop de
# tool-use (decide → chama ferramenta → lê resultado → decide), streamando os
# eventos do loop (passo/ferramenta/resultado/confirmacao_requerida/final/erro).
#
# Guardrails: exige get_current_user + acesso ao caso (verificar_acesso_caso, o
# loop re-checa em cada tool); rate-limit como os demais routers de IA; TUDO
# atrás de AI_AGENT_ENABLED (default False) — com a flag OFF responde 404 claro
# e nada muda no sistema.
from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.ia_agente import AgenteStreamRequest
from app.services.ai.agent.loop import rodar_agente

logger = logging.getLogger("ejc.ai.agent.router")

router = APIRouter(prefix="/ia", tags=["IA — Agente (tool-use / HITL)"])


@router.post("/agente/stream",
             dependencies=[Depends(rate_limit("ia-agente-stream", 10))])
async def agente_stream(
    req: AgenteStreamRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Executa (ou RETOMA) o agente (loop de tool-use) e streama os eventos via SSE.

    Eventos: `passo`, `ferramenta`, `resultado`, `confirmacao_requerida`,
    `degradacao`, `recusado`, `final`, `erro`. Escritas pausam com
    `confirmacao_requerida` devolvendo `{token, args_hash, ferramenta, args}`; o
    cliente retoma re-invocando com `retomar_token` + `decisao` (aprovar/recusar),
    ou — se o Redis estiver indisponível (token=None) — reenviando `mensagem` com
    o `aprovacoes_hash` do tool_call aprovado (HITL vinculado aos ARGS, achado H1).
    """
    settings = get_settings()
    if not settings.AI_AGENT_ENABLED:
        # Flag OFF → recurso inexistente (comportamento idêntico ao atual).
        raise HTTPException(status_code=404, detail="Módulo agêntico de IA desabilitado")

    # Cliente externo nunca acessa o agente (defense-in-depth; o AuthMiddleware
    # já barra fora do portal, mas reforçamos aqui).
    role = getattr(getattr(cu, "role", None), "value", None) or str(getattr(cu, "role", ""))
    if role == "cliente_externo":
        raise HTTPException(status_code=403, detail="Sem permissão")

    # Gate de ownership antes de iniciar o stream (o loop re-checa em cada tool).
    await verificar_acesso_caso(db, cu, req.case_id)

    fila: asyncio.Queue = asyncio.Queue()

    async def on_event(tipo: str, dados: dict) -> None:
        await fila.put({"event": tipo, "data": dados})

    async def _executar() -> None:
        # M4/S4: o agente roda numa AsyncSession PRÓPRIA (não a `db` da request).
        # A tarefa é concorrente ao gerador; compartilhar a mesma AsyncSession
        # (não thread-safe) causaria uso concorrente. A sessão dedicada é fechada
        # aqui e o cancelamento é AGUARDADO no gerador (sem sessão órfã).
        try:
            async with AsyncSessionLocal() as agente_db:
                resultado = await rodar_agente(
                    db=agente_db, user=cu, case_id=req.case_id, mensagem=req.mensagem,
                    aprovacoes_hash=set(req.aprovacoes_hash or []),
                    retomar_token=req.retomar_token, decisao=req.decisao,
                    on_event=on_event,
                )
            # `final`/`erro` já são emitidos pelo loop; para status pendente ou
            # qualquer retorno sem evento terminal, garantimos um evento de fecho.
            if resultado.get("status") == "pendente_confirmacao":
                await fila.put({"event": "confirmacao_requerida", "data": resultado})
        except asyncio.CancelledError:
            raise
        except Exception as e:  # nunca vaza detalhe cru
            logger.warning("rodar_agente falhou: %s", str(e)[:200])
            await fila.put({"event": "erro", "data": {"detalhe": type(e).__name__}})
        finally:
            await fila.put(None)  # sentinela de término do stream

    async def _gerar():
        tarefa = asyncio.create_task(_executar())
        try:
            while True:
                item = await fila.get()
                if item is None:
                    break
                yield {
                    "event": item["event"],
                    "data": json.dumps(item["data"], ensure_ascii=False, default=str),
                }
        finally:
            # Cliente desconectou no meio: cancela E AGUARDA a tarefa terminar,
            # garantindo que a AsyncSession dedicada seja fechada antes de sair.
            if not tarefa.done():
                tarefa.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tarefa

    return EventSourceResponse(_gerar())
