# EJC — Relatório Final: Consolidação do Núcleo Único de IA Nativa

Data: 2026-07-04 · Branch: `claude/ejc-legal-ai-architecture-s2ctes` · PR: #23

## 1. Situação anterior

- Gateway central legítimo (`services/ai_gateway.py`) coexistindo com um **gateway-sombra** (`core/ai_brain.py`: httpx direto ao Ollama, sem sanitização, sem AILog, sem fallback) consumido por ~16 pontos.
- ~10 endpoints de IA sem AILog; 4 fluxos enviando conteúdo ao modelo sem sanitização; 1 endpoint com `pii_removida=False` hardcoded; 1 endpoint de IA sem exigência de usuário autenticado.
- Decisão de provider fragmentada (TASK_ROUTING + system_prompts/router + env), sem política LGPD unificada e sem barreira final de PII.
- Provider Anthropic funcional mas sem timeout, sem teto de tokens, sem kill-switch.
- 1 prompt jurídico montado no navegador; conteúdo integral de peças trafegando pelo browser.
- Detalhe completo: `docs/ai/EJC_SINGLE_AI_CORE_AUDIT.md`.

## 2. Situação nova

Arquitetura única e governada:

```
frontend (lib/aiCore.ts) → backend → routers (centrais ou wrappers)
  → SingleAICoreOrchestrator (services/ai/core/)
      intenção → agente interno → RBAC/ABAC → contexto (dossiê/doc/processo/RAG)
      → sanitização LGPD (abort) → AIProviderPolicy → ai_gateway (barreira final
      de PII + cadeia por prioridade) → provider (Ollama/Anthropic/Groq)
      → validação (citações, promessas, base verificável) → AILog → HITL → resposta
```

## 3. Anthropic — onde foi integrada

- **Apenas como provider** do `ai_gateway` (`services/providers/anthropic_provider.py`), na cadeia das tarefas complexas (`analise_juridica`, `elaboracao_peca`, `estrategia`, `analise_contrato`, `auditoria_peca`, `jurimetria`) na ordem de `AI_PROVIDER_PRIORITY`, com fallback para Groq/Ollama.
- Endurecimento: `ANTHROPIC_ENABLED` (kill-switch), `ANTHROPIC_TIMEOUT_SECONDS` (timeout do client), `ANTHROPIC_MAX_TOKENS` (teto duro de saída), erros re-lançados curtos (tipo + HTTP status, `from None`) — sem corpo, sem stack trace, sem chave.
- Sem endpoint exclusivo, sem tela Anthropic, sem cliente/prompt no frontend, sem seleção de provider pelo usuário.

## 4. Confirmação — chave não exposta

- `ANTHROPIC_API_KEY` vive exclusivamente em variável de ambiente (`.env`, gitignorado e ausente do repositório), carregada por pydantic Settings com fallback `os.getenv`.
- Varredura por padrões de chave no repositório: nenhum valor hardcoded (só o placeholder vazio de `.env.example`).
- `/ai/core/status` e `/ai/status` retornam apenas booleans de configuração. Logs e mensagens de erro não incluem a chave. Frontend sem `.env` e sem `import.meta.env` em `src`. Auditoria de segurança dedicada confirmou: "Segredos: ok".

## 5. Providers preservados

Ollama (local, soberania), Groq e Anthropic — todos ativos no gateway central, escolhidos pela `AIProviderPolicy` + `AI_PROVIDER_PRIORITY`, com `AI_EXTERNAL_PROVIDERS_ALLOWED=false` como modo "só local".

## 6. O que foi criado

