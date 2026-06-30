"""
legal_base.py — Identidade jurídica centralizada do escritório (#8).

Fonte ÚNICA da identidade do escritório + regras invioláveis, injetada no system
prompt das tarefas de PROSA jurídica via ai_gateway. NÃO injeta em tarefas de
saída estruturada (analise_juridica = JSON de extração) nem em 'resumo', para não
interferir no formato esperado. Aditivo e idempotente (não duplica se já presente).
"""
from __future__ import annotations

BASE_IDENTIDADE = (
    "[IDENTIDADE] Você é assistente jurídico interno do escritório De Paula Teixeira "
    "Advogados Associados (Betim/MG), do Dr. Clovis José Soares. Áreas: Civil, Trabalhista, "
    "Consumidor, Família, Ambiental, Criminal, Previdenciário, Empresarial e Tributário. "
    "Tribunais de referência: TJMG, TRT-3, TRF-6, STJ, STF. "
    "[REGRAS] Toda saída é RASCUNHO — revisão obrigatória do advogado responsável (OAB). "
    "NUNCA invente lei, súmula, jurisprudência ou número de processo (se incerto, escreva "
    "'verificar'). NUNCA prometa resultado."
)

# Apenas tarefas de PROSA recebem a base — exclui JSON (analise_juridica) e resumo.
_TASKS_COM_BASE = {"estrategia", "auditoria_peca", "elaboracao_peca"}


def aplicar_base(messages: list[dict], task_type: str) -> list[dict]:
    """Prepend a identidade do escritório ao system message (tarefas de prosa)."""
    if task_type not in _TASKS_COM_BASE or not messages:
        return messages
    out = [dict(m) for m in messages]
    for m in out:
        if m.get("role") == "system":
            if "[IDENTIDADE]" not in (m.get("content") or ""):
                m["content"] = BASE_IDENTIDADE + "\n\n" + (m.get("content") or "")
            return out
    return [{"role": "system", "content": BASE_IDENTIDADE}] + out
