# ── app/services/ai/core/agent_registry.py ───────────────────────────────────
# REGISTRO DOS AGENTES INTERNOS do Núcleo Único de IA.
#
# Cada agente é METADADO puro (sem código de execução): domínios que atende,
# tarefa padrão (TarefaIA → system prompt/modelo), se exige fonte verificável,
# roles autorizados e o pipeline de skills que o orchestrator percorre.
# A execução real é sempre a mesma (orchestrator.run) — o agente só parametriza.
from __future__ import annotations
from dataclasses import dataclass, field

from app.services.system_prompts import TarefaIA

# Roles com acesso aos agentes TÉCNICOS (diagnóstico/reparo/design).
_ROLES_TECNICOS = ["superadmin", "admin", "socio"]

# Pipeline base compartilhado (todo agente passa por estas etapas no orchestrator).
_PIPELINE_BASE = [
    "classify_intent", "sanitize_for_external_provider", "check_pii_residual",
    "select_ai_provider", "call_model", "mark_as_draft", "log_ai_interaction",
]


@dataclass(frozen=True)
class AgenteInterno:
    nome: str
    descricao: str
    dominios: list[str]
    tarefa_padrao: TarefaIA
    prompt_key: str
    exige_fonte: bool = False
    # None = qualquer usuário interno (staff). cliente_externo NUNCA acessa
    # o núcleo (bloqueado antes, no orchestrator/router).
    roles_permitidos: list[str] | None = None
    skills: list[str] = field(default_factory=list)


def _skills(*extras: str) -> list[str]:
    """Pipeline base + skills específicas do agente (sem duplicatas)."""
    return _PIPELINE_BASE[:1] + [e for e in extras] + _PIPELINE_BASE[1:]


