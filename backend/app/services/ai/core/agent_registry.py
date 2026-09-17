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
    "EJCCoordinatorAgent": AgenteInterno(
        nome="EJCCoordinatorAgent",
        descricao="Coordenador nativo do EJC: delega ao especialista e combina método do ramo com método do módulo.",
        dominios=["ejc", "coordenacao", "modulo"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        exige_fonte=True,  # conteúdo de mérito exige fonte (A/P1-4)
        prompt_key="analise_caso",
        skills=_skills("resolve_native_skills", "retrieve_rag_sources",
                       "validate_citations"),
    ),
    "CaseAgent": AgenteInterno(
        nome="CaseAgent",
        descricao="Análise estratégica de casos: fatos, teses, riscos e providências.",
        dominios=["casos", "estrategia", "analise"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        exige_fonte=True,  # conteúdo de mérito exige fonte (A/P1-4)
        prompt_key="analise_caso",
        skills=_skills("build_case_context", "retrieve_rag_sources",
                       "validate_citations"),
    ),
    "EvidenceAgent": AgenteInterno(
        nome="EvidenceAgent",
        descricao=("Auditoria probatória transversal: separa alegação, fato comprovado, "
                   "prova existente, lacuna, ônus e diligência necessária."),
        dominios=["provas", "evidencias", "lacunas_probatorias", "onus_prova"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="provas",
        exige_fonte=True,
        skills=_skills("build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "JudicialReviewAgent": AgenteInterno(
        nome="JudicialReviewAgent",
        descricao=("Revisão judicial simulada e não preditiva: examina admissibilidade, "
                   "ônus, prova, teses contrapostas e perguntas que exigiriam saneamento."),
        dominios=["revisao_judicial", "perspectiva_magistrado", "analise_judicial"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="revisao_judicial",
        exige_fonte=True,
        skills=_skills("build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "ProcessAgent": AgenteInterno(
        nome="ProcessAgent",
        descricao="Andamento processual e prazos: fases, movimentos e datas fatais.",
        dominios=["processo", "prazos", "andamento"],
        tarefa_padrao=TarefaIA.PRAZOS,
        prompt_key="processo",
        # I5/B5: prazo é afirmação normativa (CPC/CLT/regimento) — exige fonte
        # verificável e passa pelo gate de citações como os agentes de ramo.
        exige_fonte=True,
        skills=_skills("build_case_context", "build_process_context", "analyze_deadline",
                       "retrieve_rag_sources", "validate_citations"),
    ),
    "DocumentAgent": AgenteInterno(
        nome="DocumentAgent",
        descricao="Análise/resumo de documentos do GED (texto OCR extraído).",
        dominios=["documento", "resumo", "ocr"],
        tarefa_padrao=TarefaIA.RESUMO,
        prompt_key="resumo",
        skills=_skills("build_document_context", "summarize_document", "extract_structured_data"),
    ),
    # Extração ESTRUTURADA (JSON) de pacote documental — distinta do resumo.
    # O DocumentAgent responde por `resumo` (TarefaIA.RESUMO: 900 tokens, rota
    # econômica), orçamento adequado a um sumário em prosa e INSUFICIENTE para
    # devolver o schema JSON da Entrada Universal/Defesas (~15 chaves de topo
    # com listas aninhadas). Truncado no meio, o JSON não faz parse e o chamador
    # cai no fallback — área, partes, prazo e teses chegam vazios à tela.
    # TarefaIA.DOSSIE dá o teto (5.000) e o modelo complexo que a tarefa exige.
    "DocumentExtractionAgent": AgenteInterno(
        nome="DocumentExtractionAgent",
        descricao="Extração estruturada (JSON) de pacote documental: fase, partes, datas, vícios, teses e lacunas.",
        dominios=["extracao_documental", "entrada_universal", "pacote_documental"],
        tarefa_padrao=TarefaIA.DOSSIE,
        prompt_key="analise_caso",
        skills=_skills("build_document_context", "extract_structured_data", "retrieve_rag_sources"),
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
        exige_fonte=True,  # conteúdo de mérito exige fonte (A/P1-4)
        prompt_key="honorarios",
        skills=_skills("build_case_context", "analyze_financial_case", "estimate_ai_cost",
                       "validate_citations"),
    ),
    "BankForensicsAgent": AgenteInterno(
        nome="BankForensicsAgent",
        descricao="Perícia bancária: extratos, encargos, tarifas e revisional.",
        dominios=["bancario", "extrato", "revisional"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="bancario",
        exige_fonte=True,
        skills=_skills("ramo_bancario", "build_case_context", "analyze_bank_statement"),
    ),
    "ConsumerLawAgent": AgenteInterno(
        nome="ConsumerLawAgent",
        descricao="Direito do consumidor: CDC, vícios/fato, práticas abusivas, inversão do ônus.",
        dominios=["consumidor", "cdc"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="consumidor",
        exige_fonte=True,
        skills=_skills("ramo_consumidor", "build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "TaxLawAgent": AgenteInterno(
        nome="TaxLawAgent",
        descricao="Direito tributário: CTN, execução fiscal, decadência/prescrição, CDA e embargos.",
        dominios=["tributario", "fiscal", "execucao_fiscal"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="tributario",
        exige_fonte=True,
        skills=_skills("ramo_tributario", "build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "CorporateLawAgent": AgenteInterno(
        nome="CorporateLawAgent",
        descricao="Direito empresarial: societário, contratos, recuperação/falência e compliance.",
        dominios=["empresarial", "societario", "recuperacao_judicial"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="empresarial",
        exige_fonte=True,
        skills=_skills("ramo_empresarial", "build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "LaborLawAgent": AgenteInterno(
        nome="LaborLawAgent",
        descricao="Direito do trabalho: vínculo, verbas rescisórias, jornada/horas extras, prescrição, súmulas TST.",
        dominios=["trabalhista", "clt", "verbas_rescisorias"],
        tarefa_padrao=TarefaIA.TRABALHISTA,
        prompt_key="trabalhista",
        exige_fonte=True,
        skills=_skills("ramo_trabalhista", "build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "CriminalLawAgent": AgenteInterno(
        nome="CriminalLawAgent",
        descricao="Direito penal: tipicidade, autoria/materialidade, excludentes, dosimetria, prescrição, nulidades e ANPP.",
        dominios=["criminal", "penal"],
        tarefa_padrao=TarefaIA.CRIMINAL,
        prompt_key="criminal",
        exige_fonte=True,
        skills=_skills("ramo_criminal", "build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "AdministrativeLawAgent": AgenteInterno(
        nome="AdministrativeLawAgent",
        descricao="Direito administrativo: processo administrativo (Lei 9.784), improbidade (dolo específico), responsabilidade civil do Estado, auto de infração/poder de polícia e sanções da Lei 14.133.",
        dominios=["administrativo", "improbidade", "processo_administrativo"],
        tarefa_padrao=TarefaIA.ADMINISTRATIVO,
        prompt_key="administrativo",
        exige_fonte=True,
        skills=_skills("ramo_administrativo", "build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "SpecialCourtsAgent": AgenteInterno(
        nome="SpecialCourtsAgent",
        descricao="Juizados Especiais (JEC/JEF/JEFP): rito, competência e valor de alçada, ausência de custas em 1º grau e recursos às turmas recursais.",
        dominios=["juizados", "jec", "jef", "jefp"],
        tarefa_padrao=TarefaIA.JUIZADOS,
        prompt_key="juizados",
        exige_fonte=True,
        skills=_skills("build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "CivilLawAgent": AgenteInterno(
        nome="CivilLawAgent",
        descricao="Direito civil (material e processual): responsabilidade civil, prescrição/decadência, tutelas provisórias, cumprimento de sentença/execução e recursos cíveis.",
        dominios=["civel", "civil", "responsabilidade_civil"],
        tarefa_padrao=TarefaIA.CIVEL,
        prompt_key="civel",
        exige_fonte=True,
        skills=_skills("ramo_civil", "build_case_context", "retrieve_rag_sources", "validate_citations"),
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
        dominios=["seguranca", "auditoria_acesso", "etica_oab"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="seguranca_lgpd",
        # I5/B5: base legal (LGPD/Código de Ética OAB) é afirmação normativa.
        exige_fonte=True,
        skills=_skills("retrieve_rag_sources", "generate_report", "validate_citations"),
    ),
}


def get_agente(nome: str) -> AgenteInterno:
    """Busca agente por nome; KeyError explícito se não registrado."""
    return AGENT_REGISTRY[nome]
