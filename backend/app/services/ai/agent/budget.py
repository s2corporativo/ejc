# ── app/services/ai/agent/budget.py ──────────────────────────────────────────
# Orçamento do agente: teto de PASSOS e de TOKENS acumulados. Garante que o loop
# NUNCA seja infinito e que o custo por execução seja limitado (controle de gasto
# de IA, alinhado ao teto duro do provider). Acumula os tokens de cada turno.
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentBudget:
    max_steps: int = 8
    max_tokens_total: int = 16000
    passos: int = 0
    tokens_usados: int = 0

    def registrar_turno(self, usage: dict | None) -> None:
        """Contabiliza um turno (passo) e acumula input+output tokens."""
        self.passos += 1
        if usage:
            self.tokens_usados += int(usage.get("input_tokens") or 0)
            self.tokens_usados += int(usage.get("output_tokens") or 0)

    def estourou_passos(self) -> bool:
        return self.passos >= self.max_steps

    def estourou_tokens(self) -> bool:
        return self.tokens_usados >= self.max_tokens_total

    def deve_parar(self) -> bool:
        return self.estourou_passos() or self.estourou_tokens()
