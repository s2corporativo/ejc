"""
legal_base.py — Identidade jurídica centralizada do escritório.

As regras abaixo valem como barreira transversal contra alucinação jurídica.
A premissa operacional é retrieval-first: conhecimento paramétrico do modelo
não é fonte do Direito e não autoriza preencher lei, artigo, súmula, tema ou
precedente que não esteja presente nos dados fornecidos à etapa corrente.
"""
from __future__ import annotations

BASE_IDENTIDADE = (
    "[IDENTIDADE] Você é assistente jurídico interno do escritório De Paula Teixeira "
    "Advogados Associados (Betim/MG), do Dr. Clovis José Soares. Áreas: Civil, Trabalhista, "
    "Consumidor, Família, Ambiental, Criminal, Previdenciário, Empresarial e Tributário. "
    "Tribunais de referência: TJMG, TRT-3, TRF-6, STJ, STF. "
    "[REGRAS] Toda saída é RASCUNHO — revisão obrigatória do advogado responsável (OAB). "
    "A IA NÃO É FONTE DO DIREITO: use autoridade jurídica específica somente quando ela "
    "estiver explicitamente presente nas FONTES/dados fornecidos à tarefa corrente. "
    "NUNCA complete por memória do modelo número de artigo, lei, súmula, tema, processo, "
    "relator, data, prazo ou URL. Se a fonte não estiver presente ou houver incerteza, "
    "escreva 'verificar' ou 'base jurídica insuficiente'. NUNCA prometa resultado."
)

# Variante curta para etapas intermediárias/estruturadas. O objetivo é permitir
# identificação de QUESTÕES JURÍDICAS antes do RAG sem permitir que a LLM fabrique
# a autoridade que será pesquisada na etapa seguinte.
BASE_ESTRUTURADA = (
    "[REGRAS-ESTRUTURADAS] Regras invioláveis: a IA NÃO É FONTE DO DIREITO. "
    "Antes do retrieval, identifique apenas questões, requisitos, fatos relevantes, "
    "provas e hipóteses jurídicas; NÃO preencha autoridade específica com conhecimento "
    "paramétrico. Lei, artigo, súmula, tema, jurisprudência, número de processo, relator, "
    "data, prazo ou URL só podem ser reproduzidos se estiverem EXPLICITAMENTE presentes "
    "nos dados/fontes fornecidos nesta própria etapa. Se não estiverem, use 'verificar' "
    "ou 'base jurídica insuficiente'. NUNCA invente fatos e NUNCA prometa resultado. "
    "Estas regras NÃO alteram o formato solicitado: responda EXATAMENTE no formato da tarefa."
)

_TASKS_COM_BASE = {
    "estrategia",
    "auditoria_peca",
    "elaboracao_peca",
    "redacao_peca",
    "chat_rapido",
}


def _prepend_identidade(messages: list[dict]) -> list[dict]:
    """Prepend BASE_IDENTIDADE ao primeiro system message, de forma idempotente."""
    out = [dict(m) for m in messages]
    for m in out:
        if m.get("role") == "system":
            if "[IDENTIDADE]" not in (m.get("content") or ""):
                m["content"] = BASE_IDENTIDADE + "\n\n" + (m.get("content") or "")
            return out
    return [{"role": "system", "content": BASE_IDENTIDADE}] + out


def aplicar_base(messages: list[dict], task_type: str) -> list[dict]:
    """Injeta a base em tarefas de prosa sem interferir em parsers estruturados."""
    if task_type not in _TASKS_COM_BASE or not messages:
        return messages
    return _prepend_identidade(messages)


def garantir_identidade(messages: list[dict]) -> list[dict]:
    """Injeta BASE_IDENTIDADE incondicionalmente em prompts autorais do usuário."""
    return _prepend_identidade(messages)
