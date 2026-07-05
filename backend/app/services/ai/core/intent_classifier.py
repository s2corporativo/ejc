# ── app/services/ai/core/intent_classifier.py ────────────────────────────────
# CLASSIFICADOR DE INTENÇÃO — 100% determinístico (tabelas + keywords, SEM LLM).
# Resolve (task_type, domain, mensagem) → agente interno + TarefaIA + flags.
# Determinístico de propósito: roteamento auditável, testável e sem custo.
from __future__ import annotations
from dataclasses import dataclass

from app.services.system_prompts import TarefaIA
from app.services.ai.core.agent_registry import AGENT_REGISTRY, AgenteInterno


@dataclass(frozen=True)
class IntentResultado:
    agente: str
    tarefa: TarefaIA
    exige_fonte: bool
    precisa_caso: bool


# task_type/domain (normalizado) → nome do agente. Cobre os aliases usados
# pelos endpoints do núcleo (/chat, /task, /analyze, /generate, /report).
TASK_TYPE_PARA_AGENTE: dict[str, str] = {
    # Casos / estratégia
    "chat": "CaseAgent",
    "case_analysis": "CaseAgent",
    "analise_caso": "CaseAgent",
    "case": "CaseAgent",
    "estrategia": "CaseAgent",
    # Processo / prazos
    "process_analysis": "ProcessAgent",
    "prazos": "ProcessAgent",
    "processo": "ProcessAgent",
    "process": "ProcessAgent",
    # Documentos
    "document_analysis": "DocumentAgent",
    "resumo_documento": "DocumentAgent",
    "ocr": "DocumentAgent",
    "resumo": "DocumentAgent",
    "documento": "DocumentAgent",
    "document": "DocumentAgent",
    # Redação jurídica
    "legal_draft": "LegalWritingAgent",
    "minuta": "LegalWritingAgent",
    "peca": "LegalWritingAgent",
    "redacao_peca": "LegalWritingAgent",
    # Pesquisa jurídica / RAG
    "legal_research": "RAGResearchAgent",
    "rag": "RAGResearchAgent",
    "pesquisa": "RAGResearchAgent",
    "pesquisa_juridica": "RAGResearchAgent",
    "rag_query": "RAGResearchAgent",
    # Jurimetria
    "jurimetria": "JurimetryAgent",
    "predicao": "JurimetryAgent",
    # Financeiro
    "financeiro": "FinanceAgent",
    "honorarios": "FinanceAgent",
    # Bancário
    "bancario": "BankForensicsAgent",
    "extrato": "BankForensicsAgent",
    # Compliance / regulatório / ambiental (agente de caso genérico; a tarefa
    # ambiental é refinada abaixo para usar o prompt/modelo ambiental).
    "compliance": "CaseAgent",
    "regulatorio": "CaseAgent",
    "ambiental": "CaseAgent",
    # Comunicação com cliente
    "mensagem_cliente": "ClientCommunicationAgent",
    "portal": "ClientCommunicationAgent",
    # Técnicos
    "saude_sistema": "SystemHealthAgent",
    "diagnostico": "SystemHealthAgent",
    "reparo": "RepairAgent",
    "patch": "RepairAgent",
    "design": "UIUXAgent",
    "uiux": "UIUXAgent",
    # Segurança / LGPD
    "seguranca": "SecurityLGPDOABAgent",
    "lgpd": "SecurityLGPDOABAgent",
    "auditoria_acesso": "SecurityLGPDOABAgent",
    # Relatórios (domain refina; fallback CaseAgent)
    "report": "CaseAgent",
    "relatorio": "CaseAgent",
}

# Fallback por keywords na MENSAGEM (ordem importa: mais específico primeiro).
_KEYWORDS_PARA_AGENTE: list[tuple[tuple[str, ...], str]] = [
    (("extrato", "tarifa bancária", "busca e apreensão", "revisional"), "BankForensicsAgent"),
    (("ambiental", "auto de infração ambiental", "licenciamento", "compliance", "regulatório", "regulatorio"), "CaseAgent"),
    (("lgpd", "dado pessoal", "vazamento", "auditoria de acesso"), "SecurityLGPDOABAgent"),
    (("jurimetria", "probabilidade", "predição", "predicao"), "JurimetryAgent"),
    (("honorário", "honorario", "contrato de honorários"), "FinanceAgent"),
    (("minuta", "petição", "peticao", "peça", "peca processual", "redigir", "redija"), "LegalWritingAgent"),
    (("jurisprudência", "jurisprudencia", "súmula", "sumula", "precedente", "pesquis"), "RAGResearchAgent"),
    (("prazo", "intimação", "intimacao", "audiência", "audiencia", "andamento"), "ProcessAgent"),
    (("resumir", "resumo do documento", "documento anexo", "ocr"), "DocumentAgent"),
    (("mensagem para o cliente", "comunicar o cliente", "informar o cliente"), "ClientCommunicationAgent"),
    (("diagnóstico do sistema", "diagnostico do sistema", "saúde do sistema", "saude do sistema"), "SystemHealthAgent"),
]

# Agentes cujo trabalho normalmente depende de um caso concreto.
_AGENTES_COM_CASO = {"CaseAgent", "ProcessAgent", "FinanceAgent", "BankForensicsAgent"}


def _normalizar(valor: str | None) -> str:
    return (valor or "").strip().lower().replace("-", "_").replace(" ", "_")


def _agente_por_chave(chave: str) -> str | None:
    """Lookup direto + variação sem sufixo '_analysis' (ex.: bancario_analysis)."""
    if not chave:
        return None
    if chave in TASK_TYPE_PARA_AGENTE:
        return TASK_TYPE_PARA_AGENTE[chave]
    if chave.endswith("_analysis"):
        return TASK_TYPE_PARA_AGENTE.get(chave[: -len("_analysis")])
    return None


def classify_intent(
    task_type: str,
    domain: str | None = None,
    mensagem: str = "",
) -> IntentResultado:
    """
    Resolve o agente responsável e a TarefaIA correspondente.

    Ordem de resolução: task_type → domain → keywords da mensagem →
    default (CaseAgent / analise_caso). Nunca falha — sempre roteia.
    """
    task = _normalizar(task_type)
    dom = _normalizar(domain)

    nome_agente = _agente_por_chave(task)
    # "report" genérico: o domain decide o especialista (report jurídico ≠ técnico).
    if task in ("report", "relatorio") and dom:
        nome_agente = _agente_por_chave(dom) or nome_agente
    if nome_agente is None:
        nome_agente = _agente_por_chave(dom)
    if nome_agente is None:
        msg = (mensagem or "").lower()
        for palavras, agente in _KEYWORDS_PARA_AGENTE:
            if any(p in msg for p in palavras):
                nome_agente = agente
                break
    if nome_agente is None:
        nome_agente = "CaseAgent"

    agente: AgenteInterno = AGENT_REGISTRY[nome_agente]

    # Ajuste fino da tarefa: domain "ambiental" usa o prompt/modelo ambiental.
    tarefa = agente.tarefa_padrao
    if "ambiental" in (task, dom):
        tarefa = TarefaIA.AMBIENTAL

    return IntentResultado(
        agente=nome_agente,
        tarefa=tarefa,
        exige_fonte=agente.exige_fonte,
        precisa_caso=nome_agente in _AGENTES_COM_CASO,
    )