- **Núcleo** (`backend/app/services/ai/`): `provider_policy.py` (AIProviderPolicy/PolicyDecision) e `core/`: `orchestrator.py` (SingleAICoreOrchestrator), `intent_classifier.py` (determinístico), `context_builder.py` (dossiê/documento/processo/RAG; cofre bloqueado; nº CNJ omitido), `agent_registry.py` (**14 agentes internos**: Case, Process, Document, LegalWriting, RAGResearch, Jurimetry, Finance, BankForensics, LicitacaoCompliance, ClientCommunication, SystemHealth, Repair, UIUX, SecurityLGPDOAB), `skill_registry.py` (**28 skills** com contrato completo; `apply_authorized_patch`/`rollback_patch` sem handler de propósito — nunca automáticas), `response_validator.py`, `hitl_policy.py`, `audit_logger.py`.
- **Endpoints centrais** (`routers/ai_core.py`): POST `/api/ai/core/{chat,task,analyze,generate,report}` + GET `{agents,skills,status}`.
- **Config**: `ANTHROPIC_ENABLED/TIMEOUT_SECONDS/MAX_TOKENS`, `AI_EXTERNAL_PROVIDERS_ALLOWED`, `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL`, `AI_REQUIRE_HITL`, `AI_PROVIDER_PRIORITY` (+ `.env.example`).
- **Frontend**: `frontend/src/lib/aiCore.ts` (client central tipado).
- **Testes**: `backend/tests/test_ai_core_nucleo.py` (35 testes).
- **9 prompts novos** de agente em `system_prompts/` (processo, jurimetria_pred, bancario, licitacao_compliance, comunicacao_cliente, seguranca_lgpd, saude_sistema, reparo_tecnico, uiux) com regras de fontes/honestidade epistêmica e vedação de segredos.

## 7. Endpoints legados como wrappers / routers e services analisados

Matriz completa em `docs/ai/EJC_AI_ENDPOINT_MIGRATION_MATRIX.md`. Destaques: `documento_ia/analisar`, `cerebro/analise-estrategica`, `prompts-biblioteca/executar`, `jurimetria/predicao-exito` viraram wrappers do orchestrator; `ai_brain.py` virou wrapper DEPRECATED do gateway central (fim do httpx direto); AILog adicionado em assistente(2), ia_especializada, prompts_juridicos, qualidade(2), conteudo(2); teses/sugestao-ia com usuário obrigatório + AILog. 28+ routers e ~25 services de IA analisados na auditoria (`EJC_SINGLE_AI_CORE_AUDIT.md` §2-3).

## 8. Telas ajustadas

- `CasoDetalhe.tsx`: prompt de comparação de contratos movido ao servidor (`modo="comparacao"`).
- `Pecas.tsx`: auditoria de peça por `peca_id` (ownership validado no backend).
- `IA.tsx`, `AgenteIA.tsx`, `AssistenteIA.tsx`: exibição do `aviso_hitl` do núcleo.
- Nenhuma tela chama provider/modelo diretamente; nenhuma chave/prompt sensível no cliente (confirmado por inventário e auditoria).

## 9. Duplicidades removidas

`docs/ai/EJC_AI_DUPLICATION_REMOVAL_REPORT.md`: dois gateways → um; lógica de IA por módulo → núcleo; decisão de provider → policy única; prompt no cliente → servidor; AILog canônico via `ai_guard` nos fluxos novos/corrigidos.

## 10. LGPD/OAB, HITL e logs

- Dupla barreira de sanitização (ai_guard com abort 422 no núcleo + barreira final no gateway para TODO provider externo, inclusive no caminho `executar_tarefa_ia` — fix P1-1).
- Documentos de cofre (confidencialidade ≥ restrito) nunca viram prompt; nº CNJ omitido do contexto; `cliente_externo` bloqueado em dupla camada; agentes técnicos restritos a superadmin/admin/socio; ownership por caso via `verificar_acesso_caso`.
- Toda resposta jurídica: `is_rascunho=True` + "Rascunho sujeito à revisão humana (HITL obrigatório — OAB)"; promessa de resultado detectada → alerta + revisão obrigatória; tarefa com fonte exigida sem âncora → "SEM BASE VERIFICÁVEL".
- AILog com prompt sanitizado, fontes RAG, tokens e custo BRL; no núcleo, falha de log derruba a chamada (sem trilha → sem resposta).
- AuthMiddleware, RBAC, ABAC, `--workers 1`, migrations e proteção `include_name` intocados. Nenhuma migration criada (zero mudança de schema).

