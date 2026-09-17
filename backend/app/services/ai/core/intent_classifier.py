# ── app/services/ai/core/intent_classifier.py ────────────────────────────────
# CLASSIFICADOR DE INTENÇÃO — 100% determinístico (tabelas + keywords, SEM LLM).
# Resolve (task_type, domain, mensagem) → agente interno + TarefaIA + flags.
# Determinístico de propósito: roteamento auditável, testável e sem custo.
from __future__ import annotations
import re
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
    # Coordenação nativa do EJC
    "ejc": "EJCCoordinatorAgent",
    "coordenacao": "EJCCoordinatorAgent",
    "modulo": "EJCCoordinatorAgent",
    # Casos / estratégia
    "chat": "CaseAgent",
    "case_analysis": "CaseAgent",
    "analise_caso": "CaseAgent",
    "case": "CaseAgent",
    "estrategia": "CaseAgent",
    # Funções jurídicas transversais
    "provas": "EvidenceAgent",
    "evidencias": "EvidenceAgent",
    "lacunas_probatorias": "EvidenceAgent",
    "onus_prova": "EvidenceAgent",
    "revisao_judicial": "JudicialReviewAgent",
    "perspectiva_magistrado": "JudicialReviewAgent",
    "analise_judicial": "JudicialReviewAgent",
    # Processo / prazos
    "process_analysis": "ProcessAgent",
    "prazos": "ProcessAgent",
    "processo": "ProcessAgent",
    "process": "ProcessAgent",
    # Documentos
    "document_analysis": "DocumentAgent",
    # Extração estruturada (JSON) de pacote documental — orçamento de DOSSIÊ.
    "document_extraction": "DocumentExtractionAgent",
    "extracao_documental": "DocumentExtractionAgent",
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
    # Áreas jurídicas com agente dedicado
    "consumidor": "ConsumerLawAgent",
    "cdc": "ConsumerLawAgent",
    "tributario": "TaxLawAgent",
    "fiscal": "TaxLawAgent",
    "execucao_fiscal": "TaxLawAgent",
    "empresarial": "CorporateLawAgent",
    "societario": "CorporateLawAgent",
    "recuperacao_judicial": "CorporateLawAgent",
    # Agronegócio: matéria comercial (CorporateLawAgent), sem agente dedicado
    # desde a consolidação 38→8 (2026-09-06, escopo definido pelo titular).
    "agronegocio": "CorporateLawAgent",
    "cpr": "CorporateLawAgent",
    "credito_rural": "CorporateLawAgent",
    "trabalhista": "LaborLawAgent",
    "clt": "LaborLawAgent",
    "verbas_rescisorias": "LaborLawAgent",
    "criminal": "CriminalLawAgent",
    "penal": "CriminalLawAgent",
    "administrativo": "AdministrativeLawAgent",
    "improbidade": "AdministrativeLawAgent",
    "processo_administrativo": "AdministrativeLawAgent",
    "juizados": "SpecialCourtsAgent",
    "juizado_especial": "SpecialCourtsAgent",
    "jec": "SpecialCourtsAgent",
    "jef": "SpecialCourtsAgent",
    "jefp": "SpecialCourtsAgent",
    "civel": "CivilLawAgent",
    "civil": "CivilLawAgent",
    "responsabilidade_civil": "CivilLawAgent",
    "cumprimento_sentenca": "CivilLawAgent",
    # Contratual: Código Civil Livro I Título V — sem agente dedicado desde a
    # consolidação 38→8 (2026-09-06).
    "contratual": "CivilLawAgent",
    "contrato": "CivilLawAgent",
    # Responsabilidade médica: espécie de responsabilidade civil (art. 951 CC)
    # — sem agente dedicado desde a consolidação 38→8 (2026-09-06).
    "medico": "CivilLawAgent",
    "erro_medico": "CivilLawAgent",
    "responsabilidade_medica": "CivilLawAgent",
    # Saúde suplementar: relação de consumo (Súmula 469/STJ) — sem agente
    # dedicado desde a consolidação 38→8 (2026-09-06).
    "saude": "ConsumerLawAgent",
    "plano_saude": "ConsumerLawAgent",
    "sus": "ConsumerLawAgent",
    "ans": "ConsumerLawAgent",
    # Compliance / regulatório (agente de caso genérico)
    "compliance": "CaseAgent",
    "regulatorio": "CaseAgent",
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
    # Segurança técnica e mérito de LGPD (sem agente dedicado desde a
    # consolidação 38→8 de 2026-09-06) — SecurityLGPDOABAgent cobre ambos.
    "seguranca": "SecurityLGPDOABAgent",
    "auditoria_acesso": "SecurityLGPDOABAgent",
    # Relatórios (domain refina; fallback CaseAgent)
    "report": "CaseAgent",
    "relatorio": "CaseAgent",
}

