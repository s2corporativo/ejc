"""Feature flags das integrações externas adicionadas na Issue #836.

Regra do EJC: integração externa nova nasce opt-in/default OFF e deve poder ser
interrompida sem alterar código. A leitura é feita a cada chamada para que o
mesmo contrato seja reutilizável por rotas e jobs.
"""
from __future__ import annotations

import os

from fastapi import HTTPException

_TRUE = frozenset({"1", "true", "yes", "on", "sim"})

FLAGS: dict[str, str] = {
    "cnj_sgt": "CNJ_SGT_ENABLED",
    "tcu": "TCU_OPEN_DATA_ENABLED",
    "ibge": "IBGE_LOCALIDADES_ENABLED",
    "ibama": "IBAMA_OPEN_DATA_ENABLED",
    "mj": "CONSUMIDOR_GOV_OPEN_DATA_ENABLED",
    "cvm": "CVM_OPEN_DATA_ENABLED",
    "tse": "TSE_OPEN_DATA_ENABLED",
    "pgfn": "PGFN_OPEN_DATA_ENABLED",
    "querido_diario": "QUERIDO_DIARIO_ENABLED",
    "ide_sisema": "IDE_SISEMA_ENABLED",
    # Jurimetria dos tribunais (Issue #1527): consulta agregada ao DataJud.
    # Exige também DATAJUD_ENABLED/DATAJUD_API_KEY — é uma leitura a mais da
    # mesma integração, com o próprio interruptor.
    "jurimetria_tribunais": "JURIMETRIA_TRIBUNAIS_ENABLED",
}


def enabled(source: str) -> bool:
    """Retorna False para flag ausente, desconhecida ou valor não afirmativo."""
    env_name = FLAGS.get(source)
    if not env_name:
        return False
    return os.getenv(env_name, "").strip().casefold() in _TRUE


def require_enabled(source: str, label: str) -> None:
    """Interrompe antes de qualquer I/O externo com resposta controlada 503.

    ``HTTPException`` é deliberada: nas rotas FastAPI ela preserva o 503 sem
    virar 502 genérico; em jobs internos continua sendo uma exceção rastreável,
    fazendo a execução ser marcada como erro em vez de falso sucesso vazio.
    """
    if enabled(source):
        return
    env_name = FLAGS.get(source, "FEATURE_FLAG")
    raise HTTPException(
        status_code=503,
        detail=f"Integração {label} desabilitada por configuração ({env_name}).",
    )
