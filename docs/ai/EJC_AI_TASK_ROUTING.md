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

`get_configuracao(tarefa)` devolve provider/model/prompt_key/max_tokens/temperature.
O caminho legado segue a mesma política: Groq para triagem/resumo/default;
Maritaca/Sabiá para leitura, análise, prazos, peças e pesquisa. Claude não é
selecionado por este router; é uma escolha explícita no gateway/interface.

| TarefaIA | Provider/modelo automático | Uso |
|---|---|---|
| TRIAGEM, RESUMO, DEFAULT | Groq | tarefas corriqueiras/econômicas |
| PRAZOS, HONORARIOS, AUDIENCIA | Maritaca/Sabiá | leitura e raciocínio jurídico |
| RAG_QUERY, PESQUISA_JURIDICA | Maritaca/Sabiá | leitura/síntese das fontes recuperadas e pesquisa |
| ANALISE_CASO, DOSSIE | Maritaca/Sabiá | análise e estratégia |
| MINUTAS e áreas jurídicas especializadas | Maritaca/Sabiá | redação/análise de mérito |

Claude/Anthropic continua disponível com `provider_override="anthropic"`,
acionado explicitamente no EJC.

No núcleo, o orchestrator usa `cfg.temperature`/`cfg.max_tokens` e o system prompt do `prompt_key` do agente (orchestrator.py:126-127, 143). O provider/model da tabela é usado diretamente pelo caminho legado `executar_tarefa_ia` (ai_gateway.py:408-445); no caminho do núcleo quem decide o provider é a cadeia do gateway (abaixo).

## 4. TarefaIA → task_type do gateway (orchestrator.py:38-61)

`_TAREFA_PARA_GATEWAY`: ANALISE_CASO/DOSSIE/TRABALHISTA/CRIMINAL/FAMILIA → `estrategia`; AMBIENTAL/PRAZOS/AUDIENCIA/HONORARIOS/PESQUISA_JURIDICA/RAG_QUERY → `analise_juridica`; MINUTAS → `elaboracao_peca`; TRIAGEM/RESUMO → `resumo`; DEFAULT → `chat_rapido`. Overrides por agente (`_AGENTE_GATEWAY_OVERRIDE`): JurimetryAgent→`jurimetria`, BankForensicsAgent→`analise_contrato`, LicitacaoComplianceAgent→`auditoria_peca`. Aliases do gateway (`TASK_ALIASES`, ai_gateway.py:39-46): redacao_peca/redacao_juridica/peca_juridica→elaboracao_peca; analise_caso→estrategia; pesquisa_juridica/rag_query→analise_juridica.

## 5. task_type do gateway → cadeia de providers (TASK_ROUTING, ai_gateway.py:76-118)

| task_type | Cadeia declarada (ordem do TASK_ROUTING) | Modelo Ollama |
|---|---|---|
| analise_juridica | Maritaca → (Ollama) → Groq | leitura/pesquisa jurídica |
| elaboracao_peca | Maritaca → (Ollama) → Groq | redação automática |
| resumo | Groq → (Ollama) → Maritaca | rotina |
| chat_rapido | Groq → (Ollama) → Maritaca | rotina |
| analise_contrato | Maritaca → (Ollama) → Groq | leitura/raciocínio |
| estrategia | Maritaca → (Ollama) → Groq | mérito |
| auditoria_peca | Maritaca → (Ollama) → Groq | revisão |
| jurimetria | Maritaca → (Ollama) → Groq | análise |

Ordem final usa `AI_PROVIDER_PRIORITY=groq,maritaca,ollama,anthropic` e,
depois, a promoção por perfil da tarefa + filtro `_provider_elegivel` (ai_gateway.py:272-330): ollama exige OLLAMA_ENABLED; anthropic exige ENABLED+chave+AI_EXTERNAL_PROVIDERS_ALLOWED (modelo = ANTHROPIC_MODEL_COMPLEXO, linha 305); groq exige chave+externos permitidos. Cadeia vazia → último recurso `("groq", ...)` que falha com erro claro (linhas 327-329). `provider_override`/`AI_PROVIDER != "auto"` força um único provider (linhas 179-182, 316-317). Em cada tentativa a provider externo aplica-se a barreira final de PII (linhas 192-207); falha → próximo da cadeia com `fallback_ativado`/`fallback_motivo` no `GatewayResponse` (linhas 135-148).
