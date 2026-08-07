# EJC — Roteamento de Tarefas de IA (ponta a ponta)

Data: 2026-07-04.

Cadeia de decisão: `task_type/domain/keywords → agente (intent_classifier) → TarefaIA → ConfiguracaoIA (system_prompts/router.py) → task_type do gateway → cadeia de providers (TASK_ROUTING + AI_PROVIDER_PRIORITY + elegibilidade)`.

## 1. task_type/domain/keywords → agente (intent_classifier.py)

`classify_intent(task_type, domain, mensagem)` (intent_classifier.py:119) é 100% determinístico (sem LLM). Ordem de resolução: task_type → domain → keywords da mensagem → default `CaseAgent` (nunca falha). `report/relatorio` com domain deixa o domain escolher o especialista (linhas 134-136). Sufixo `_analysis` é normalizado (linhas 108-116).

`TASK_TYPE_PARA_AGENTE` (linhas 22-83) — resumo por agente:

| Agente | task_types/domains aceitos |
|---|---|
| CaseAgent | chat, case_analysis, analise_caso, case, estrategia, report, relatorio |
| ProcessAgent | process_analysis, prazos, processo, process |
| DocumentAgent | document_analysis, resumo_documento, ocr, resumo, documento, document |
| LegalWritingAgent | legal_draft, minuta, peca, redacao_peca |
| RAGResearchAgent | legal_research, rag, pesquisa, pesquisa_juridica, rag_query |
| JurimetryAgent | jurimetria, predicao |
| FinanceAgent | financeiro, honorarios |
| BankForensicsAgent | bancario, extrato |
| LicitacaoComplianceAgent | licitacao, compliance, regulatorio, ambiental |
| ClientCommunicationAgent | mensagem_cliente, portal |
| SystemHealthAgent | saude_sistema, diagnostico |
| RepairAgent | reparo, patch |
| UIUXAgent | design, uiux |
| SecurityLGPDOABAgent | seguranca, lgpd, auditoria_acesso |

Fallback por keywords na mensagem (`_KEYWORDS_PARA_AGENTE`, linhas 86-98, mais específico primeiro): "extrato/revisional"→BankForensics; "licitação/edital/compliance"→Licitacao; "lgpd/vazamento"→SecurityLGPDOAB; "jurimetria/probabilidade"→Jurimetry; "honorário"→Finance; "minuta/petição/redigir"→LegalWriting; "jurisprudência/súmula/pesquis"→RAGResearch; "prazo/intimação/audiência"→Process; "resumir/ocr"→Document; "mensagem para o cliente"→ClientCommunication; "diagnóstico do sistema"→SystemHealth.

## 2. Agente → TarefaIA

`tarefa_padrao` do agente (tabela em `EJC_AI_AGENTS_AND_SKILLS.md`); ajuste fino: LicitacaoComplianceAgent com task/domain "ambiental" usa `TarefaIA.AMBIENTAL` (intent_classifier.py:151-153).

## 3. TarefaIA → ConfiguracaoIA (system_prompts/router.py:53-72)

`get_configuracao(tarefa)` devolve provider/model/prompt_key/max_tokens/temperature. `_RAPIDO`=ANTHROPIC_MODEL_RAPIDO, `_COMPLEXO`=ANTHROPIC_MODEL_COMPLEXO (defaults Haiku), `_GROQ`=llama-3.3-70b-versatile:

