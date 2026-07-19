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

# Variante CURTA para tarefas de SAÍDA ESTRUTURADA (JSON/listas parseadas):
# carrega o núcleo anti-alucinação SEM interferir no formato de saída. Pensada
# para prepend direto no system prompt de etapas intermediárias de pipeline
# (ex.: peca_service etapas 1, 2, 5 e 6), cujos textos alimentam a peça final.
# NÃO contém chaves, cercas de código nem instrução de formato própria — apenas
# reforça que o formato pedido pelo prompt da etapa deve ser respeitado, para
# não poluir/quebrar parsers (_parse_json/_parse_itens/_tipo_identificado).
BASE_ESTRUTURADA = (
    "[REGRAS-ESTRUTURADAS] Regras invioláveis (OAB): NUNCA invente lei, súmula, "
    "jurisprudência, número de processo, datas, prazos ou fatos — se a informação "
    "não constar dos dados fornecidos ou houver incerteza, diga explicitamente "
    "que não sabe (escreva 'verificar'). NUNCA prometa resultado. Estas regras "
    "NÃO alteram o formato de saída: responda EXATAMENTE no formato solicitado "
    "pela tarefa, sem texto fora do formato pedido."
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
    _TASKS_COM_BASE, então aplicar_base os deixaria SEM a barreira
    anti-alucinação (regra OAB). Aqui a barreira é obrigatória e idempotente.

    DECISÃO EXPLÍCITA (vs. a exclusão de analise_juridica/resumo em
    _TASKS_COM_BASE): a exclusão foi desenhada para o path de EXTRAÇÃO-JSON do
    gateway (executar_tarefa_ia), cujo consumidor faz parse. Estes canais
    devolvem PROSA crua (resp.texto) ao usuário como RASCUNHO — nunca são
    parseados como JSON —, então injetar a identidade é seguro e intencional:
    a barreira anti-alucinação prevalece sobre a preservação de formato."""
    return _prepend_identidade(messages)
