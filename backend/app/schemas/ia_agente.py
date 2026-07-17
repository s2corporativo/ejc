# ── app/schemas/ia_agente.py ─────────────────────────────────────────────────
# Contrato de entrada do MÓDULO AGÊNTICO DE IA (POST /ia/agente/stream).
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class AgenteStreamRequest(BaseModel):
    case_id: str = Field(..., max_length=64,
                         description="Caso em contexto (RBAC/ownership re-checado no loop e em cada tool).")
    # `mensagem` é obrigatória no INÍCIO; opcional numa RETOMADA (retomar_token).
    mensagem: str | None = Field(
        default=None, max_length=20_000,
        description="Instrução/pergunta do advogado ao agente (obrigatória no início).")
    # ── HITL vinculado aos ARGS (achado H1) ──────────────────────────────────
    # Ao pausar numa write-tool, o servidor devolve {token, args_hash}. O cliente
    # retoma com retomar_token + decisao (caminho Redis, sem re-run) OU, se o
    # Redis estiver indisponível (token=None), reenvia a mensagem com o
    # aprovacoes_hash do tool_call que aprovou (fallback: só executa se casar).
    retomar_token: str | None = Field(
        default=None, max_length=128,
        description="Token opaco devolvido no evento confirmacao_requerida (retoma o estado no Redis).")
    decisao: str | None = Field(
        default=None, pattern="^(aprovar|recusar)$",
        description="Decisão humana na retomada: 'aprovar' executa exatamente o tool_call pendente; 'recusar' segue sem executar.")
    aprovacoes_hash: list[str] = Field(
        default_factory=list, max_length=32,
        description="Hashes de (nome+args) de write-tools aprovadas — FALLBACK usado quando o Redis está indisponível.")

    @model_validator(mode="after")
    def _exige_mensagem_ou_retomada(self):
        if not self.retomar_token and not (self.mensagem and self.mensagem.strip()):
            raise ValueError("Informe `mensagem` (início) ou `retomar_token` (retomada).")
        if self.retomar_token and not self.decisao:
            raise ValueError("Na retomada, informe `decisao` ('aprovar' ou 'recusar').")
        return self