| TarefaIA | Provider/modelo | max_tokens | temp | Justificativa |
|---|---|---|---|---|
| TRIAGEM | groq | 1200 | 0.1 | Classificação — Groq grátis |
| RESUMO | groq | 900 | 0.2 | Sumarização — Groq grátis |
| PRAZOS | anthropic/_RAPIDO | 1200 | 0.0 | Prazo fatal — precisão |
| HONORARIOS | anthropic/_RAPIDO | 1800 | 0.1 | Honorários OAB/MG |
| AUDIENCIA | anthropic/_RAPIDO | 2000 | 0.2 | Preparação de audiência |
| RAG_QUERY | anthropic/_RAPIDO | 1500 | 0.1 | Síntese de RAG |
| ANALISE_CASO | anthropic/_COMPLEXO | 4000 | 0.1 | Análise estratégica |
| DOSSIE | anthropic/_COMPLEXO | 5000 | 0.1 | Dossiê completo |
| MINUTAS | anthropic/_COMPLEXO | 6000 | 0.15 | Redação de peças |
| AMBIENTAL | anthropic/_COMPLEXO | 4000 | 0.1 | Direito ambiental técnico |
| TRABALHISTA | anthropic/_COMPLEXO | 3500 | 0.1 | CLT + TST |
| CRIMINAL | anthropic/_COMPLEXO | 3000 | 0.1 | Criminal — sensível |
| FAMILIA | anthropic/_COMPLEXO | 3000 | 0.1 | Família — sensível |
| PESQUISA_JURIDICA | anthropic/_COMPLEXO | 3000 | 0.2 | Pesquisa jurisprudencial |
| DEFAULT | anthropic/_RAPIDO | 2000 | 0.2 | Fallback — Haiku |

No núcleo, o orchestrator usa `cfg.temperature`/`cfg.max_tokens` e o system prompt do `prompt_key` do agente (orchestrator.py:126-127, 143). O provider/model da tabela é usado diretamente pelo caminho legado `executar_tarefa_ia` (ai_gateway.py:408-445); no caminho do núcleo quem decide o provider é a cadeia do gateway (abaixo).

## 4. TarefaIA → task_type do gateway (orchestrator.py:38-61)

`_TAREFA_PARA_GATEWAY`: ANALISE_CASO/DOSSIE/TRABALHISTA/CRIMINAL/FAMILIA → `estrategia`; AMBIENTAL/PRAZOS/AUDIENCIA/HONORARIOS/PESQUISA_JURIDICA/RAG_QUERY → `analise_juridica`; MINUTAS → `elaboracao_peca`; TRIAGEM/RESUMO → `resumo`; DEFAULT → `chat_rapido`. Overrides por agente (`_AGENTE_GATEWAY_OVERRIDE`): JurimetryAgent→`jurimetria`, BankForensicsAgent→`analise_contrato`, LicitacaoComplianceAgent→`auditoria_peca`. Aliases do gateway (`TASK_ALIASES`, ai_gateway.py:39-46): redacao_peca/redacao_juridica/peca_juridica→elaboracao_peca; analise_caso→estrategia; pesquisa_juridica/rag_query→analise_juridica.

## 5. task_type do gateway → cadeia de providers (TASK_ROUTING, ai_gateway.py)

| task_type | Cadeia declarada (ordem do TASK_ROUTING) |
|---|---|
| analise_juridica | anthropic → maritaca → groq |
| elaboracao_peca | anthropic → maritaca → groq |
| resumo | maritaca → groq |
| chat_rapido | maritaca → groq |
| analise_contrato | anthropic → maritaca → groq |
| estrategia | anthropic → maritaca → groq |
| auditoria_peca | anthropic → maritaca → groq |
| jurimetria | anthropic → maritaca → groq |

Ordem final = `_ordenar_por_prioridade` por `AI_PROVIDER_PRIORITY` (default `anthropic,maritaca,groq`) + filtro `_provider_elegivel` (ai_gateway.py): anthropic exige ENABLED+chave+AI_EXTERNAL_PROVIDERS_ALLOWED (modelo = ANTHROPIC_MODEL_COMPLEXO); maritaca exige ENABLED+chave+AI_EXTERNAL_PROVIDERS_ALLOWED; groq exige chave+externos permitidos. Cadeia vazia → último recurso `("groq", ...)` que falha com erro claro. `provider_override`/`AI_PROVIDER != "auto"` força um único provider. Em cada tentativa a provider externo aplica-se a barreira final de PII; falha → próximo da cadeia com `fallback_ativado`/`fallback_motivo` no `GatewayResponse`.

O EJC não tem provider de IA local: sem nenhum provider externo elegível
(chave ausente ou `AI_EXTERNAL_PROVIDERS_ALLOWED=false`), a cadeia fica vazia
e a chamada é bloqueada por política de sigilo/LGPD.
