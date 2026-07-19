# ── app/services/ai_core_hardening_patch.py ──────────────────────────────────
"""Hardening aditivo do núcleo de IA/RAG carregado no startup.

Duas correções transitórias de compatibilidade:
1. resolução de provedores fail-closed para todos os aliases legados de `chat`;
2. resolução server-side do escopo de precedentes de encerramento cuja chave
   canônica é `caso:<id>`, fluxo legado que não passava client_id ao RAG.

As duas correções operam em primitivas consultadas em runtime, alcançando call
sites que importaram funções antes do startup. A convergência definitiva deve
eliminar os patches ao centralizar provider registry e contratos de ingestão.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("ejc.ai.core.hardening")
_INSTALADO = False


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


def instalar() -> None:
    global _INSTALADO
    if _INSTALADO:
        return
    _instalar_resolver_provedores()
    _instalar_resolucao_escopo_rag()
    _INSTALADO = True
    logger.info("Hardening do núcleo de IA/RAG instalado")