## 11. Auditoria de segurança (independente) e correções

Agente somente-leitura auditou todo o diff vs main: **0 P0**; achados corrigidos no commit `fix(seguranca)`: P1-1 (bypass da barreira em `executar_tarefa_ia`), P2-1 (AILog fail-safe → canônico com erro propagado), P2-2 (`/ai/executar` e `/ai/status` acessíveis a cliente_externo), P2-3 (contexto de terceiros no system prompt → bloco [CONTEXTO] delimitado na mensagem de usuário + instrução anti-injection), P3-2 (max_length em `/teses-v4/sugestao-ia`). P3-1 (routers `intake`/`area_modulos`/`module_help` não montados em `main.py`) é pré-existente e fora do escopo desta consolidação.

## 12. Testes e comandos executados (Etapas 13 e 15)

| Comando | Resultado |
|---|---|
| `python3 -m pytest tests/test_ai_core_nucleo.py -x -q` (backend) | **35 passed** |
| `python3 -m pytest tests/ -q` (backend, pós-fixes) | **147 passed, 8 skipped** (skips pré-existentes gated por `RUN_DB_TESTS`/Postgres) |
| `python3 -m compileall app -q` + import `app.main` | OK |
| `npm run lint` (tsc --noEmit) | sem erros |
| `npm run build` (tsc + vite) | sucesso (5.96s) |
| `docker compose config -q` | não avaliável neste ambiente (exige `.env` local, que corretamente não existe no repositório) |
| `graphify update .` | automático via hooks a cada edição |

Cobertura de testes por cenário exigido: Anthropic on/off/sem chave, teto de tokens, bloqueio por PII, fallback local, priorização complexa/econômica, cadeia por prioridade, classificador (caso/peça/licitação/keywords/fallback), promessa de resultado, sem base verificável, HITL inegociável, 403 cliente_externo, 403 agente técnico p/ advogado, AILog fake, registries (14/28, patch nunca automático), rotas centrais.

## 13. Riscos remanescentes e pendências futuras

1. Services internos no `ai_brain` deprecado (`rag_juridico`, `motor_estrategico`, `war_room`, `sentimento_magistrado`, `minerador_sucesso`, `gatilhos_estruturais`): sanitizados e na barreira do gateway, mas **sem AILog** (sem db/user no fluxo) — migrar gradualmente para `orchestrator.run`.
2. INSERTs manuais antigos de AILog em fluxos não tocados — padronizar em `ai_guard.registrar_ai_log`.
3. `veredito_ia` é heurística rotulada como IA — renomear na UI ou migrar para `JurimetryAgent`.
4. Deprecação efetiva dos endpoints duplicados (2× detectar-prazos, 2× honorários) — decisão de produto.
5. Telas legadas continuam nos endpoints antigos (agora wrappers); migração ao `aiCore.ts` pode ser incremental.
6. Skips de teste dependentes de Postgres (`RUN_DB_TESTS=1`) devem rodar no CI com banco (job existente "Validação schema + RAG row-level").
7. Prompt injection: mitigado (contexto como dado delimitado + HITL + validador), não eliminável por construção — manter revisão humana.

## 14. Conclusão

O EJC passa a ter **uma única IA nativa** (SingleAICoreOrchestrator), governada por policy central, auditável (AILog), segura (LGPD dupla barreira, RBAC/ABAC, cofre, anti-injection), extensível (registries de agentes/skills) e integrada a todos os domínios via endpoints centrais + wrappers. Anthropic/Claude opera exclusivamente como provider do `ai_gateway`, ao lado de Ollama e Groq, com chave apenas em ambiente e custo monitorado por chamada.
