# EJC — Agentes Internos e Skills do Núcleo Único de IA

Data: 2026-07-04 · Código: `backend/app/services/ai/core/{agent_registry,skill_registry}.py`.

**Agentes NÃO são IAs independentes.** Cada `AgenteInterno` é metadado puro (agent_registry.py:23-34): domínios, `tarefa_padrao` (TarefaIA → prompt/modelo), `prompt_key`, `exige_fonte`, `roles_permitidos` e pipeline de skills. A execução é sempre a mesma — `SingleAICoreOrchestrator.run` — o agente apenas parametriza o pipeline (agent_registry.py:7). Introspecção: `GET /api/ai/core/agents` e `/skills` (metadados; nunca prompts/handlers).

## 1. Os 14 agentes (AGENT_REGISTRY, agent_registry.py:42-163)

Todo agente compartilha o pipeline base `classify_intent → [skills próprias] → sanitize_for_external_provider → check_pii_residual → select_ai_provider → call_model → mark_as_draft → log_ai_interaction` (agent_registry.py:17-20, 37-39). Roles: vazio = qualquer staff (cliente_externo sempre bloqueado); "técnicos" = superadmin/admin/socio.

| Agente | Domínios | Tarefa padrão | Exige fonte | Roles | Skills específicas (além do pipeline base) |
|---|---|---|---|---|---|
| CaseAgent | casos, estrategia, analise | analise_caso | não | staff | build_case_context, retrieve_rag_sources |
| ProcessAgent | processo, prazos, andamento | prazos | não | staff | build_case_context, build_process_context, analyze_deadline |
| DocumentAgent | documento, resumo, ocr | resumo | não | staff | build_document_context, summarize_document, extract_structured_data |
| LegalWritingAgent | minuta, peca, redacao | minutas | **sim** | staff | build_case_context, retrieve_rag_sources, generate_legal_draft, validate_citations |
| RAGResearchAgent | pesquisa, rag, jurisprudencia | pesquisa_juridica | **sim** | staff | retrieve_rag_sources, validate_citations |
| JurimetryAgent | jurimetria, predicao, estatistica | analise_caso | **sim** | staff | build_case_context, retrieve_rag_sources, validate_citations |
| FinanceAgent | financeiro, honorarios | honorarios | não | staff | build_case_context, analyze_financial_case, estimate_ai_cost |
| BankForensicsAgent | bancario, extrato, revisional | analise_caso | não | staff | build_case_context, analyze_bank_statement |
| LicitacaoComplianceAgent | licitacao, compliance, regulatorio, ambiental | analise_caso (ambiental → AMBIENTAL) | não | staff | build_case_context, build_document_context, audit_licitacao_document |
| ClientCommunicationAgent | mensagem_cliente, portal, comunicacao | default | não | staff | build_case_context |
| SystemHealthAgent | saude_sistema, diagnostico | default | não | técnicos | diagnose_system_module, generate_report |
| RepairAgent | reparo, patch, manutencao | default | não | técnicos | diagnose_system_module, generate_repair_plan, generate_patch_preview, apply_authorized_patch, rollback_patch |
| UIUXAgent | design, uiux | default | não | técnicos | audit_design_system, generate_saas_redesign_plan |
| SecurityLGPDOABAgent | seguranca, lgpd, auditoria_acesso | analise_caso | não | staff | retrieve_rag_sources, generate_report |

Observações: JurimetryAgent/BankForensicsAgent/LicitacaoComplianceAgent têm perfil de gateway próprio (jurimetria/analise_contrato/auditoria_peca — orchestrator.py:57-61); SystemHealthAgent/RepairAgent recebem o GRAPH_REPORT como contexto técnico, nunca segredos (orchestrator.py:128-132).

## 2. As 28 skills (SKILL_REGISTRY, skill_registry.py:103-207)

Skill = capacidade reutilizável com contrato documentado. "Automática" = tem `handler` (delega a serviço já consolidado, import tardio); sem handler = descrita no prompt/pipeline, execução não automatizada. Skills de patch têm `handler=None` DE PROPÓSITO (skill_registry.py:7-9). Permissões: staff, salvo indicação "técnicos".