def _msg_tem_termo(msg: str, termo: str) -> bool:
    """Substring comum, mas com fronteira de palavra para siglas curtas (≤3
    caracteres, sem espaço) — sem isso "ibs"/"cbs"/"cdc" casam com qualquer
    palavra que os contenha como substring (ex.: "ICBS", "cbsistema")."""
    if len(termo) <= 3 and " " not in termo:
        return re.search(rf"\b{re.escape(termo)}\b", msg) is not None
    return termo in msg


# Fallback por keywords na MENSAGEM (ordem importa: mais específico primeiro).
_KEYWORDS_PARA_AGENTE: list[tuple[tuple[str, ...], str]] = [
    (("auditar provas", "auditoria probatória", "auditoria probatoria", "lacunas probatórias", "lacunas probatorias", "ônus da prova", "onus da prova", "quais provas faltam"), "EvidenceAgent"),
    (("revisão judicial", "revisao judicial", "perspectiva do magistrado", "perspectiva do juiz", "como um magistrado", "como um juiz avaliaria"), "JudicialReviewAgent"),
    (("extrato", "tarifa bancária", "busca e apreensão", "revisional"), "BankForensicsAgent"),
    (("cdc", "código de defesa do consumidor", "codigo de defesa do consumidor", "relação de consumo", "vício do produto", "vicio do produto", "propaganda enganosa"), "ConsumerLawAgent"),
    (("execução fiscal", "execucao fiscal", "certidão de dívida ativa", "certidao de divida ativa", "icms", "decadência tributária", "decadencia tributaria", "tributár", "reforma tributária", "reforma tributaria", "ibs", "cbs", "imposto seletivo", "split payment", "lc 214", "lei complementar 214"), "TaxLawAgent"),
    # Agronegócio: matéria comercial (CC/Lei 8.929) — sem agente dedicado desde
    # a consolidação 38→8 (2026-09-06); dobrado sobre CorporateLawAgent.
    (("recuperação judicial", "recuperacao judicial", "falência", "falencia", "dissolução de sociedade", "dissolucao de sociedade", "apuração de haveres", "societár", "cédula de produto rural", "cedula de produto rural", " cpr ", "barter", "crédito rural", "credito rural", "arrendamento rural", "parceria rural", "agronegócio", "agronegocio", "commodities agrícolas", "commodities agricolas"), "CorporateLawAgent"),
    (("reclamatória trabalhista", "reclamatoria trabalhista", "verbas rescisórias", "verbas rescisorias", "horas extras", "vínculo empregatício", "vinculo empregaticio", "aviso prévio", "aviso previo", "fgts", "trabalhist", "clt"), "LaborLawAgent"),
    # Mais específico que a keyword crua "penal" do CriminalLawAgent (abaixo):
    # "cláusula penal" é instituto contratual (CC arts. 408-416), não penal.
    # Sem agente contratual dedicado desde a consolidação 38→8 (2026-09-06) —
    # o desempate segue necessário (impede queda no CriminalLawAgent).
    (("cláusula penal", "clausula penal"), "CaseAgent"),
    (("criminal", "penal", "denúncia criminal", "denuncia criminal", "inquérito policial", "inquerito policial", "dosimetria", "flagrante", "habeas corpus", "prisão preventiva", "prisao preventiva", "anpp"), "CriminalLawAgent"),
    (("improbidade", "processo administrativo", "auto de infração", "auto de infracao", "poder de polícia", "poder de policia", "responsabilidade civil do estado", "servidor público", "servidor publico", "sanção administrativa", "sancao administrativa", "administrativo"), "AdministrativeLawAgent"),
    (("juizado especial", "juizados especiais", "turma recursal", "recurso inominado", "lei 9.099", "lei 9099", "jefp", " jec", " jef"), "SpecialCourtsAgent"),
    # Responsabilidade médica: espécie de responsabilidade civil (art. 951 CC)
    # e rescisão contratual (CC Livro I Título V) — sem agentes dedicados desde
    # a consolidação 38→8 (2026-09-06); dobradas sobre CivilLawAgent.
    (("responsabilidade civil", "dano moral", "dano material", "danos morais", "reparação de danos", "reparacao de danos", "cumprimento de sentença", "cumprimento de sentenca", "tutela de urgência", "tutela de urgencia", "tutela provisória", "tutela provisoria", "prescrição civil", "prescricao civil", "ação de cobrança", "acao de cobranca", "erro médico", "erro medico", "responsabilidade médica", "responsabilidade medica", "consentimento informado", "negligência médica", "negligencia medica", "imperícia médica", "impericia medica", "iatrogenia", "rescisão contratual", "rescisao contratual", "distrato", "inadimplemento contratual", "onerosidade excessiva", "vício redibitório", "vicio redibitorio", "revisão contratual", "revisao contratual", "boa-fé objetiva", "exceção do contrato não cumprido"), "CivilLawAgent"),
    (("compliance", "regulatório", "regulatorio"), "CaseAgent"),
    (("auditoria de acesso", "segurança do sistema", "seguranca do sistema"), "SecurityLGPDOABAgent"),
    (("jurimetria", "probabilidade", "predição", "predicao"), "JurimetryAgent"),
    (("honorário", "honorario", "contrato de honorários"), "FinanceAgent"),
    (("minuta", "petição", "peticao", "peça", "peca processual", "redigir", "redija"), "LegalWritingAgent"),
    (("jurisprudência", "jurisprudencia", "súmula", "sumula", "precedente", "pesquis"), "RAGResearchAgent"),
    (("prazo", "intimação", "intimacao", "audiência", "audiencia", "andamento"), "ProcessAgent"),
    (("resumir", "resumo do documento", "documento anexo", "ocr"), "DocumentAgent"),
    (("mensagem para o cliente", "comunicar o cliente", "informar o cliente"), "ClientCommunicationAgent"),
    (("diagnóstico do sistema", "diagnostico do sistema", "saúde do sistema", "saude do sistema"), "SystemHealthAgent"),
    # Saúde suplementar: relação de consumo (Súmula 469/STJ) — sem agente
    # dedicado desde a consolidação 38→8 (2026-09-06); dobrada sobre
    # ConsumerLawAgent. Fica APÓS SystemHealthAgent para nunca capturar
    # "saúde do sistema" (técnico); só reage a keywords jurídicas de saúde.
    (("plano de saúde", "plano de saude", "negativa de cobertura", "fornecimento de medicamento", "judicialização da saúde", "judicializacao da saude", "rol da ans", "saúde suplementar", "saude suplementar", "home care", "internação hospitalar", "internacao hospitalar"), "ConsumerLawAgent"),
]

