# ── app/services/ai_core_hardening_patch.py ──────────────────────────────────
"""Hardening aditivo do AI Gateway carregado no startup.

O gateway possui inúmeros call sites legados que importaram ``chat`` por
referência. Alterar apenas o símbolo público não alcançaria esses chamadores.
Este instalador corrige a primitiva interna ``_resolver_cadeia`` — consultada em
runtime por qualquer referência de ``chat`` — para que um kill-switch ou falta
de credencial nunca seja contornado por fallback sintético ao Groq.

É patch transitório e pequeno. A convergência definitiva deve mover a resolução
para um registro único de provedores, eliminando a duplicação entre
``AIProviderPolicy`` e ``ai_gateway``.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("ejc.ai.core.hardening")
_INSTALADO = False


def instalar() -> None:
    global _INSTALADO
    if _INSTALADO:
        return

    from app.services import ai_gateway

    if getattr(ai_gateway, "_ejc_fail_closed_resolver_installed", False):
        _INSTALADO = True
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
        # O legado sintetizava [("groq", ...)] quando nenhum candidato era
        # elegível. Isso podia ignorar AI_EXTERNAL_PROVIDERS_ALLOWED=false e
        # tentar rede externa mesmo com o kill-switch acionado. Filtrar aqui é
        # a última defesa comum a TODOS os call sites, inclusive referências
        # antigas de `chat` importadas antes do startup patch.
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
    _INSTALADO = True
    logger.info("AI Gateway protegido por resolução fail-closed de provedores")
