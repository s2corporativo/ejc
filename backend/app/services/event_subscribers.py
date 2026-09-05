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

_TRADUZ_TIPOS = {"intimacao", "decisao", "peticao", "audiencia", "movimento"}
_TIPOS_PUBLICOS_CLIENTE = {"intimacao", "decisao", "audiencia", "movimento"}


def _install_document_analysis_hook() -> None:
    """Aponta o callback legado do router para a implementação compartilhada.

    Compatibilidade transitória: `documents.py` ainda referencia `_analisar_doc_bg`
    diretamente. Em vez de manter uma terceira cópia do algoritmo no boot, este
    adapter instala a função única de `document_analysis_hook`. A remoção física
    do símbolo legado do router pode ocorrer depois, sem alterar comportamento.
    """
    try:
        from app.routers import documents as documents_router
        from app.services.document_analysis_hook import analisar_documento_bg
    except Exception as exc:  # pragma: no cover
        logger.warning("Hook documental compartilhado indisponível: %s", exc)
        return

    documents_router._analisar_doc_bg = analisar_documento_bg
    logger.info("Hook documental centralizado em document_analysis_hook")


def _install_ai_core_hardening() -> None:
    """Ativa gates críticos; falha no patch impede boot inseguro."""
    try:
        from app.services.ai_core_hardening_patch import instalar

        instalar()
    except Exception as exc:
        logger.critical(
            "Hardening crítico do núcleo de IA/RAG não pôde ser instalado: %s",
            exc,
            exc_info=True,
        )
        raise RuntimeError("Hardening crítico do núcleo de IA/RAG indisponível") from exc


def _install_datajud_cognitive_feed() -> None:
    """Ativa DataJud → RAG nativo sem tornar o conector requisito de boot."""
    try:
        from app.services.datajud_cognitive_patch import instalar

        instalar()
    except Exception as exc:
        logger.error("Feed cognitivo DataJud indisponível: %s", exc, exc_info=True)


def _install_financial_scheduler_hardening() -> None:
    """Instala callbacks financeiros consolidados antes do scheduler iniciar.

    É um adapter isolado: preserva IDs/horários do scheduler central e corrige
    apenas as fontes de verdade do Morning Brief e a auditoria da transição de
    honorários para atrasado. Falhar aqui não deve derrubar todo o EJC, mas fica
    explícito em log para diagnóstico.
    """
    try:
        from app.services.scheduler_financeiro import instalar

        instalar()
    except Exception as exc:  # pragma: no cover
        logger.error(
            "Hardening financeiro do scheduler indisponível: %s",
            exc,
            exc_info=True,
        )


# Routers são registrados explicitamente em app/main.py. Aqui permanecem apenas
# subscribers e patches/adapters de comportamento já necessários ao runtime.
_install_document_analysis_hook()
_install_ai_core_hardening()
_install_datajud_cognitive_feed()
_install_financial_scheduler_hardening()


@on("movimento.criado")
async def _traduzir_andamento(db, entidade_id, payload):
    tipo = (payload or {}).get("tipo", "")
    if tipo not in _TRADUZ_TIPOS:
        return
    from app.services.movimento_ia import traduzir_movimento

    await traduzir_movimento(db, entidade_id)


@on("movimento.criado")
async def _notificar_cliente_movimento(db, entidade_id, payload):
    """Avisa o cliente com mensagem genérica, sem teor ou estratégia."""
    tipo = (payload or {}).get("tipo", "")
    if tipo not in _TIPOS_PUBLICOS_CLIENTE:
        return

    from sqlalchemy import select

    from app.models.case import Case
    from app.models.user import User, UserRole
    from app.services.notification_service import criar_notificacao_interna

    caso = await db.get(Case, entidade_id)
    if caso is None or not caso.client_id:
        return

    res = await db.execute(
        select(User).where(
            User.client_id == caso.client_id,
            User.role == UserRole.cliente_externo,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    usuarios_cliente = res.scalars().all()
    if not usuarios_cliente:
        return

    ref = f" (caso {caso.numero_interno})" if caso.numero_interno else ""
    for user in usuarios_cliente:
        await criar_notificacao_interna(
            db,
            user_id=user.id,
            titulo="Atualização no seu processo",
            mensagem=f"Há uma nova atualização no seu processo{ref}.",
            tipo="processo",
        )


@on("caso.encerrado")
async def _log_encerramento(db, entidade_id, payload):
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
