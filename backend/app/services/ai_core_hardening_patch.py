# ── app/services/ai_core_hardening_patch.py ──────────────────────────────────
"""Hardening aditivo do núcleo de IA/RAG carregado no startup.

Correções transitórias de compatibilidade:
1. conexão do ProviderRegistry único ao runtime;
2. resolução de provedores fail-closed para todos os aliases legados de `chat`;
3. resolução server-side do escopo de precedentes de encerramento cuja chave
   canônica é `caso:<id>`, fluxo legado que não passava client_id ao RAG;
4. listagem de KnowledgeDoc escopada, evitando exposição de títulos/fontes de
   peças internas a usuários sem acesso ao caso ou cliente correspondente.

As correções operam em primitivas consultadas em runtime, alcançando call sites
que importaram funções antes do startup. A convergência definitiva deve eliminar
os adapters ao centralizar contratos de provider, ingestão e ownership.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("ejc.ai.core.hardening")
_INSTALADO = False


def _instalar_provider_registry() -> None:
    """Conecta a fonte única de providers antes de instalar o fail-closed."""
    from app.services.ai.provider_registry_runtime import instalar
    instalar()


def _instalar_resolver_provedores() -> None:
    from app.services import ai_gateway

    if getattr(ai_gateway, "_ejc_fail_closed_resolver_installed", False):
        return

    original = ai_gateway._resolver_cadeia

    def resolver_fail_closed(
        task_type: str,
        provider_force: str | None,
        model_override: str | None,
        provider_preferido: str | None = None,
        model_preferido: str | None = None,
    ) -> list[tuple[str, str | None]]:
        cadeia = original(
            task_type,
            provider_force,
            model_override,
            provider_preferido,
            model_preferido,
        )
        seguros = [
            (provider, model)
            for provider, model in cadeia
            if ai_gateway._provider_elegivel(provider)
        ]
        if cadeia and not seguros:
            logger.warning(
                "Cadeia de IA esvaziada pelo gate de elegibilidade "
                "(task=%s); nenhum provider será chamado.",
                task_type,
            )
        return seguros

    ai_gateway._resolver_cadeia = resolver_fail_closed
    ai_gateway._ejc_fail_closed_resolver_installed = True


def _instalar_resolucao_escopo_rag() -> None:
    """Compatibiliza o encerramento legado sem aceitar escopo do cliente.

    `cases.encerrar_caso` usa chave `caso:<uuid>` e import local da função; a
    identidade do caso é, portanto, verificável no servidor. Somente esse padrão
    canônico pode ser auto-resolvido. Qualquer outra categoria/chave sem client_id
    continua bloqueada pelo write gate de `ingestion_service`.
    """
    from app.services import ingestion_service

    if getattr(ingestion_service, "_ejc_scope_resolver_installed", False):
        return

    original = ingestion_service.upsert_documento

    async def upsert_com_escopo_canonico(db, **kwargs):
        categoria = kwargs.get("categoria")
        client_id = kwargs.get("client_id")
        chave = str(kwargs.get("chave_origem") or "")
        if categoria == "precedente_interno" and not client_id and chave.startswith("caso:"):
            case_id = chave.removeprefix("caso:").strip()
            if case_id:
                from app.models.case import Case
                case = await db.get(Case, case_id)
                if case is not None and case.deleted_at is None and case.client_id:
                    kwargs["client_id"] = str(case.client_id)
                    kwargs["case_id"] = str(case.id)
                    logger.info(
                        "Escopo RAG resolvido pelo caso canônico %s para precedente interno",
                        getattr(case, "numero_interno", None) or case.id,
                    )
        return await original(db, **kwargs)

    ingestion_service.upsert_documento = upsert_com_escopo_canonico
    ingestion_service._ejc_scope_resolver_installed = True


async def _listar_docs_escopado(
    page: int = 1,
    page_size: int = 20,
    categoria: str | None = None,
    db=None,
    cu=None,
):
    """Contrato seguro de GET /rag/docs.

    Gestão (sócio+) mantém visão integral para curadoria. Demais usuários veem:
    conteúdo público; conteúdo do próprio cliente externo; e documentos ligados
    a casos nos quais são responsável/auxiliar ou que permanecem sem atribuição,
    exatamente conforme a salvaguarda do ownership canônico.
    """
    from sqlalchemy import and_, func as sqlfunc, or_, select
    from app.core.ownership import is_gestao
    from app.models.case import Case
    from app.models.rag import KnowledgeDoc

    q = select(KnowledgeDoc).where(KnowledgeDoc.deleted_at.is_(None))
    if not is_gestao(cu):
        visibilidade = [KnowledgeDoc.client_id.is_(None)]
        client_id = getattr(cu, "client_id", None)
        if client_id:
            visibilidade.append(KnowledgeDoc.client_id == client_id)

        casos_permitidos = select(Case.id).where(
            Case.deleted_at.is_(None),
            or_(
                Case.advogado_responsavel_id == getattr(cu, "id", None),
                Case.advogado_auxiliar_id == getattr(cu, "id", None),
                and_(
                    Case.advogado_responsavel_id.is_(None),
                    Case.advogado_auxiliar_id.is_(None),
                ),
            ),
        )
        visibilidade.append(KnowledgeDoc.case_id.in_(casos_permitidos))
        q = q.where(or_(*visibilidade))

    if categoria:
        q = q.where(KnowledgeDoc.categoria == categoria)
    q = q.order_by(KnowledgeDoc.created_at.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar() or 0
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [
            {
                "id": d.id,
                "titulo": d.titulo,
                "categoria": d.categoria,
                "fonte": d.fonte,
                "tribunal": d.tribunal,
                "status_indexacao": d.status_indexacao,
                "created_at": d.created_at,
            }
            for d in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _instalar_listagem_rag_escopada() -> None:
    """Substitui o callable da rota antes de o router ser incluído no FastAPI."""
    from app.routers import rag

    if getattr(rag.router, "_ejc_docs_scope_installed", False):
        return

    encontrada = False
    for route in rag.router.routes:
        if getattr(route, "name", "") == "listar_docs":
            route.endpoint = _listar_docs_escopado
            route.dependant.call = _listar_docs_escopado
            encontrada = True
            break
    if not encontrada:
        raise RuntimeError("Rota listar_docs do RAG não localizada para hardening")

    setattr(rag.router, "_ejc_docs_scope_installed", True)
    logger.info("Listagem de KnowledgeDoc protegida por escopo de acesso")


def instalar() -> None:
    global _INSTALADO
    if _INSTALADO:
        return
    _instalar_provider_registry()
    _instalar_resolver_provedores()
    _instalar_resolucao_escopo_rag()
    _instalar_listagem_rag_escopada()
    _INSTALADO = True
    logger.info("Hardening do núcleo de IA/RAG instalado")
