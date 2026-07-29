# EJC — Matriz de Migração de Endpoints de IA para o Núcleo Único

Data: 2026-07-04 · Branch: `claude/ejc-legal-ai-architecture-s2ctes`

Política: **nenhum endpoint legado foi removido** — os que tinham lógica própria de IA viraram **wrappers do núcleo único** (`SingleAICoreOrchestrator`) ou foram corrigidos para usar o gateway central com sanitização + AILog. Shapes de resposta antigos foram preservados; campos novos do núcleo (`log_id`, `is_rascunho`, `aviso_hitl`, `fontes`, `citacoes`, `modelo`, `provider`) foram **acrescentados** sem quebrar o frontend.

## Endpoints centrais (novos)

| Endpoint | Uso |
|---|---|
| POST `/api/ai/core/chat` | conversa/pergunta livre (CaseAgent default) |
| POST `/api/ai/core/task` | tarefa tipada (task_type + domain + IDs) |
| POST `/api/ai/core/analyze` | análise por domínio |
| POST `/api/ai/core/generate` | geração (minuta/peça/mensagem/relatório) |
| POST `/api/ai/core/report` | relatório executivo por domínio |
| GET `/api/ai/core/agents` · `/skills` · `/status` | introspecção (staff; sem prompts internos, sem valores de chave) |

Client frontend: **não existe client tipado do núcleo**. `frontend/src/lib/aiCore.ts` foi removido em 1befdf0 sem nunca ter tido consumidor; hoje todo consumo de IA do frontend passa pelo cliente axios único (`frontend/src/lib/api.ts`) chamando os endpoints legados. Migrar as telas para `/api/ai/core/*` — e só então criar o client tipado, junto do primeiro consumidor real — é pendência registrada em docs/HIGIENIZACAO_BACKLOG_FRONTEND.md.

## Matriz de migração (legado → núcleo)

| Endpoint legado | Situação anterior | Situação nova | Chamada interna |
|---|---|---|---|
| POST `/documentos-ia/analisar` | lógica própria via documento_service | **wrapper do núcleo** (diagnóstico) + OCR local preservado; degradação segura se núcleo abortar | `orchestrator.run(task_type="document_analysis", domain="documents", ...)` |
| POST `/cerebro/analise-estrategica` | gateway-sombra `ai_brain.modo_duas_ias`, sem San/AILog | **wrapper do núcleo** | `orchestrator.run(task_type="case_analysis", domain="estrategia", ...)` |
| POST `/prompts-biblioteca/{id}/executar` | gateway-sombra, sem San/AILog | **wrapper do núcleo** | `orchestrator.run(task_type="chat", usar_rag=False, ...)` |
| POST `/jurimetria/predicao-exito` | gateway-sombra `ai_brain.generate`, sem San/AILog | **wrapper do núcleo** (+ `Depends(get_db)`) | `orchestrator.run(task_type="jurimetria", ...)` |
| GET `/teses/sugestao-ia` | gateway-sombra, sem San/AILog, **sem usuário** | gateway central + `sanitizar_ou_abortar` + `registrar_ai_log` + usuário autenticado obrigatório | `ai_gateway.chat(task_type="analise_juridica")` |
| POST `/assistente/cases/{id}/chat` e `/assistente/detectar-prazos` | gateway central, **sem AILog** | AILog via `registrar_ai_log` + campos HITL | inalterado (gateway central) |
| POST `/ia-especializada/{perfil}` | sem San do input, sem AILog, fontes não estruturadas | `sanitizar_ou_abortar` + AILog + `fontes: [{titulo, categoria, fonte}]` | inalterado (gateway central) |
| POST `/prompts-juridicos/{id}/executar` | San ok, **sem AILog** | AILog + campos HITL | inalterado |
| POST `/qualidade/consistencia` e `/simular-adversario` | San ok, **sem AILog** | AILog (helper `_log`) | inalterado |
| POST `/conteudo/faq` e `/glossario` | **sem AILog** | AILog (helper `_log`) | inalterado |
| POST `/ai/caso/{id}/estrategia` | input sem San; `pii_removida=False` hardcoded | `sanitizar_pii` no input + flag real | inalterado |
| POST `/ai/analisar-contrato` | um texto apenas; prompt de comparação era montado NO FRONTEND | aceita `texto_contrato_2` + `modo="comparacao"`; prompt de comparação montado no servidor | `ai_service.analisar_contrato` estendida |
| POST `/ai/auditar-peca` | frontend buscava e reenviava o conteúdo integral da peça | aceita `peca_id` (busca `LegalDoc` com ownership via `verificar_acesso_caso`) | `ai_service.auditar_peca` |
| `core/ai_brain.py` (`processar_demanda`/`generate`/`modo_duas_ias`) | **gateway-sombra**: httpx direto ao Ollama, sem San/AILog/fallback | **wrapper DEPRECATED**: `sanitizar_pii` + delega a `services/ai_gateway.chat` (barreira PII + fallback); interface e shapes preservados p/ 16 consumidores | `ai_gateway.chat(task_type=mapeado)` |

## Endpoints que já estavam corretos (sem mudança)

`/ai/analisar-caso`, `/ai/executar` (ai_tools — padrão-ouro), `/ai/*` de ia_extra, `/ai/skills/*`, `/ia-defensiva/*`, `/pecas/gerar` (pipeline + citation_check), `/teses-v4/*`, `/rag/*`, `/validador-juridico/validar`, `/dossie/*`, `/analise-bancaria/*`, `/cases/{id}/score-juridico/calcular` — todos já usavam o gateway central com San+AILog+HITL.

## Fora de IA real (sem mudança, documentado)

- `/veredito_ia/analisar` — heurística determinística (não chama modelo). Rotulagem deve deixar claro que não é LLM.
- `/bank-analysis/*`, `/v1/licitacao-auditoria/*`, `/document-templates/*` — determinísticos.

## Gap conhecido (aceito nesta fase)

Services internos que usam o `ai_brain` deprecado sem sessão de banco (`rag_juridico`, `motor_estrategico`, `war_room`, `sentimento_magistrado`, `minerador_sucesso`, `gatilhos_estruturais`) agora passam pelo gateway central com sanitização e barreira PII, mas **não gravam AILog** (não têm `db/user` no fluxo). Migração completa desses services para `orchestrator.run` é pendência futura (ver relatório final).
