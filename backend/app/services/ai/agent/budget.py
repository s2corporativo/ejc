# ── app/services/ai/agent/budget.py ──────────────────────────────────────────
# Orçamento do agente: teto de PASSOS, de TOKENS acumulados e de CUSTO (R$).
# Garante que o loop NUNCA seja infinito e que o gasto por execução seja limitado
# (controle de custo de IA, alinhado ao teto duro do provider). Acumula tokens e
# custo de cada turno.
#
# É a FONTE ÚNICA do limite de passos do loop: rodar_agente itera enquanto
# `not deve_parar()` e chama `registrar_turno`/`registrar_custo` a cada passo
# (achado L6 — não há mais contagem de passos paralela e morta).
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentBudget:
    max_steps: int = 8
    max_tokens_total: int = 120000
    max_custo_brl: float = 2.00
    passos: int = 0
    tokens_usados: int = 0
    custo_acumulado: float = 0.0

    def registrar_turno(self, usage: dict | None) -> None:
        """Contabiliza um turno (passo) e acumula input+output tokens."""
        self.passos += 1
        if usage:
            self.tokens_usados += int(usage.get("input_tokens") or 0)
            self.tokens_usados += int(usage.get("output_tokens") or 0)

    def registrar_custo(self, custo_brl: float) -> None:
        """Acumula o custo estimado (R$) do turno (Sugestão 2 — teto de gasto)."""
        self.custo_acumulado += float(custo_brl or 0.0)

    def estourou_passos(self) -> bool:
        return self.passos >= self.max_steps

    def estourou_tokens(self) -> bool:
        return self.tokens_usados >= self.max_tokens_total

    def estourou_custo(self) -> bool:
        return self.max_custo_brl > 0 and self.custo_acumulado >= self.max_custo_brl

    def deve_parar(self) -> bool:
        """Condição ÚNICA de parada do loop: passos, tokens OU custo estourados."""
        return self.estourou_passos() or self.estourou_tokens() or self.estourou_custo()

    def motivo_parada(self) -> str | None:
        """Texto do aviso de parada por orçamento (None se ainda há folga)."""
        if self.estourou_passos():
            return f"Parada por teto de passos do agente ({self.max_steps})."
        if self.estourou_tokens():
            return ("Parada por teto de tokens do agente "
                    f"({self.tokens_usados}/{self.max_tokens_total}).")
        if self.estourou_custo():
            return ("Parada por teto de custo do agente "
                    f"(R$ {self.custo_acumulado:.4f}/R$ {self.max_custo_brl:.2f}).")
        return None
