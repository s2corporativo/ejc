# EJC — Auditoria da IA Existente (Núcleo Único de IA)

Data: 2026-07-04 · Branch: `claude/ejc-legal-ai-architecture-s2ctes`
Escopo: inventário completo da superfície de IA do EJC (backend FastAPI + frontend React) antes da consolidação em um núcleo único de IA nativa.

> **Nota de atualização (2026-07-27)** — documento histórico (retrato de 2026-07-04). O plano da Etapa 9 (§7) previa um client `aiCore` no frontend: ele chegou a ser criado (`frontend/src/lib/aiCore.ts`) mas **nunca teve um consumidor** e foi removido em 1befdf0. As telas de IA continuam nos endpoints legados; ver a pendência em `docs/HIGIENIZACAO_BACKLOG_FRONTEND.md`.
>
> **Nota de atualização (2026-08)** — o provider Ollama (IA local) foi REMOVIDO do EJC (Issue #761): já vinha desligado em produção (`OLLAMA_ENABLED=false`, último da cadeia) e sem uso real. O `_call_ollama` do gateway-sombra (§1, linha 14) também foi removido — o shim `core/ai_brain.py` hoje só delega ao gateway central. O `EJC não tem mais provider local`; a cadeia atual é `anthropic → maritaca → groq`. As referências a Ollama abaixo retratam o estado em 2026-07-04 (histórico).

---

## 1. Arquitetura atual da IA (situação encontrada)

O EJC possui um gateway central legítimo — `backend/app/services/ai_gateway.py` — que já implementa o princípio "nenhuma tela acessa modelo diretamente": roteamento por tipo de tarefa, cadeia de fallback e três providers plugáveis em `backend/app/services/providers/` (Ollama local, Groq, Anthropic/Claude). O módulo profissional `executar_tarefa_ia()` (ai_gateway.py:329) já entrega HITL (`is_rascunho/requer_revisao`), custo estimado em BRL e registro em `ai_logs`.

**Porém existe um segundo gateway-sombra**: `backend/app/core/ai_brain.py` (classe `AIGateway`, singletons `ai_gateway`/`ai_brain`), que chama Ollama **diretamente via httpx** (`_call_ollama`, ai_brain.py:29-46), fora da camada `providers/`, sem AILog, sem sanitização embutida e sem fallback. Cerca de 16 pontos do sistema o consomem.

```
Fluxo correto (majoritário):
frontend → /api/... → router → service → services/ai_gateway → providers/{ollama,groq,anthropic} → AILog/HITL

Fluxo-sombra (a eliminar):
frontend → /api/... → router → core/ai_brain → httpx → Ollama   (sem AILog, sem sanitização, sem fallback)
```

## 2. Routers de IA encontrados (registrados em `main.py`, prefixo global `/api`)

Nenhuma rota de IA é pública — `AuthMiddleware` (main.py:215) cobre tudo; whitelist pública em `core/auth_middleware.py:21-34` contém apenas auth/health/docs/webhooks.

| Router | Prefixo | Endpoints de IA | Gateway | Sanitização | AILog | HITL |
|---|---|---|---|---|---|---|
| `ai.py` | `/ai` | analisar-caso, dossie, resumir-documento, teses-ocultas, auditar-peca, preparar-audiencia, assistente, dual, estrategia, analisar-contrato, detectar-prazos, logs (HITL) | central | ✔ (exceto `estrategia`: `pii_removida=False` hardcoded, ai.py:646) | ✔ | ✔ |
| `ai_tools.py` | `/ai` | executar (`executar_tarefa_ia` — pipeline padrão-ouro) | central | ✔ `sanitizar_ou_abortar` | ✔ | ✔ |
| `ia_extra.py` | `/ai` | traduzir-andamento, resumir-texto, gerar-minuta, pesquisar, sugestao-honorarios | central | ✔ | ✔ | ✔ |
| `ai_skills.py` | `/ai/skills` | list, execute, execute-doc | central | ✔ | ✔ | ✔ |
| `assistente.py` | `/assistente` | chat por caso, detectar-prazos | central | ✔ | **✘** | parcial |
| `cerebro.py` | `/cerebro` | analise-estrategica (`modo_duas_ias`) | **sombra** | **✘** | **✘** | **✘** |
| `documento_ia.py` | `/documentos-ia` | analisar → `documento_service` | central | ✔ | ✔ | ✔ |
| `ia_defensiva.py` | `/ia-defensiva` | analisar, historico (HITL) | central | ✔ | ✔ | ✔ |
| `ia_especializada.py` | `/ia-especializada` | {perfil} | central | parcial (não sanitiza a pergunta) | **✘** | **✘** |
| `ia_governanca.py` | `/ia-governanca` | dashboards/curadoria (sem chamada de modelo) | — | — | — | — |
| `ia_saude.py` | `/ia-saude` | dashboards de uso/custo (leitura de AILog) | — | — | — | — |
| `rag.py` | `/rag` | ingest*, buscar, match-casos, monitor-legislativo, ingerir-ai-log | central + embeddings | ✔ | ✔ | ✔ |
| `peca_geracao.py` | `/pecas` | gerar (pipeline 6 etapas + `citation_check`) | central | ✔ | ✔ | ✔ |
| `prompts.py` | `/prompts-biblioteca` | {id}/executar | **sombra** | **✘** | **✘** | **✘** |
| `prompts_juridicos.py` | `/prompts-juridicos` | {id}/executar | central | ✔ | **✘** | **✘** |
| `jurimetria.py` | `/jurimetria` | predicao-exito (demais são SQL analítico) | **sombra** | **✘** | **✘** | **✘** |
| `teses.py` | `/teses` | sugestao-ia | **sombra** | **✘** | **✘** | **✘** |
| `teses_v4.py` | `/teses-v4` | sugerir-teses, analise (padrão-ouro `ai_guard`) | central | ✔ | ✔ | ✔ |
| `qualidade.py` | `/qualidade` | verificar-citacoes, consistencia, simular-adversario | central | ✔ | **✘** | **✘** |
| `conteudo.py` | `/conteudo` | faq, glossario | central | ✔ | **✘** | — |
| `score_juridico.py` | `/cases/{id}/score-juridico` | calcular | central | ✔ | ✔ | ✔ |
| `analise_bancaria.py` | `/analise-bancaria` | contrato, modalidades, taxa-media | central | ✔ | ✔ | ✔ |
| `bank_analysis.py` | `/bank-analysis` | upload/parse (determinístico, sem LLM) | — | — | — | — |
| `licitacao_auditoria.py` | `/v1/licitacao-auditoria` | analyze-competitor-proposal (determinístico) | — | — | — | — |
| `veredito_ia_router.py` | `/veredito_ia` | analisar — **"IA" simulada** (heurística, core/veredito_ia.py:29-50) | — | — | — | rótulo enganoso |
| `validador_juridico.py` | `/validador-juridico` | validar | central | ✔ | ✔ | ✔ |
| `dossie_estrategico.py` | `/dossie` | gerar + aprovar (HITL) | central | ✔ | ✔ | ✔ |
| outros (`cases.py:579`, `clients.py:278`, `intelligence_v3.py:32`, `curadoria_renomada.py`, `jurisprudencia_interna.py`, `honorarios_oab.py`, `conversao_caso.py`, `legal_docs.py`, `movimentos.py`) | — | usos pontuais | misto (4 na sombra) | misto | misto | misto |

## 3. Services de IA

- **Usam o gateway central** (`ai_gateway.chat`/`executar_tarefa_ia`): `ai_service` (inclui `buscar_contexto_rag` — ponto único de recuperação RAG com escopo por cliente), `peca_service` (pipeline + `citation_check`), `case_intel`, `analise_estrategica`, `ai_skill_service`, `checklist_ia`, `movimento_ia`, `documento_service`, `dossie_service`, `visual_law`, `validador_juridico_service`, `ia_defensiva_service`.
- **Usam o gateway-sombra** (`core.ai_brain`): `rag_juridico`, `gatilhos_estruturais`, `sentimento_magistrado`, `minerador_sucesso`, `motor_estrategico`, `war_room` — e os routers `cerebro`, `prompts`, `jurimetria`, `teses`, `intelligence_v3`, `curadoria_renomada`, `cases`, `clients`, `rag` (import pontual).
- **RAG/embeddings/ingestão**: `embedding_service` (768 dims, pgvector), `embeddings_api`, `ingestion_service`, `sumulas_ingestion`, `ingestors/`, `rag_juridico`.
- **Guardas**: `sanitizer.py` (regex CPF/CNPJ/processo/RG/e-mail/telefone/CEP/cartão/PIX), `ai_guard.py` (2ª barreira com abort 422 + AILog que propaga erro), `citation_check.py` (anti-alucinação por lookup exato no RAG), `case_context.py` (dossiê sanitizado), `pii_crypto`, `client_anonimizacao`.

## 4. Telas React consumidoras de IA

Inventário completo em §2 do relatório de frontend: `IA.tsx`, `CasoDetalhe.tsx`, `Pecas.tsx`, `AssistenteIA.tsx`, `AgenteIA.tsx`, `FerramentasIA.tsx`, `ramos/RamoBase.tsx`, `Conhecimento.tsx`, `KnowledgeHub.tsx`, `GovernancaIA.tsx`, `Jurimetria.tsx`, `DashboardIA.tsx`, `Prompts.tsx`, `Noticias.tsx`, `LicitacaoAuditoria.tsx`, `ExplicarMov.tsx`, `VeredutoIAWithVictoryVault.tsx`, `MemoriaInstitucional.tsx`, `Biblioteca.tsx`.

**Resultado positivo**: nenhuma tela chama Anthropic/Groq/Ollama diretamente; nenhuma chave no bundle (não há `.env` de frontend nem `import.meta.env` em `src`); nenhuma seleção de provider/modelo na UI; portal do cliente (`cliente_externo`) não consome nenhum endpoint de IA.

**Desvios encontrados**:
1. `CasoDetalhe.tsx:2961` — único prompt jurídico montado no navegador (comparação de contratos) e injetado em `texto_contrato`.
2. `Pecas.tsx:250-258` — busca o conteúdo integral da peça e reenvia ao `/ai/auditar-peca` (o backend deveria receber só o ID).
3. Não há client central de IA em `lib/api.ts` — cada página chama endpoints inline (20+ paths distintos).

## 5. Providers atuais

| Provider | Onde | Estado |
|---|---|---|
| Ollama (local) | `services/providers/ollama_provider.py` | `OLLAMA_ENABLED` default False; modelos por tarefa via env |
| Groq | `services/providers/groq_provider.py` | via `GROQ_API_KEY`; sanitização LGPD obrigatória documentada |
| Anthropic/Claude | `services/providers/anthropic_provider.py` | integrado ao gateway; ver §6 |
| Ollama direto (indevido) | `core/ai_brain.py:29-46` | httpx direto — a eliminar |

## 6. Estado da Anthropic

- Chave: **presente com o nome esperado** `ANTHROPIC_API_KEY`, carregada pela `Settings` tipada (core/config.py:67, pydantic + `.env`) com fallback `os.getenv` no provider. `.env` está gitignorado e ausente do repositório; **nenhum valor hardcoded** (varredura por padrão de chave só encontrou o placeholder vazio de `.env.example`). **Não exposta ao frontend** (sem variável `VITE_*`, sem chave no bundle).
- Modelos configuráveis: `ANTHROPIC_MODEL_RAPIDO`/`ANTHROPIC_MODEL_COMPLEXO` (defaults Haiku, econômicos).
- Roteamento por tarefa: `services/system_prompts/router.py` (TarefaIA → provider/modelo/max_tokens/temperature) com fallback Groq quando Claude indisponível.
- Custo: estimado em BRL por chamada (`ai_gateway._custo_brl`) e gravado em `ai_logs`.
- Lacunas (corrigidas na consolidação): faltavam `ANTHROPIC_ENABLED`, `ANTHROPIC_TIMEOUT_SECONDS`, `ANTHROPIC_MAX_TOKENS` e as flags de governança `AI_EXTERNAL_PROVIDERS_ALLOWED`, `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL`, `AI_REQUIRE_HITL`, `AI_PROVIDER_PRIORITY`; o provider não aplicava timeout nem teto de tokens.

## 7. Duplicidades

1. **Dois gateways** — `services/ai_gateway.py` (correto) × `core/ai_brain.py` (sombra).
2. **AILog escrito por 3 caminhos** — SQL cru no gateway (ai_gateway.py:314), helper ORM `ai_guard.registrar_ai_log` (canônico) e `AILog(...)` manuais espalhados.
3. **"Análise de caso" por 6 caminhos** — `/ai/analisar-caso`, `/ai/executar`, `/cerebro/analise-estrategica`, `case_intel.triagem_caso`, `analise_estrategica.analisar_caso`, `/teses-v4/analise`.
4. **Dois "detectar-prazos"** (`ai.py:682` e `assistente.py:88`); **duas análises de contrato** (`/ai/analisar-contrato` e `/analise-bancaria/contrato`); **duas sugestões de honorários** (`ia_extra` e `honorarios_oab`); **três geradores de peça/minuta** (`peca_service` pipeline, `/ai/gerar-minuta`, templates determinísticos).
5. Três routers diferentes compartilham o prefixo `/ai` (`ai.py`, `ai_tools.py`, `ia_extra.py`).

## 8. Riscos (ordem de prioridade)

- **P0 — Gateway-sombra sem LGPD**: `cerebro`, `prompts`, `jurimetria`, `teses` (+6 services) enviam conteúdo ao modelo **sem sanitização e sem AILog** via `core/ai_brain`.
- **P1 — Endpoints sem AILog**: `assistente` (2), `ia_especializada`, `prompts_juridicos`, `qualidade` (2), `conteudo` (2), além dos P0.
- **P1 — `ai.py:/caso/{id}/estrategia`**: `pii_removida=False` hardcoded e input sem `sanitizar_pii`.
- **P2 — RAG sem fontes ao cliente**: `ia_especializada`, `conteudo`, `honorarios_oab`, `qualidade` usam RAG mas não devolvem fontes estruturadas; `citation_check` aplicado só em `peca_service`, `analise_estrategica` e `qualidade`.
- **P2 — HITL ausente no payload** dos fluxos-sombra (sem `is_rascunho/requer_revisao`).
- **P3 — Rótulo enganoso**: `veredito_ia` é heurística simulada apresentada como IA.
- **P3 — Prompt no cliente**: `CasoDetalhe.tsx:2961`; conteúdo integral de peça trafegando pelo browser (`Pecas.tsx`).

## 9. Lacunas de governança

- Sem política central de seleção de provider (decisão espalhada entre `TASK_ROUTING`, `system_prompts/router.py` e `AI_PROVIDER`).
- Sem barreira final de PII no gateway antes de provider externo (cada endpoint depende da própria disciplina).
- Sem registro central de agentes/skills; sem classificador de intenção; sem validador de resposta unificado (promessa de resultado / "sem base verificável").

## 10. Plano de consolidação para o núcleo único

1. **Etapa 2** — padronizar config Anthropic + flags de governança (`ANTHROPIC_ENABLED/TIMEOUT/MAX_TOKENS`, `AI_EXTERNAL_PROVIDERS_ALLOWED`, `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL`, `AI_REQUIRE_HITL`, `AI_PROVIDER_PRIORITY`).
2. **Etapas 3-4** — endurecer `anthropic_provider` (timeout, teto de tokens, erros sem stack trace); criar `services/ai/provider_policy.py` (AIProviderPolicy) e barreira final de PII no `ai_gateway` para providers externos; incluir Anthropic na cadeia de roteamento das tarefas complexas.
3. **Etapas 5-7** — criar `services/ai/core/` (SingleAICoreOrchestrator + intent_classifier + context_builder + agent_registry com 14 agentes internos + skill_registry com 28 skills + response_validator + hitl_policy + audit_logger), integrando sanitizer/ai_guard/citation_check/case_context/rag/AILog.
4. **Etapa 8** — router `/api/ai/core/{chat,task,analyze,generate,report}`; endpoints legados viram wrappers do núcleo; `core/ai_brain.py` reescrito como wrapper deprecado que delega ao gateway central (elimina o httpx direto preservando os 16 consumidores).
5. **Etapa 9** — client `aiCore` em `lib/api.ts`; migrar prompt de comparação de contratos para o backend; `auditar-peca` por ID.
6. **Etapas 12-15** — regras rígidas preservadas (LGPD/OAB/HITL/RBAC/ABAC), testes, documentação e validação final.

---
*Gerado durante a consolidação do Núcleo Único de IA. Complementos: `EJC_SINGLE_AI_CORE_ARCHITECTURE.md`, `EJC_AI_ENDPOINT_MIGRATION_MATRIX.md`, `EJC_AI_DUPLICATION_REMOVAL_REPORT.md`.*
