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

# Tipos "públicos" que o cliente pode ser avisado (sem 'peticao', que é
# estratégia/produção interna, e sem 'ia'/notas internas).
_TIPOS_PUBLICOS_CLIENTE = {"intimacao", "decisao", "audiencia", "movimento"}


def _patch_precedentes_router() -> None:
    """Registra subrouter de precedentes sem reescrever o router grande.

    O `main.py` já inclui `jurisprudencia_externa.router` em `/api`. Ao anexar o
    subrouter aqui, antes do include principal, o endpoint fica disponível em:
    `/api/jurisprudencia-externa/precedentes/buscar`.
    """
    try:
        from app.routers import jurisprudencia_externa
        from app.routers import precedentes_jurisprudencia

        jurisprudencia_externa.router.include_router(precedentes_jurisprudencia.router)
        logger.info("Router de precedentes multifonte registrado")
    except Exception as exc:  # pragma: no cover - import defensivo no startup
        logger.warning("Router de precedentes multifonte indisponível: %s", exc)


def _patch_documents_background_analysis() -> None:
    """Substitui o hook legado de análise documental por versão sem corte.

    Correção P1: o router de documentos mantinha compatibilidade legada no hook
    de background e enviava apenas o prefixo do OCR para `analisar_caso`. Aqui o
    hook é substituído, no carregamento do app, por uma implementação equivalente
    que entrega o OCR completo ao pipeline moderno. O `analisar_caso` já monta
    dossiê documental para textos longos, então o envio completo não sobrecarrega
    o prompt e evita perda de fatos, pedidos, provas, prazos e teses.
    """
    try:
        from app.routers import documents as documents_router
    except Exception as exc:  # pragma: no cover - import defensivo no startup
        logger.warning("Patch do hook documental indisponível: %s", exc)
        return

    async def _analisar_doc_bg_sem_corte(case_id: str, ocr_text: str, doc_id: str, user_id: str) -> None:
        """Dispara análise estratégica usando OCR completo, sem truncamento."""
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


_patch_precedentes_router()
_patch_documents_background_analysis()


@on("movimento.criado")
async def _traduzir_andamento(db, entidade_id, payload):
    """Ao registrar um andamento oficial, gera o resumo em linguagem simples (IA).
    Notas internas e itens 'ia' são ignorados (não precisam de tradução)."""
    tipo = (payload or {}).get("tipo", "")
    if tipo not in _TRADUZ_TIPOS:
        return
    from app.services.movimento_ia import traduzir_movimento
    await traduzir_movimento(db, entidade_id)


@on("movimento.criado")
async def _notificar_cliente_movimento(db, entidade_id, payload):
    """Avisa o cliente (portal) quando há um novo andamento público no caso.

    LGPD/segurança: a notificação é GENÉRICA por design. NUNCA carrega teor do
    andamento, PII, estratégia ou conteúdo interno — apenas um aviso de que houve
    atualização, com a referência mínima do número interno do caso (quando houver).
    Notas internas e itens 'ia'/'peticao' são ignorados.
    """
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
