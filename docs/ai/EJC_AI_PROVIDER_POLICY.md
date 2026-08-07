# EJC — AIProviderPolicy (política central de provedores)

Data: 2026-07-04 (atualizado 2026-08 — remoção do Ollama local) · Código: `backend/app/services/ai/provider_policy.py`.

A `AIProviderPolicy` (provider_policy.py:43) decide, ANTES de qualquer chamada de modelo: quais providers são elegíveis, em que ordem tentar, se o conteúdo exige sanitização para destino externo e se a chamada é permitida. É **decisão pura** — não chama modelo; o despacho continua no `ai_gateway`.

## 1. Entrada e saída

```python
AIProviderPolicy().avaliar(texto_completo, task_type, *,
                           ja_sanitizado=False, exige_fonte=False) -> PolicyDecision
```

`PolicyDecision` (provider_policy.py:32-40):

| Campo | Significado |
|---|---|
| `permitido: bool` | False = chamada bloqueada |
| `provider_chain: list[(provider, model|None)]` | Ordem de tentativa; model=None (o gateway resolve por tarefa) |
| `sanitizar_antes: bool` | Destino externo na cadeia exige conteúdo sanitizado |
| `motivo: str` | Justificativa da decisão (auditável) |
| `requer_hitl: bool` | Espelha `AI_REQUIRE_HITL` |
| `requer_fonte: bool` | Propaga `exige_fonte` do agente |
| `bloqueio_motivo: str|None` | Mensagem SEGURA de bloqueio (nunca ecoa conteúdo/valores de PII) |

O orchestrator invoca a policy após a sanitização do input (`ja_sanitizado=True`) e converte `permitido=False` em HTTP 422 com `bloqueio_motivo` (orchestrator.py:115-122).

## 2. Elegibilidade por provider (`_elegivel`, provider_policy.py)

| Provider | Condição |
|---|---|
| `anthropic` | `ANTHROPIC_ENABLED` + `ANTHROPIC_API_KEY` + `AI_EXTERNAL_PROVIDERS_ALLOWED` |
| `maritaca` | `MARITACA_ENABLED` + `MARITACA_API_KEY` + `AI_EXTERNAL_PROVIDERS_ALLOWED` |
| `groq` | `GROQ_API_KEY` + `AI_EXTERNAL_PROVIDERS_ALLOWED` |
| outros | sempre False |

`AI_EXTERNAL_PROVIDERS_ALLOWED=false` desliga TODOS os externos de uma vez — e, sem provider local (o EJC não tem um), a cadeia fica vazia (soberania de dados = IA indisponível, não IA local).

## 3. Ordem base — `AI_PROVIDER_PRIORITY`

CSV em Settings (default `anthropic,maritaca,groq`). `_ordem_prioridade` (provider_policy.py) deduplica e normaliza; vazio → fallback `["anthropic","maritaca","groq"]`. Cadeia base = prioridade filtrada por elegibilidade.

## 4. Priorização por perfil de tarefa (provider_policy.py)

- `TAREFAS_COMPLEXAS` = {analise_caso, minutas, dossie, pesquisa_juridica, estrategia, analise_juridica, elaboracao_peca} → se Anthropic elegível, vai para a FRENTE da cadeia ("tarefa complexa — Anthropic priorizado"); sem Anthropic, Maritaca (Sabiá) é priorizada entre os externos.
- `TAREFAS_ECONOMICAS` = {resumo, triagem, chat_rapido} → Groq à frente (custo ~zero).
- Aceita tanto nomes de `TarefaIA` quanto task_types do gateway.

## 5. Barreira LGPD (provider_policy.py)

Se há externo elegível e `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=true`:
1. `sanitizar_antes=True`; se `ja_sanitizado=False`, aplica `sanitizar_pii` internamente;
2. `validar_sem_pii` checa residual (CPF/CNPJ/processo/RG/e-mail/telefone/CEP);
3. residual encontrado → **externos removidos da cadeia** (não há provider local no EJC, então a cadeia normalmente fica vazia); motivo registra apenas os TIPOS de PII;
4. cadeia vazia → `permitido=False` com `bloqueio_motivo` seguro: conteúdo com dados pessoais não pode ir a provider externo e não há processamento local disponível — remova os dados pessoais do texto e tente novamente. O conteúdo jamais é ecoado.

## 6. Dupla barreira

A policy decide no núcleo, mas o `ai_gateway` **não confia** nessa decisão: antes de despachar a cada provider externo ele re-sanitiza toda mensagem e pula o provider se sobrar PII (`_sanitizar_messages_externo` + loop). Se todos os externos forem pulados por PII, o gateway falha com mensagem segura. Regras de elegibilidade são idênticas nos dois pontos (`_provider_elegivel`, ai_gateway.py).

## 7. Roteamento recomendado por cenário

| Cenário | Cadeia resultante | Por quê |
|---|---|---|
| Análise de caso/minuta/dossiê, conteúdo limpo | anthropic → maritaca → groq | Tarefa complexa prioriza Claude (MODEL_COMPLEXO) |
| Resumo/triagem/chat rápido | maritaca → groq | Econômicas; Anthropic nem entra no TASK_ROUTING de resumo/chat |
| Qualquer tarefa com PII residual após sanitização | (vazia) → HTTP 422 | Externos removidos (LGPD) e não há provider local |
| `AI_EXTERNAL_PROVIDERS_ALLOWED=false` | (vazia) → HTTP 422 | Modo soberania total (sem IA local no EJC) |
| `ANTHROPIC_ENABLED=false` (kill-switch) | maritaca → groq | Claude fora sem apagar a chave |
