"""
event_subscribers.py — Subscribers do barramento de eventos (ativação da
arquitetura orientada a eventos do EJC).

Importado em main.py por efeito colateral: ao importar, os decorators @on
registram os handlers no event_bus. Cada subscriber é ISOLADO (o event_bus já
captura exceções e nunca derruba o request) e ADITIVO — não duplica fluxos
diretos já existentes (triagem, notificações de prazo, kanban, etc.).

Eventos hoje emitidos pelo sistema:
  caso.criado       (cases.criar)
  caso.atualizado   (cases.atualizar)
  caso.encerrado    (cases.encerrar_caso)
  movimento.criado  (cases.criar_movimento)
  documento.importado (cases.aplicar_extracao)
"""
from __future__ import annotations
import logging

from app.services.event_bus import on

logger = logging.getLogger("ejc.event_subscribers")

# Tipos de andamento que valem tradução automática em linguagem simples.
_TRADUZ_TIPOS = {"intimacao", "decisao", "peticao", "audiencia", "movimento"}


@on("movimento.criado")
async def _traduzir_andamento(db, entidade_id, payload):
    """Ao registrar um andamento oficial, gera o resumo em linguagem simples (IA).
    Notas internas e itens 'ia' são ignorados (não precisam de tradução)."""
    tipo = (payload or {}).get("tipo", "")
    if tipo not in _TRADUZ_TIPOS:
        return
    from app.services.movimento_ia import traduzir_movimento
    await traduzir_movimento(db, entidade_id)


@on("caso.encerrado")
async def _log_encerramento(db, entidade_id, payload):
    """Trilha leve de encerramento (o aprendizado institucional já roda em
    background no handler; aqui só registramos o evento de domínio)."""
    logger.info(
        f"[evento] caso.encerrado {entidade_id} "
        f"resultado={(payload or {}).get('resultado')}"
    )


@on("documento.importado")
async def _log_importacao(db, entidade_id, payload):
    logger.info(
        f"[evento] documento.importado → caso {entidade_id} "
        f"(partes={(payload or {}).get('partes', 0)}, areas={(payload or {}).get('areas', 0)})"
    )