# Agentes cujo trabalho normalmente depende de um caso concreto.
_AGENTES_COM_CASO = {
    "CaseAgent", "EvidenceAgent", "JudicialReviewAgent", "ProcessAgent",
    "FinanceAgent", "BankForensicsAgent",
    "ConsumerLawAgent", "TaxLawAgent", "CorporateLawAgent",
    "LaborLawAgent", "CriminalLawAgent",
    "AdministrativeLawAgent", "SpecialCourtsAgent", "CivilLawAgent",
}


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
    # Tarefas genéricas deixam o domínio selecionar o especialista delegado.
    if task in (
        "chat", "case_analysis", "analise_caso", "case", "estrategia",
        "report", "relatorio",
    ) and dom:
        nome_agente = _agente_por_chave(dom) or nome_agente
    if nome_agente is None:
        nome_agente = _agente_por_chave(dom)
    if nome_agente is None:
        msg = (mensagem or "").lower()
        for palavras, agente in _KEYWORDS_PARA_AGENTE:
            if any(_msg_tem_termo(msg, p) for p in palavras):
                nome_agente = agente
                break
    if nome_agente is None:
        nome_agente = "CaseAgent"

    agente: AgenteInterno = AGENT_REGISTRY[nome_agente]
    tarefa = agente.tarefa_padrao

    return IntentResultado(
        agente=nome_agente,
        tarefa=tarefa,
        exige_fonte=agente.exige_fonte,
        precisa_caso=nome_agente in _AGENTES_COM_CASO,
    )
