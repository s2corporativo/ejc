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
    "EnvironmentalLawAgent": AgenteInterno(
        nome="EnvironmentalLawAgent",
        descricao="Direito ambiental: licenciamento, infrações, responsabilidade, reparação e regularização.",
        dominios=["ambiental", "licenciamento_ambiental", "infracao_ambiental"],
        tarefa_padrao=TarefaIA.AMBIENTAL,
        prompt_key="ambiental",
        exige_fonte=True,
        skills=_skills("ramo_ambiental", "build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "DigitalLGPDAgent": AgenteInterno(
        nome="DigitalLGPDAgent",
        descricao="Direito digital e LGPD: bases legais, contratos digitais, incidentes e prova eletrônica.",
        dominios=["digital_lgpd", "lgpd", "direito_digital"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="seguranca_lgpd",
        exige_fonte=True,
        skills=_skills("ramo_digital_lgpd", "build_case_context", "retrieve_rag_sources", "validate_citations"),
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
    "SocialSecurityAgent": AgenteInterno(
        nome="SocialSecurityAgent",
        descricao="Direito previdenciário: RGPS, benefícios, carência, prévio requerimento (INSS).",
        dominios=["previdenciario", "inss", "beneficio"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="previdenciario",
        exige_fonte=True,
        skills=_skills("ramo_previdenciario", "build_case_context", "retrieve_rag_sources", "validate_citations"),
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
    "FamilyLawAgent": AgenteInterno(
        nome="FamilyLawAgent",
        descricao="Direito de família: divórcio/guarda, alimentos, união estável, regime de bens; melhor interesse da criança.",
        dominios=["familia", "divorcio", "alimentos", "guarda"],
        tarefa_padrao=TarefaIA.FAMILIA,
        prompt_key="familia",
        exige_fonte=True,
        skills=_skills("ramo_familia", "build_case_context", "retrieve_rag_sources", "validate_citations"),
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
    "SuccessionLawAgent": AgenteInterno(
        nome="SuccessionLawAgent",
        descricao="Direito das sucessões: abertura, ordem de vocação, legítima, colação/sonegados, inventário/arrolamento/partilha (judicial e extrajudicial) e ITCMD.",
        dominios=["sucessoes", "inventario", "partilha", "heranca"],
        tarefa_padrao=TarefaIA.SUCESSOES,
        prompt_key="sucessoes",
        exige_fonte=True,
        skills=_skills("build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "RealEstateLawAgent": AgenteInterno(
        nome="RealEstateLawAgent",
        descricao="Direito imobiliário: locação (despejo/revisional/renovatória), usucapião, condomínio e registros públicos.",
        dominios=["imobiliario", "locacao", "despejo", "usucapiao", "condominio"],
        tarefa_padrao=TarefaIA.IMOBILIARIO,
        prompt_key="imobiliario",
        exige_fonte=True,
        skills=_skills("ramo_imobiliario", "build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "ConstitutionalLawAgent": AgenteInterno(
        nome="ConstitutionalLawAgent",
        descricao="Direito constitucional e remédios: mandado de segurança, habeas data, ação popular, ação civil pública e controle de constitucionalidade (difuso/concentrado).",
        dominios=["constitucional", "mandado_seguranca", "habeas_data", "acao_popular",
                  "acao_civil_publica", "controle_constitucionalidade"],
        tarefa_padrao=TarefaIA.CONSTITUCIONAL,
        prompt_key="constitucional",
        exige_fonte=True,
        skills=_skills("build_case_context", "retrieve_rag_sources", "validate_citations"),
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
    "TrafficLawAgent": AgenteInterno(
        nome="TrafficLawAgent",
        descricao="Direito de trânsito: CTB e Resoluções CONTRAN, processo administrativo (defesa prévia/JARI/CETRAN), suspensão/cassação da CNH e crimes de trânsito (arts. 302-312) no rito do JECrim.",
        dominios=["transito", "ctb", "multa", "cnh", "jari", "cetran"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="transito",
        exige_fonte=True,
        skills=_skills("ramo_transito", "build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "HealthLawAgent": AgenteInterno(
        nome="HealthLawAgent",
        descricao="Direito à saúde: SUS (Lei 8.080), planos de saúde (Lei 9.656), rol exemplificativo da ANS (Lei 14.454), negativa de cobertura e judicialização de medicamentos/insumos.",
        dominios=["saude", "sus", "plano_saude", "ans"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="saude",
        exige_fonte=True,
        skills=_skills("build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "MedicalLawAgent": AgenteInterno(
        nome="MedicalLawAgent",
        descricao="Responsabilidade civil médica: obrigação de meio × resultado, erro médico (imperícia/negligência/imprudência), consentimento informado e responsabilidade do hospital.",
        dominios=["medico", "erro_medico", "responsabilidade_medica"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="medico",
        exige_fonte=True,
        skills=_skills("build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "AgrarianLawAgent": AgenteInterno(
        nome="AgrarianLawAgent",
        descricao="Direito agrário: Estatuto da Terra, reforma agrária (Lei 8.629), função social da propriedade rural, usucapião especial rural (CF art. 191), posse agrária e INCRA.",
        dominios=["agrario", "reforma_agraria", "posse_rural"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="agrario",
        exige_fonte=True,
        skills=_skills("build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "AgribusinessLawAgent": AgenteInterno(
        nome="AgribusinessLawAgent",
        descricao="Direito do agronegócio: CPR (Lei 8.929, alterada pela Lei 13.986), contratos agrários (arrendamento/parceria), barter, crédito rural e marco legal do agro.",
        dominios=["agronegocio", "cpr", "credito_rural"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="agronegocio",
        exige_fonte=True,
        skills=_skills("build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "ElectoralLawAgent": AgenteInterno(
        nome="ElectoralLawAgent",
        descricao="Direito eleitoral: Código Eleitoral, inelegibilidades (LC 64/135 — Ficha Limpa), eleições/propaganda (Lei 9.504), prestação de contas, registro de candidatura e AIJE/AIME/RCED.",
        dominios=["eleitoral", "inelegibilidade", "prestacao_contas_eleitoral"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="eleitoral",
        exige_fonte=True,
        skills=_skills("build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "InternationalLawAgent": AgenteInterno(
        nome="InternationalLawAgent",
        descricao="Direito internacional privado: LINDB, homologação de sentença estrangeira e exequatur de carta rogatória (competência do STJ), contratos internacionais e arbitragem estrangeira (Convenção de Nova York).",
        dominios=["internacional", "homologacao_sentenca_estrangeira", "contrato_internacional"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="internacional",
        exige_fonte=True,
        skills=_skills("build_case_context", "retrieve_rag_sources", "validate_citations"),
    ),
    "ContractLawAgent": AgenteInterno(
        nome="ContractLawAgent",
        descricao="Direito contratual: Teoria Geral dos Contratos (CC arts. 421-480), função social e boa-fé objetiva, vícios redibitórios/evicção, onerosidade excessiva, distrato e revisão contratual.",
        dominios=["contratual", "contrato"],
        tarefa_padrao=TarefaIA.ANALISE_CASO,
        prompt_key="contratual",
        exige_fonte=True,
        skills=_skills("build_case_context", "retrieve_rag_sources", "validate_citations"),
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
