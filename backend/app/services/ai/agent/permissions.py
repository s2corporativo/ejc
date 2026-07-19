# ── app/services/ai/agent/permissions.py ─────────────────────────────────────
# Visibilidade e política de confirmação das ferramentas do agente.
#   • LEITURA  → automática (sem confirmação).
#   • ESCRITA  → exige confirmação humana (HITL) antes de executar.
# A fonte de verdade é o REGISTRY (cada tool declara requer_confirmacao/roles);
# estes helpers são a fachada consultada pelo loop e pelo router.
from __future__ import annotations

from app.services.ai.agent.tools.registry import REGISTRY


def pode_ver_tool(tool: str, role: str) -> bool:
    """True se o papel `role` pode ver/usar a ferramenta `tool`."""
    return tool in REGISTRY.nomes_visiveis(role)


def requer_confirmacao(tool: str) -> bool:
    """True se `tool` é de ESCRITA (precisa de aprovação humana antes de rodar)."""
    return REGISTRY.requer_confirmacao(tool)
