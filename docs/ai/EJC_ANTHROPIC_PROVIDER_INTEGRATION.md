# EJC — Integração Anthropic/Claude (provider do gateway, nada além)

Data: 2026-07-04.

Anthropic entra no EJC **exclusivamente como um provider plugável do `ai_gateway`** (`backend/app/services/providers/anthropic_provider.py`), com o mesmo contrato de Ollama/Groq: `chat(messages, model, temperature, max_tokens) -> (texto, usage_dict)`. Não existe endpoint, service ou tela "da Anthropic".

## 1. Variáveis de ambiente (core/config.py:67-78; .env.example:17-29)

| Variável | Default | Efeito |
|---|---|---|
| `ANTHROPIC_API_KEY` | vazio | Chave. Sem ela o provider levanta erro claro e o gateway segue a cadeia (anthropic_provider.py:41) |
| `ANTHROPIC_ENABLED` | `true` | Kill-switch sem remover a chave (anthropic_provider.py:35,74) |
| `ANTHROPIC_TIMEOUT_SECONDS` | `120` | Timeout do client (anthropic_provider.py:44) |
| `ANTHROPIC_MAX_TOKENS` | `8000` | Teto DURO de saída: `mt = min(max_tokens_do_chamador, ANTHROPIC_MAX_TOKENS)` (anthropic_provider.py:80) |
| `ANTHROPIC_MODEL_RAPIDO` | `claude-haiku-4-5-20251001` | Tarefas factuais/médias (system_prompts/router.py:11) |
| `ANTHROPIC_MODEL_COMPLEXO` | `claude-haiku-4-5-20251001` | Tarefas complexas; subir para `claude-sonnet-4-6` via .env quando quiser mais qualidade (router.py:13) |

A chave vive **somente** no `.env`/ambiente do processo (Settings pydantic + fallback `os.getenv`, anthropic_provider.py:23-26). Jamais é logada, ecoada em erro, gravada em AILog ou exposta em endpoint — `/ai/core/status` devolve só booleans (`bool(s.ANTHROPIC_ENABLED and s.ANTHROPIC_API_KEY)`, ai_core.py:189). Não há variável `VITE_*` nem chave no bundle do frontend.

## 2. Endurecimento do provider (anthropic_provider.py)

- Client lazy: SDK importado só no uso; instanciado apenas com chave presente (linhas 33-46).
- `ANTHROPIC_ENABLED=false` → `RuntimeError` imediato antes de qualquer rede (linhas 35-36, 74-75).
- Conversão OpenAI→Anthropic: mensagens `system` viram parâmetro `system`; garante ≥1 mensagem de usuário (`_split_system`, linhas 49-63).
- Erros da API re-lançados como `RuntimeError` CURTO — tipo + status HTTP, **sem stack trace, sem corpo de resposta, sem chave**; `from None` corta a cadeia original (linhas 90-97).
- SDK síncrono executado em `asyncio.to_thread` para não bloquear o event loop (linha 100).
- `usage` devolve `model`, `input_tokens`, `output_tokens` — insumo do custo/auditoria.

## 3. Posição na cadeia por tarefa

Dois caminhos, ambos dentro do gateway:

1. **`ai_gateway.chat` (Núcleo Único)** — `TASK_ROUTING` (ai_gateway.py:76-118) inclui `anthropic` em TODAS as tarefas, inclusive `resumo`/`chat_rapido` (política do escritório, 2026-07-26 — qualidade acima de custo; ver `EJC_AI_PROVIDER_POLICY.md`). A ordem final respeita `AI_PROVIDER_PRIORITY` (default `ollama,anthropic,maritaca,groq`) + a promoção do roteamento inteligente (`model_router.py`, `ROTEAMENTO_PROVIDER_LEVE/MEDIO/PESADO=anthropic` por padrão) filtrada por elegibilidade (`_resolver_cadeia`, ai_gateway.py:309-330; `_provider_elegivel`, linhas 272-283: exige `ANTHROPIC_ENABLED` + chave + `AI_EXTERNAL_PROVIDERS_ALLOWED`). Modelo: sempre `ANTHROPIC_MODEL_COMPLEXO` neste caminho, qualquer tarefa/tier (`_resolver_modelo`, linhas 303-305).
2. **`executar_tarefa_ia` (módulo por tarefa)** — `system_prompts/router.py` define provider/modelo por `TarefaIA`: todas as tarefas usam Anthropic/COMPLEXO (antes triagem/resumo usavam Groq "rota econômica" e prazos/honorários/audiência/rag_query usavam Claude Haiku — ambos revogados em 2026-07-26). Groq/Ollama seguem só como fallback na composição da cadeia.

**Fallback**: no `chat`, falha de um provider registra motivo curto e tenta o próximo da cadeia (ai_gateway.py:235-240); em `executar_tarefa_ia`, Anthropic indisponível → fallback explícito para Groq (ai_gateway.py:424-431).

## 4. Custo BRL

`_custo_brl` (ai_gateway.py:387-390) aplica pricing USD/1M tokens por modelo (`_PRICING_USD_MM`, linhas 380-384: haiku-4-5, sonnet-4-6, opus-4-8) × `USD_BRL_RATE` (env, default 5.70). Calculado apenas quando `provedor == "anthropic"` (Ollama/Groq custam 0) e gravado em `ai_logs.custo_estimado` (orchestrator.py:153-154, 168). `ANTHROPIC_MAX_TOKENS` é o teto duro de gasto por chamada, independente do chamador. Detalhes em `EJC_AI_COST_AND_AUDIT_POLICY.md`.

## 5. Barreira LGPD (obrigatória)

Anthropic é provider EXTERNO (`_PROVIDERS_EXTERNOS`, ai_gateway.py:121; provider_policy.py:19). Com `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=true`, o gateway sanitiza cada mensagem e, havendo PII residual, **pula a Anthropic** e tenta o próximo provider — nunca ecoando o conteúdo, só os tipos de PII (ai_gateway.py:192-207, 333-347). A `AIProviderPolicy` aplica a mesma regra antes, no núcleo (dupla barreira).

## 6. Onde a Anthropic aparece (superfície completa)

| Ponto | Papel | Referência |
|---|---|---|
| `providers/anthropic_provider.py` | Único código que fala com a API | todo o arquivo |
| `ai_gateway.TASK_ROUTING` / `_resolver_cadeia` | Posição na cadeia por tarefa | ai_gateway.py:76-118, 309-330 |
| `ai_gateway._PRICING_USD_MM` / `_custo_brl` | Custo BRL por chamada | ai_gateway.py:380-390 |
| `provider_policy.AIProviderPolicy` | Elegibilidade + priorização de tarefas complexas | provider_policy.py:51-55, 113-115 |
| `system_prompts/router.py` | Provider/modelo por TarefaIA (caminho legado) | router.py:53-72 |
| `ai_gateway.health` / `/ai/core/status` | Disponibilidade (booleans apenas) | ai_gateway.py:254-267; ai_core.py:189 |

Qualquer outro uso é desvio de arquitetura e deve ser tratado como incidente.

## 7. PROIBIDO

- Endpoint exclusivo da Anthropic ou rota que a chame fora de `ai_gateway`/`providers/`.
- Chave, prompt ou seleção de modelo no frontend (o frontend envia intenção/IDs; `lib/aiCore.ts` não conhece providers).
- Import de `anthropic` fora de `providers/anthropic_provider.py`.
- Logar/retornar a chave ou o corpo de erro da API (o provider já reduz o erro a tipo+status).
- Enviar conteúdo não sanitizado: a barreira final do gateway não é contornável por parâmetro.