| Skill | Finalidade | Entrada → Saída | Riscos / Pré/Pós-condições | Automática |
|---|---|---|---|---|
| classify_intent | Rotear ao agente interno | task_type, domain, mensagem → IntentResultado | baixo (determinístico, sem LLM); sempre resolve (default CaseAgent) | sim |
| build_case_context | Dossiê sanitizado do caso | db, case_id → dict{texto, meta, nomes_proteger} | pré: ownership validado (ABAC); pós: sem PII estrutural | sim |
| build_process_context | Metadados processuais | db, process_id → bloco textual | pós: número CNJ omitido | não |
| build_document_context | Texto OCR do GED | db, document_id → bloco [DOCUMENTO] truncado | médio (sigilo); pré: documento FORA do cofre | não |
| retrieve_rag_sources | Buscar fontes (pgvector 768d) | db, consulta, limite → list[dict fontes] | pós: fontes devolvidas para citação | sim |
| sanitize_for_external_provider | Sanitizar PII (LGPD) | texto, nomes_proteger → (texto_limpo, houve_remocao) | ALTO se ignorada (vazamento LGPD); pós: 422 se PII persistir | sim |
| check_pii_residual | Segunda barreira de PII | texto → list[str] tipos (vazia = limpo) | baixo | sim |
| select_ai_provider | Cadeia de providers (policy) | texto, task_type → PolicyDecision | pós: externo só com conteúdo sem PII | sim |
| call_model | Chamada única via ai_gateway | messages, task_type... → GatewayResponse | médio (custo/token); pré: sanitizado + policy permitiu | sim |
| validate_citations | Conferir súmulas/artigos na base oficial | db, texto → dict{total, confirmadas, nao_encontradas} | pós: não confirmadas viram alerta HITL | sim |
| mark_as_draft | Carimbo rascunho HITL (OAB) | resultado dict → + is_rascunho/status_hitl | baixo | sim |
| log_ai_interaction | Gravar AILog | db, user, tarefa... → log_id | CRÍTICO se omitida; pós: erro de gravação PROPAGA | sim |
| estimate_ai_cost | Custo BRL por chamada | model, tokens in/out → float BRL | baixo | sim |
| generate_legal_draft | Minuta/peça jurídica | tema, tipo_peca, contexto → rascunho + citações | ALTO (conteúdo jurídico); pós: citation_check + HITL obrigatório | não |
| summarize_document | Resumo estruturado de OCR | texto → resumo técnico | baixo | não |
| extract_structured_data | Extração de campos | texto, schema → dict | baixo | não |
| analyze_deadline | Prazos e datas fatais | contexto processual → prazos + base legal | ALTO (prazo fatal); dupla conferência humana | não |
| analyze_financial_case | Honorários/financeiro (OAB/MG) | contexto + parâmetros → análise rascunho | baixo | não |
| analyze_bank_statement | Extrato/contrato bancário | texto → apontamentos + base normativa | pós: estimativas sujeitas a perícia | não |
| audit_licitacao_document | Auditoria Lei 14.133/2021 | documento → (não) conformidades + base legal | baixo | não |
| diagnose_system_module | Diagnóstico via grafo de código | módulo/sintoma → diagnóstico do GRAPH_REPORT | técnicos; pré: contexto SEM segredos | sim |
| generate_repair_plan | Plano de reparo | diagnóstico → plano ordenado + testes | técnicos; pós: plano é PROPOSTA | não |
| generate_patch_preview | Prévia de patch (diff) | plano → diff textual p/ revisão | técnicos; médio — nunca aplicado automaticamente | não |
| apply_authorized_patch | Aplicar patch autorizado | patch aprovado + autorização → n/a | técnicos; ALTO; pré: AUTORIZAÇÃO HUMANA + rollback; pós: NUNCA automática (handler ausente de propósito) | não |
| rollback_patch | Reverter patch | id do patch → n/a | técnicos; ALTO; NUNCA automática | não |
| audit_design_system | Consistência do design system | escopo → achados priorizados | técnicos | não |
| generate_saas_redesign_plan | Plano de redesign SaaS | escopo + objetivos → plano com critérios de aceite | técnicos | não |
| generate_report | Relatório executivo | domínio + contexto → relatório rascunho | baixo | não |

Contrato completo (logs, tratamento de erro) no dataclass `Skill` (skill_registry.py:18-30); listagem segura via `listar_skills()` (skill_registry.py:214-224 — expõe `automatica = handler is not None`).
