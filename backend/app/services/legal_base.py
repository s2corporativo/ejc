"""
legal_base.py — Identidade jurídica centralizada do escritório (#8).

Fonte ÚNICA da identidade do escritório e do padrão de apresentação jurídica,
injetada no system prompt das tarefas de PROSA jurídica via ai_gateway. NÃO
injeta em tarefas de saída estruturada (analise_juridica = JSON de extração) nem
em 'resumo', para não interferir no formato esperado. Aditivo e idempotente.
"""
from __future__ import annotations

BASE_IDENTIDADE = (
    "[IDENTIDADE] Você atua como assistente jurídico interno do escritório De Paula Teixeira "
    "Advogados Associados (Betim/MG), do Dr. Clovis José Soares. Áreas: Civil, Trabalhista, "
    "Consumidor, Família, Ambiental, Criminal, Previdenciário, Empresarial e Tributário. "
    "Tribunais de referência: TJMG, TRT-3, TRF-6, STJ, STF. "
    "[PADRAO_DE_APRESENTACAO] Apresente suas respostas como um advogado experiente faria: "
    "com linguagem técnica, postura profissional, raciocínio jurídico organizado, indicação "
    "de tese, fundamento, prova, risco, estratégia, providência prática e conclusão objetiva. "
    "Quando elaborar peças, minutas, propostas, comunicações, pareceres, estimativas ou planos, "
    "entregue o texto em formato profissional pronto para revisão e uso pelo escritório. "
    "Diferencie fatos confirmados, inferências técnicas, lacunas documentais e pontos a verificar. "
    "Não invente lei, súmula, jurisprudência, número de processo, documento, dado financeiro ou fato; "
    "quando a base não permitir conclusão segura, marque o ponto como 'verificar'."
)

# Apenas tarefas de PROSA recebem a base — exclui JSON (analise_juridica) e resumo.
_TASKS_COM_BASE = {
    "estrategia",
    "auditoria_peca",
    "elaboracao_peca",
    "redacao_peca",
    "chat_rapido",
}


def _prepend_identidade(messages: list[dict]) -> list[dict]:
    """Prepend BASE_IDENTIDADE ao 1º system message (cria um se não houver).
    Idempotente: detecta [IDENTIDADE] e não duplica."""
    out = [dict(m) for m in messages]
    for m in out:
        if m.get("role") == "system":
            if "[IDENTIDADE]" not in (m.get("content") or ""):
                m["content"] = BASE_IDENTIDADE + "\n\n" + (m.get("content") or "")
            return out
    return [{"role": "system", "content": BASE_IDENTIDADE}] + out


def aplicar_base(messages: list[dict], task_type: str) -> list[dict]:
    """Prepend a identidade do escritório ao system message (tarefas de prosa).
    Gated por task_type: exclui JSON de extração (analise_juridica) e resumo."""
    if task_type not in _TASKS_COM_BASE or not messages:
        return messages
    return _prepend_identidade(messages)


def garantir_identidade(messages: list[dict]) -> list[dict]:
    """Injeta BASE_IDENTIDADE INCONDICIONALMENTE (independe de task_type).

    Para canais de prompt AUTORAIS DO USUÁRIO — skills configuráveis no banco
    (EjcSkill) e biblioteca de prompts (PromptJuridico). Esses prompts não
    passam pela curadoria de código e seu task_type pode não estar em
    _TASKS_COM_BASE, então aplicar_base não aplicaria o padrão central de
    apresentação jurídica. Aqui a política é obrigatória e idempotente.

    DECISÃO EXPLÍCITA (vs. a exclusão de analise_juridica/resumo em
    _TASKS_COM_BASE): a exclusão foi desenhada para o path de EXTRAÇÃO-JSON do
    gateway (executar_tarefa_ia), cujo consumidor faz parse. Estes canais
    devolvem PROSA crua ao usuário, então injetar a identidade é seguro e
    intencional: o padrão central prevalece sobre a preservação de formato.
    """
    return _prepend_identidade(messages)
