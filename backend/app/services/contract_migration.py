"""Compatibilidade e telemetria da migração de contratos da IA.

A migração é observável antes de qualquer remoção de rota. Os headers não
contêm dados pessoais e permitem ao gateway/frontend identificar a versão
recebida. O log estruturado registra apenas rota, contrato e modo legado.
"""
from __future__ import annotations

import logging
from typing import Any

from starlette.responses import Response

logger = logging.getLogger("ejc.contract_migration")

CANONICAL_CONTRACT = "case_intelligence.v1"
LEGACY_ADAPTER_CONTRACT = "legacy-adapter"
DEPRECATION_DOC = "/docs/migracao-contratos-ia"


def mark_contract_response(response: Response | None, *, route: str,
                           legacy_adapter: bool = False,
                           sunset: str | None = None) -> None:
    """Marca uma resposta sem alterar o corpo nem quebrar clientes antigos."""
    # Testes/consumidores internos podem chamar o router diretamente, sem o
    # ciclo de injeção FastAPI. Nessa situação a telemetria corporal continua
    # ativa e o header simplesmente não é aplicável.
    if response is None or not hasattr(response, "headers"):
        logger.info(
            "contract_usage route=%s contract=%s legacy_adapter=%s response_headers=false",
            route, CANONICAL_CONTRACT, str(legacy_adapter).lower(),
        )
        return
    response.headers["X-Contract-Version"] = CANONICAL_CONTRACT
    response.headers["X-Contract-Adapter"] = (
        LEGACY_ADAPTER_CONTRACT if legacy_adapter else CANONICAL_CONTRACT
    )
    if legacy_adapter:
        response.headers["Deprecation"] = "true"
        response.headers["Link"] = f"<{DEPRECATION_DOC}>; rel=\"deprecation\""
        if sunset:
            response.headers["Sunset"] = sunset
    logger.info(
        "contract_usage route=%s contract=%s legacy_adapter=%s",
        route, CANONICAL_CONTRACT, str(legacy_adapter).lower(),
    )


def mark_payload(payload: dict[str, Any], *, route: str,
                 legacy_adapter: bool = False) -> dict[str, Any]:
    """Carimba respostas armazenadas/logadas sem incluir PII."""
    if not isinstance(payload, dict):
        return payload
    payload.setdefault("contract_version", CANONICAL_CONTRACT)
    payload.setdefault("contract_legacy_adapter", legacy_adapter)
    logger.info(
        "contract_usage route=%s contract=%s legacy_adapter=%s",
        route, CANONICAL_CONTRACT, str(legacy_adapter).lower(),
    )
    return payload