AGENT_REGISTRY: dict[str, AgenteInterno] = {
    "CaseAgent": AgenteInterno(
        nome="CaseAgent",
        descricao="Análise estratégica de casos: fatos, teses, riscos e providências.",
        dominios=["casos", "estrategia", "analise"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="analise_caso",
        skills=_skills("build_case_context", "retrieve_rag_sources"),
    ),
    "ProcessAgent": AgenteInterno(
        nome="ProcessAgent",
        descricao="Andamento processual e prazos: fases, movimentos e datas fatais.",
        dominios=["processo", "prazos", "andamento"],
        tarefa_padrao=TarefaIA.PRAZOS,
        prompt_key="processo",
        skills=_skills("build_case_context", "build_process_context", "analyze_deadline"),
    ),
    "DocumentAgent": AgenteInterno(
        nome="DocumentAgent",
        descricao="Análise/resumo de documentos do GED (texto OCR extraído).",
        dominios=["documento", "resumo", "ocr"],
        tarefa_padrao=TarefaIA.RESUMO,
        prompt_key="resumo",
        skills=_skills("build_document_context", "summarize_document", "extract_structured_data"),
    ),
    "LegalWritingAgent": AgenteInterno(
        nome="LegalWritingAgent",
        descricao="Redação de minutas e peças jurídicas (sempre rascunho HITL).",
        dominios=["minuta", "peca", "redacao"],
        tarefa_padrao=TarefaIA.MINUTAS,
        prompt_key="minutas",
        exige_fonte=True,
        skills=_skills("build_case_context", "retrieve_rag_sources",
                       "generate_legal_draft", "validate_citations"),
    ),
    "RAGResearchAgent": AgenteInterno(
        nome="RAGResearchAgent",
        descricao="Pesquisa jurídica na base interna (RAG) com citação de fontes.",
        dominios=["pesquisa", "rag", "jurisprudencia"],
        tarefa_padrao=TarefaIA.PESQUISA_JURIDICA,
        prompt_key="pesquisa_juridica",
        exige_fonte=True,
        skills=_skills("retrieve_rag_sources", "validate_citations"),
    ),
    "JurimetryAgent": AgenteInterno(
        nome="JurimetryAgent",
        descricao="Jurimetria/predição: cenários probabilísticos sem promessa de resultado.",
        dominios=["jurimetria", "predicao", "estatistica"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="jurimetria_pred",
        exige_fonte=True,
        skills=_skills("build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "FinanceAgent": AgenteInterno(
        nome="FinanceAgent",
        descricao="Honorários e análise financeira de casos (tabela OAB/MG, contratos).",
        dominios=["financeiro", "honorarios"],
        tarefa_padrao=TarefaIA.HONORARIOS,
        prompt_key="honorarios",
        skills=_skills("build_case_context", "analyze_financial_case", "estimate_ai_cost"),
    ),
    "BankForensicsAgent": AgenteInterno(
        nome="BankForensicsAgent",
        descricao="Perícia bancária: extratos, encargos, tarifas e revisional.",
        dominios=["bancario", "extrato", "revisional"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="bancario",
        skills=_skills("build_case_context", "analyze_bank_statement"),
    ),
    "LicitacaoComplianceAgent": AgenteInterno(
        nome="LicitacaoComplianceAgent",
        descricao="Licitações, compliance, regulatório e ambiental (auditoria documental).",
        dominios=["licitacao", "compliance", "regulatorio", "ambiental"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="licitacao_compliance",
        skills=_skills("build_case_context", "build_document_context", "audit_licitacao_document"),
    ),
    "ClientCommunicationAgent": AgenteInterno(
        nome="ClientCommunicationAgent",
        descricao="Rascunhos de comunicação com o cliente (linguagem clara, sem juridiquês).",
        dominios=["mensagem_cliente", "portal", "comunicacao"],
        tarefa_padrao=TarefaIA.DEFAULT,
        prompt_key="comunicacao_cliente",
        skills=_skills("build_case_context"),
    ),
    "SystemHealthAgent": AgenteInterno(
        nome="SystemHealthAgent",
        descricao="Diagnóstico de saúde do sistema EJC (usa GRAPH_REPORT; nunca segredos).",
        dominios=["saude_sistema", "diagnostico"],
        tarefa_padrao=TarefaIA.DEFAULT,
        prompt_key="saude_sistema",
        roles_permitidos=_ROLES_TECNICOS,
        skills=_skills("diagnose_system_module", "generate_report"),
    ),
    "RepairAgent": AgenteInterno(
        nome="RepairAgent",
        descricao="Planos de reparo técnico (preview de patch; aplicação SEMPRE humana).",
        dominios=["reparo", "patch", "manutencao"],
        tarefa_padrao=TarefaIA.DEFAULT,
        prompt_key="reparo_tecnico",
        roles_permitidos=_ROLES_TECNICOS,
        skills=_skills("diagnose_system_module", "generate_repair_plan",
                       "generate_patch_preview", "apply_authorized_patch", "rollback_patch"),
    ),
    "UIUXAgent": AgenteInterno(
        nome="UIUXAgent",
        descricao="Auditoria de design system e propostas de UI/UX do EJC.",
        dominios=["design", "uiux"],
        tarefa_padrao=TarefaIA.DEFAULT,
        prompt_key="uiux",
        roles_permitidos=_ROLES_TECNICOS,
        skills=_skills("audit_design_system", "generate_saas_redesign_plan"),
    ),
    "SecurityLGPDOABAgent": AgenteInterno(
        nome="SecurityLGPDOABAgent",
        descricao="Segurança, LGPD e ética OAB: riscos, bases legais e auditoria de acesso.",
        dominios=["seguranca", "lgpd", "auditoria_acesso"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="seguranca_lgpd",
        skills=_skills("retrieve_rag_sources", "generate_report"),
    ),
}


def get_agente(nome: str) -> AgenteInterno:
    """Busca agente por nome; KeyError explícito se não registrado."""
    return AGENT_REGISTRY[nome]
