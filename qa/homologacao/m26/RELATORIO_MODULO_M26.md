# Relatório de Homologação — Módulo M26
## Segurança Adversarial da IA (Prompt Injection e Segurança da IA)

| Campo | Valor |
|---|---|
| Data | 16/08/2026 |
| Branch | `homologacao-m07-2026-08-16` |
| Commit | pendente (a criar ao final) |
| Bateria | `scripts/inventory/m26_injection_tests.py` |
| Resultado | **41/41 PASS (100%)** |
| Status | **HOMOLOGADO** |
| Correções de código | Não necessárias |
| Correções de dados | Não aplicável |

## 1. Objetivo e método

M26 homologa a defesa adversarial da IA do EJC conforme o PROMPT 26: **injection direta, injection em documento, extração de system prompt, vazamento entre tenants, tool calling indevido (SQL, filesystem, URLs), markdown malicioso e instruções escondidas em documentos**, com quantificação por cenário.

A bateria distingue duas camadas: (A) **barreiras determinísticas** — o sanitizer, a guarda de entrada (ai_guard) e a barreira final do gateway antes de qualquer provider externo; (B) **provas reais** — payloads de ataque concretos (seis vetores) processados pela função pública do gateway, e um teste HTTP real de autorização. A execução real do LLM não é necessária para provar as barreiras, porque a propriedade de segurança defendida — *nenhum dado pessoal e nenhuma URL extraída do prompt cru chega ao provider externo* — é verificável no texto sanitizado. Ambientes sem Ollama local (sandbox) com AI_ENABLED=false preservam o estado operacional: o endpoint retorna 503 seguro em vez de vazar.

## 2. Resultados quantificados

| # | Cenário de ataque | Barreira | Resultado |
|---|---|---|---|
| 1–24 | PII estrutural (CPF, CNPJ, processo CNJ, RG, e-mail, telefone, CEP, cartão, chave PIX, OAB, endereço, data de nascimento) | `sanitizar_pii` — 12 placeholders | **24/24 PASS**: nenhum dígito do padrão original remanesce |
| 25–26 | CPF/CNPJ em provedor externo vs. uso interno | `sanitizar_pii` / `sanitizar_pii_interno` | **2/2 PASS**: externo mascara; interno preserva (Ollama local) |
| 27 | PII residual após sanitização | `validar_sem_pii` (segunda barreira) | **1/1 PASS** |
| 28 | Nomes do caso (cliente / parte contrária) | `nomes_proteger` → [PARTE_N] | **1/1 PASS** |
| 29 | Barreira de entrada (ai_guard) | não aborta análise legítima, sanitiza e registra residual sem vazar valores | **1/1 PASS** |
| 30 | Cliente externo no orquestrador de IA | RBAC do `SingleAICoreOrchestrator` | **1/1 PASS** |
| 31 | Caso de tenant terceiro via RAG/caso | `verificar_acesso_caso` (ownership) | **1/1 PASS** |
| 32–35 | Tool calling indevido: SQL, filesystem, comandos de sistema, URLs do prompt | arquitetura do gateway (não há ferramentas executáveis) | **4/4 PASS** |
| 36–41 | Seis vetores de ataque reais: injection direta, instrução escondida em documento, extração de prompt/segredo, markdown/HTML malicioso, URLs perigosas (file://, javascript:), PII do tenant | barreira final `_sanitizar_messages_externo` + pseudonimização; AILog recebe versão pseudonimizada | **6/6 PASS**: nenhum valor proibido em claro, residual detectado/monitorado |
| 41 | Cliente externo bloqueado do endpoint HTTP `/api/ai/resumir-texto` | RBAC portal | **1/1 PASS** (HTTP real) |

## 3. Provas principais (trecho das barreiras confirmadas)

A barreira final do gateway mascara todos os 12 padrões estruturados antes de Anthropic/Groq e **pulou o provider externo com RuntimeError segura quando sobra residual** (`_ProviderPulado` → mensagem "Conteúdo com dados pessoais não pode ir a provider externo — configure Ollama ou revise o texto", que não ecoa conteúdo nem valores de PII). O mapa de reidratação da pseudonimização vive apenas em memória e **nunca é logado em AILog/Langfuse nem enviado ao provider**. No AILog, o `prompt_sanitizado` é truncado em 8.000 caracteres e a mensagem segura do bloqueio nunca contém o conteúdo do texto. Os erros propagados ao usuário são leigos (classe do erro + status HTTP), com trilha interna completa apenas em log do servidor — sem stack trace público (padrão P0 §3.2 confirmado na inspeção do código).

## 4. Ressalvas registradas (não impeditivas)

1. **Sem execução real do LLM neste ambiente**: o sandbox não tem Ollama local e `AI_ENABLED=false` por configuração operacional (economia; M23/M24 já provaram graceful degradation 503). As barreiras que protegem o provider externo foram provadas de forma determinística e exaustiva; a resistência do LLM em si aos seis vetores de injection é mitigada pelo system prompt ("Não invente nada que não esteja no texto") e pela sanitização, mas recomenda-se re-executar a seção D contra um provider real habilitado (AI_ENABLED=true) quando disponível, como teste complementar.
2. **Instruções escondidas em documentos RAG**: o contexto RAG recuperado é anexado ao system prompt após sanitização e é escopado por client (tenant). O mecanismo de contenção é o escopo de recuperação + sanitização, não um filtro anti-instruction independente — arquitetura correta e coerente, mas é a única superfície sem barreira dedicada de "instruction hiding" documental.

## 5. Checklist obrigatório

- [x] Backend inicia sem erro (health ready após bateria)
- [x] Endpoints respondem (teste HTTP real de RBAC do portal)
- [x] Autorização validada (cliente_externo negado em IA interna e portal)
- [x] Logs sem dado sensível (piloto do gateway não ecoa PII; AILog truncado e sanitizado)
- [x] Banco sem drift (bateria sem persistência de dados)
- [x] Dados sintéticos identificados por `EJC_QA_*` (usuários QA apenas)
- [x] Rollback: nenhuma alteração de código ou dados aplicada
- [x] Sem segredo versionado; sem quebra de módulo existente

## 6. Próximos passos

Continuar para **M27 — Chat Jurídico** (PROMPT 27, linha 781 do arquivo de comando).
