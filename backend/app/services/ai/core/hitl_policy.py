# ── app/services/ai/core/hitl_policy.py ──────────────────────────────────────
# POLÍTICA HITL (Human-In-The-Loop) do Núcleo Único de IA.
#
# Regra OAB/EJC: TODA saída de IA é rascunho. Nenhuma resposta jurídica é
# apresentada como definitiva; o advogado responsável revisa antes de qualquer
# uso. A flag AI_REQUIRE_HITL existe apenas para ambientes de teste — em
# produção permanece True.
from __future__ import annotations

from app.core.config import get_settings

AVISO_HITL = "Rascunho sujeito à revisão humana (HITL obrigatório — OAB)."


def aplicar(resultado: dict) -> dict:
    """Carimba o resultado padronizado do orchestrator como rascunho HITL.

    Mesmo com AI_REQUIRE_HITL=false (testes), `is_rascunho` permanece True —
    o toggle só controla a exigência de revisão formal, nunca o rótulo de
    rascunho (vedação de resposta jurídica 'final' é inegociável)."""
    requer = bool(get_settings().AI_REQUIRE_HITL)
    resultado["is_rascunho"] = True
    resultado["requer_revisao"] = requer or resultado.get("revisao_obrigatoria", False)
    resultado["status_hitl"] = "gerado"
    resultado["aviso_hitl"] = AVISO_HITL
    return resultado
