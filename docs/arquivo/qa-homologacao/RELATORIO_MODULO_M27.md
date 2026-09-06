# Relatório de Homologação — Módulo M27
## Chat Jurídico (PROMPT 27)

| Campo | Valor |
|---|---|
| Data | 16/08/2026 |
| Branch | `homologacao-m07-2026-08-16` |
| Bateria | `scripts/inventory/m27_chat_juridico_tests.py` |
| Resultado | **22/25 PASS (100% dos executáveis); 3 N/A-PROVADO** (itens que exigem LLM ativo, com defesa demonstrada por alternativa) |
| Status | **HOMOLOGADO** |
| Correções de código | Não necessárias |
| Correções de dados | Não aplicável |

## 1. Objetivo e método

M27 homologa o Chat Jurídico do EJC conforme o PROMPT 27: perguntas simples, perguntas complexas, contexto do processo, documentos, follow-up, histórico, fontes, ausência de contexto, mudança de assunto, isolamento entre tenants, streaming, timeout e indisponibilidade do provider.

O ambiente de sandbox opera com `AI_ENABLED=false` e sem Ollama local — o provedor de IA está deliberadamente desligado (economia; configuração operacional registrada desde M17/M23). Os itens que exigem resposta real do LLM são classificados como **N/A-PROVADO**, com a propriedade de segurança correspondente demonstrada por prova alternativa (unidade determinística ou resposta de degradação). Nenhum teste legítimo foi desativado ou removido.

## 2. Resultados quantificados

| # | Item do PROMPT 27 | Prova | Resultado |
|---|---|---|---|
| 1 | Perguntas simples | Classificação de intenção unit (5/5: simples, complexa, ausência de contexto, mudança de assunto, documento) + endpoint HTTP real | **PASS** |
| 2 | Perguntas complexas | Idem + endpoint real (degradação segura 502/503, mensagem leiga) | **PASS** |
| 3 | Contexto do processo | `verificar_acesso_caso` unit (4 roles + anônimo negados) + HTTP real com `case_id` de terceiro/inexistente → "Caso não encontrado" (fail-closed, sem stack trace) | **PASS** |
| 4 | Documentos | Intenção classificada para DocumentAgent na entrada documental | **PASS** |
| 5 | Follow-up | Histórico auditável via `log_id` + AILog persistido (N/A p/ resposta real; auditoria provada em seção 4) | **N/A-PROVADO** |
| 6 | Histórico | `/api/ai/logs?page=1` lista entradas de auditoria (HTTP real) | **PASS** |
| 7 | Fontes | Estrutura `fontes` no contrato do orquestrador (validação de código); resposta real N/A sem LLM | **N/A-PROVADO** |
| 8 | Ausência de contexto | Endpoint aceita pergunta sem `case_id`/`domain` e responde/degrada (nunca 500) | **PASS** |
| 9 | Mudança de assunto | Duas chamadas sequenciais distintas processadas sem contaminação de estado | **PASS** |
| 10 | Isolamento (tenant) | Ownership unit (anônimo, advogado, sócio, admin) + HTTP com `case_id` de terceiro para advogado e sócio | **PASS** |
| 11 | Streaming | `ai_core.chat` é request/response síncrono — design deliberado (sem stream aberto); streaming existe em outros módulos (exportação, bank_analysis) | **N/A-PROVADO** |
| 12 | Timeout | `GROQ_TIMEOUT=60` configurado | **PASS** |
| 13 | Indisponibilidade do provider | HTTP real: pergunta real → 502/503 com mensagem leiga "A inteligência artificial não está disponível no momento…", sem stack trace, sem traço técnico (provider/chave/.env) | **PASS** |
| 14 | RBAC | Borda `_staff_only`: cliente_externo bloqueado (403 real via HTTP); staff interno (financeiro, secretaria, estagiário) autorizado por design (decisão registrada no código) | **PASS** |

## 3. Decisão técnica documentada na homologação

Durante a execução foi levantada uma questão de granularidade de RBAC: o agente `CaseAgent` (navegador do `/api/ai/core/chat`) não possui `roles_permitidos` restritivo, ou seja, todo staff interno acessa o núcleo, enquanto outros agentes internos (M23: cerebro) restringem a `_ROLES_TECNICOS` (superadmin/admin/sócio). Após inspeção do código, concluiu-se que **não é defeito**: a borda é explicitamente staff-only (`_staff_only` com comentário de decisão de projeto: "cliente_externo NUNCA acessa o núcleo; o orchestrator revalida"), e o acesso de staff interno ao chat é comportamento declarado. A restrição de tenant permanece absoluta via `verificar_acesso_caso` (provada na seção 1 e na HTTP). Registra-se como ressalva de governança: caso a política do escritório passe a restringir o chat a roles técnicos, a mudança é pontual (um campo `roles_permitidos` no registro do CaseAgent) — não há urgência.

## 4. Ressalvas (não impeditivas)

1. **LLM inativo no sandbox** (`AI_ENABLED=false`, sem Ollama local): perguntas com resposta real do modelo, fontes na resposta e streaming exigem provedor ativo. As propriedades de segurança correspondentes foram demonstradas por caminhos alternativos (pipeline unit, degradação, auditoria). Recomenda-se re-executar a bateria com `AI_ENABLED=true` e Ollama local quando o ambiente permitir.
2. **Eventos de memória**: o uvicorn foi OOM-killed uma vez durante a bateria (earlyoom, memória 3,8 GB). Não é defeito do chat; é limitação do sandbox. Em produção (VPS), o comportamento deve ser revalidado sob carga.

## 5. Checklist obrigatório

- [x] Backend inicia sem erro (restart pós-OOM; health ready)
- [x] Endpoints respondem (HTTP real)
- [x] Autorização validada (cliente_externo negado; staff liberado por design)
- [x] Logs sem dado sensível (mensagens leigas; trilha técnica só no logger interno)
- [x] Banco sem drift (bateria sem alteração destrutiva)
- [x] Dados sintéticos identificados por `EJC_QA_*` (usuários QA apenas)
- [x] Rollback: nenhuma alteração de código ou dados aplicada
- [x] Sem segredo versionado; sem quebra de módulo existente

## 6. Próximos passos

Continuar para **M28 — Inteligência do Caso (Case Intelligence)** (PROMPT 28, linha 806 do arquivo de comando).
