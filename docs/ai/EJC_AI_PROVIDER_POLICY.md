# EJC — AIProviderPolicy (política central de provedores)

Data: 2026-07-04 · Código: `backend/app/services/ai/provider_policy.py`.

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

## 2. Elegibilidade por provider (`_elegivel`, provider_policy.py:46-58)

| Provider | Condição |
|---|---|
| `ollama` | `OLLAMA_ENABLED` |
| `anthropic` | `ANTHROPIC_ENABLED` + `ANTHROPIC_API_KEY` + `AI_EXTERNAL_PROVIDERS_ALLOWED` |
| `groq` | `GROQ_API_KEY` + `AI_EXTERNAL_PROVIDERS_ALLOWED` |
| outros | sempre False |

`AI_EXTERNAL_PROVIDERS_ALLOWED=false` desliga TODOS os externos de uma vez (soberania de dados).

## 3. Ordem base — `AI_PROVIDER_PRIORITY`

CSV em Settings (default `ollama,anthropic,groq`, config.py:92). `_ordem_prioridade` (provider_policy.py:60-68) deduplica e normaliza; vazio → fallback `["ollama","anthropic","groq"]`. Cadeia base = prioridade filtrada por elegibilidade.

## 4. Priorização por perfil de tarefa (provider_policy.py:21-29, 112-119)

- `TAREFAS_COMPLEXAS` = {analise_caso, minutas, dossie, pesquisa_juridica, estrategia, analise_juridica, elaboracao_peca} → se Anthropic elegível, vai para a FRENTE da cadeia ("tarefa complexa — Anthropic priorizado").
- `TAREFAS_ECONOMICAS` = {resumo, triagem, chat_rapido} → Ollama/Groq à frente (custo ~zero).
- Aceita tanto nomes de `TarefaIA` quanto task_types do gateway.

## 5. Barreira LGPD (provider_policy.py:95-110)

Se há externo elegível e `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=true`:
1. `sanitizar_antes=True`; se `ja_sanitizado=False`, aplica `sanitizar_pii` internamente;
2. `validar_sem_pii` checa residual (CPF/CNPJ/processo/RG/e-mail/telefone/CEP);
3. residual encontrado → **externos removidos da cadeia** (fica só Ollama local, se habilitado); motivo registra apenas os TIPOS de PII;
4. cadeia vazia → `permitido=False` com `bloqueio_motivo` seguro: "Nenhum provedor de IA elegível... Habilite o Ollama local (OLLAMA_ENABLED=true) ou remova dados pessoais do texto" (provider_policy.py:123-136). O conteúdo jamais é ecoado.

## 6. Dupla barreira

A policy decide no núcleo, mas o `ai_gateway` **não confia** nessa decisão: antes de despachar a cada provider externo ele re-sanitiza toda mensagem e pula o provider se sobrar PII (`_sanitizar_messages_externo` + loop, ai_gateway.py:192-207, 333-347). Se todos os externos forem pulados por PII e não houver local, o gateway falha com mensagem segura (ai_gateway.py:242-247). Regras de elegibilidade são idênticas nos dois pontos (`_provider_elegivel`, ai_gateway.py:272-283).

## 7. Roteamento recomendado por cenário

| Cenário | Cadeia resultante | Por quê |
|---|---|---|
| Análise de caso/minuta/dossiê, conteúdo limpo | anthropic → ollama → groq | Tarefa complexa prioriza Claude (MODEL_COMPLEXO) |
| Resumo/triagem/chat rápido | ollama → groq | Econômicas; Anthropic nem entra no TASK_ROUTING de resumo/chat |
| Qualquer tarefa com PII residual após sanitização | somente ollama | Externos removidos (LGPD) |
| PII residual e `OLLAMA_ENABLED=false` | (vazia) → HTTP 422 | Bloqueio com motivo seguro |
| `AI_EXTERNAL_PROVIDERS_ALLOWED=false` | somente ollama | Modo soberania total |
| `ANTHROPIC_ENABLED=false` (kill-switch) | ollama → groq | Claude fora sem apagar a chave |
