# EJC — Política de Custo e Auditoria da IA

Data: 2026-07-04 · Código: `backend/app/services/ai_gateway.py`, `backend/app/models/ai_log.py`, `backend/app/routers/{ia_saude,ia_governanca}.py`.

## 1. Cálculo de custo — `_custo_brl` (ai_gateway.py:387-390)

```python
usd = (input_tokens * preco_input + output_tokens * preco_output) / 1_000_000
brl = round(usd * float(os.getenv("USD_BRL_RATE", "5.70")), 4)
```

Pricing por modelo (`_PRICING_USD_MM`, ai_gateway.py:380-384, USD por 1M tokens):

| Modelo | Input | Output |
|---|---|---|
| claude-haiku-4-5-20251001 | 0.80 | 4.00 |
| claude-sonnet-4-6 | 3.00 | 15.00 |
| claude-opus-4-8 | 15.00 | 75.00 |

Modelo fora da tabela → custo 0 (atualizar `_PRICING_USD_MM` ao adotar novo modelo). Câmbio via env `USD_BRL_RATE` (default 5.70). O custo só é calculado quando `provedor == "anthropic"` (orchestrator.py:153-154; ai_gateway.py:435) — Ollama local e Groq contam como 0. Skill de introspecção: `estimate_ai_cost` (skill_registry.py:152-154).

## 2. Tetos duros de custo

- **`ANTHROPIC_MAX_TOKENS`** (default 8000, config.py:78): teto DURO de saída aplicado dentro do provider — `mt = min(max_tokens_do_chamador, ANTHROPIC_MAX_TOKENS)` (anthropic_provider.py:80). Nenhum chamador consegue exceder.
- **`ANTHROPIC_TIMEOUT_SECONDS`** (default 120): corta chamadas penduradas (anthropic_provider.py:44).
- **`ANTHROPIC_ENABLED=false`**: kill-switch imediato de gasto sem apagar a chave (anthropic_provider.py:35,74).
- Modelos default econômicos: RAPIDO e COMPLEXO em Haiku; Sonnet é opt-in via `.env` (config.py:69-71).
- Orçamentos de contexto do núcleo limitam input: dossiê ≤8000 chars, documento ≤6000, chunk RAG ≤900 ×6 (context_builder.py:16-19).

## 3. O que é gravado em `ai_logs` (models/ai_log.py:45-78)

Toda interação do núcleo grava, via `audit_logger.registrar` → `ai_guard.registrar_ai_log`:

| Coluna | Conteúdo |
|---|---|
| `user_id`, `case_id`, `tipo_uso`, `created_at` | Quem, para qual caso, para quê, quando |
| `modelo` | Forma canônica `provedor/modelo` (normalizada no ORM, `normalizar_modelo_ia`, ai_log.py:15-27,74-78) |
| `prompt_sanitizado` (≤8000), `pii_removida` | LGPD: só o prompt SEM PII |
| `resposta` | Conteúdo validado entregue ao usuário |
| `fontes_rag` | **Rastreabilidade RAG**: títulos/categorias dos chunks usados (≤20 fontes, ≤2000 chars; sem conteúdo — audit_logger.py:33-42) |
| `tokens_input`, `tokens_output` | Consumo real informado pelo provider |
| `custo_estimado` (Numeric 12,6) | BRL de `_custo_brl` |
| `status_hitl`, `revisado_por`, `revisado_em` | Ciclo HITL |

**Gravação é obrigatória**: no núcleo, erro de INSERT propaga — sem trilha, sem resposta (ai_guard.py:53-57; skill `log_ai_interaction` marcada "crítico se omitida", skill_registry.py:147-151). O caminho legado `_registrar_ai_log` (ai_gateway.py:393-405) ainda é fail-safe (warning) — usar o caminho canônico em código novo.

## 4. Dashboards

- **`GET /api/ia-saude/dashboard`** (ia_saude.py:26-62): agrega AILog — volume, `custo_total_brl` (soma de `custo_estimado`, linhas 41-42, 57), distribuição `por_status_hitl`, modelos; `GET /ia-saude/estado-operacional` (linha 67) expõe as flags operacionais. Somente leitura.
- **`GET /api/ia-governanca/*`** (ia_governanca.py): governança/curadoria — status HITL por período (linha 218), aproveitamento de respostas `revisado/aplicado` (linha 247), pendências `status_hitl='gerado'` (linha 385).

## 5. Procedimento em custo anômalo

1. **Conter**: `ANTHROPIC_ENABLED=false` (para o gasto na hora, cadeia cai para Ollama/Groq) e/ou reduzir `ANTHROPIC_MAX_TOKENS`; alternativa branda: `ANTHROPIC_MODEL_COMPLEXO=claude-haiku-4-5-20251001`.
2. **Diagnosticar**: consultar `ai_logs` por `custo_estimado`/`tokens_output` desc — identificar user_id, case_id, tipo_uso, modelo e horário; conferir `fontes_rag`/`prompt_sanitizado` para contexto inflado; usar `/ia-saude/dashboard` para a série por período.
3. **Verificar configuração**: `USD_BRL_RATE` correto; `_PRICING_USD_MM` atualizado para os modelos em uso; `AI_PROVIDER_PRIORITY` ainda com `ollama` à frente; `TAREFAS_ECONOMICAS` não roteando para Anthropic.
4. **Corrigir a causa**: endpoint/agente que envia contexto além do orçamento, laço de reprocessamento, ou tarefa simples mapeada como complexa (`_TAREFA_PARA_GATEWAY`/`TAREFAS_COMPLEXAS`).
5. **Registrar**: decisão e ajuste documentados; o AILog é a fonte de verdade da reconstrução do gasto (nunca apagar registros).

## 6. Limitações conhecidas

- `custo_estimado` é ESTIMATIVA (pricing estático × câmbio de env), não fatura — conciliar periodicamente com o console da Anthropic.
- Groq é tratado como custo 0 (plano gratuito; campos `GROQ_PRECO_*_BRL_POR_MILHAO` existem em config.py:137-138 para quando isso mudar).
- Chamadas sem `db`/`user` (internas) não geram AILog (`audit_logger.registrar` retorna None, audit_logger.py:60-66) — o orchestrator só aceita isso quando não há sessão disponível.
