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


def _patch_precedentes_router() -> None:
    try:
        from app.routers import jurisprudencia_externa
        from app.routers import precedentes_jurisprudencia

        jurisprudencia_externa.router.include_router(precedentes_jurisprudencia.router)
        logger.info("Router de precedentes multifonte registrado")
    except Exception as exc:  # pragma: no cover
        logger.warning("Router de precedentes multifonte indisponível: %s", exc)


def _patch_advogado_estilo_router() -> None:
    try:
        from app.routers import peca_geracao
        from app.routers import advogado_estilo

        peca_geracao.router.include_router(advogado_estilo.router)
        logger.info("Router de aprendizado de estilo registrado")
    except Exception as exc:  # pragma: no cover
        logger.warning("Router de aprendizado de estilo indisponível: %s", exc)


def _patch_documents_background_analysis() -> None:
    """Substitui o hook legado de análise documental por versão sem corte."""
    try:
        from app.routers import documents as documents_router
    except Exception as exc:  # pragma: no cover
        logger.warning("Patch do hook documental indisponível: %s", exc)
        return

    async def _analisar_doc_bg_sem_corte(case_id: str, ocr_text: str, doc_id: str, user_id: str) -> None:
        try:
            from app.services.analise_estrategica import analisar_caso
            from app.core.database import AsyncSessionLocal
            from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
            from sqlalchemy import text as _sql
            from uuid import uuid4 as _uuid4
            import json as _json

            async with AsyncSessionLocal() as db:
                row = await db.execute(
                    _sql("SELECT titulo, area, numero_processo, client_id FROM cases WHERE id = :id"),
                    {"id": case_id},
                )
                caso = row.fetchone()

                resultado = await analisar_caso(
                    titulo=(caso.titulo if caso else "") or "",
                    area=(caso.area if caso else "") or "",
                    numero_processo=(caso.numero_processo if caso else "") or "",
                    texto_documento=ocr_text,
                    scope_client_id=(caso.client_id if caso else None),
                    case_id=case_id,
                    db=db,
                )

                fontes = None
                if isinstance(resultado, dict) and resultado.get("_fontes_rag"):
                    fontes = _json.dumps(resultado["_fontes_rag"], ensure_ascii=False)[:2000]
                log = AILog(
                    id=str(_uuid4()),
                    user_id=user_id,
                    case_id=case_id,
                    tipo_uso=AITipoUso.analise_caso,
                    modelo="auto-analise-doc",
                    prompt_sanitizado=f"[auto] analise estrategica do documento {doc_id}",
                    resposta=_json.dumps(resultado, ensure_ascii=False)[:8000],
                    fontes_rag=fontes,
                    status_hitl=AIStatusHITL.gerado,
                )
                db.add(log)
                await db.commit()
        except Exception as exc:
            logger.warning("Hook analise doc sem corte falhou: %s", exc)

    documents_router._analisar_doc_bg = _analisar_doc_bg_sem_corte
    logger.info("Hook de análise documental ajustado para OCR completo")


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


_patch_precedentes_router()
_patch_advogado_estilo_router()
_patch_documents_background_analysis()
_install_ai_core_hardening()
_install_datajud_cognitive_feed()


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
