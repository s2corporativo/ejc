# ── app/schemas/ia_agente.py ─────────────────────────────────────────────────
# Contrato de entrada do MÓDULO AGÊNTICO DE IA (POST /ia/agente/stream).
from __future__ import annotations

from pydantic import BaseModel, Field


class AgenteStreamRequest(BaseModel):
    case_id: str = Field(..., max_length=64,
                         description="Caso em contexto (RBAC/ownership re-checado no loop e em cada tool).")
    mensagem: str = Field(..., min_length=1, max_length=20_000,
                          description="Instrução/pergunta do advogado ao agente.")
    ferramentas_aprovadas: list[str] = Field(
        default_factory=list, max_length=32,
        description="Nomes de ferramentas de ESCRITA já aprovadas pelo humano (HITL). "
                    "Vazio no primeiro turno; ao confirmar, o cliente re-invoca com a "
                    "ferramenta pendente incluída aqui.",
    )
