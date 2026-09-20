# EJC — AIProviderPolicy (política central de provedores)

Data: 2026-07-04 · Código: `backend/app/services/ai/provider_policy.py`.

> **Estado atual (20/09/2026).** Política operacional vigente: **Groq** para
> tarefas corriqueiras/baixo custo; **Maritaca/Sabiá** para leitura, análise,
> raciocínio e pesquisa jurídica; **Ollama** para sigilo/fallback local; e
> **Claude/Anthropic somente quando requisitado explicitamente no EJC**.
>
> - **Quatro provedores**: `ollama`, `anthropic`, `maritaca`, `groq`
>   (`provider_registry.PROVIDERS_SUPORTADOS`). A Maritaca (Sabiá) existe desde
>   julho e não constava aqui.
> - **Fonte única de elegibilidade**: `services/ai/provider_registry.py`
>   (`_requisitos` → `provider_elegivel`/`motivo_inelegivel`, e as variantes
>   `*_com(provider, settings)` para painéis). A `AIProviderPolicy._elegivel`,
>   o gateway (`_provider_elegivel`, `_resolver_cadeia`), `integration_status`,
>   `ia_saude` e `/ai/status` consultam essa fonte — a tabela da §2 é histórica.
> - **Requisitos por provedor**: `AI_ENABLED` (kill-switch global, requisito de
>   TODOS desde AUD27-P0-1) + flag própria (`OLLAMA_ENABLED`, `ANTHROPIC_ENABLED`,
>   `MARITACA_ENABLED`, `GROQ_ENABLED`) + chave (externos) +
>   `AI_EXTERNAL_PROVIDERS_ALLOWED` (externos).
> - **Prioridade default**: `AI_PROVIDER_PRIORITY="groq,maritaca,ollama,anthropic"`.
>   Com `ANTHROPIC_EXPLICIT_ONLY=true`, o Anthropic é retirado da cadeia
>   automática; a posição final existe apenas para compatibilidade/configuração.
> - **Perfil de IA**: `AI_PROFILE=externo|local|hibrido|desligado` deriva as
>   flags acima e a prioridade (`config._aplicar_perfil_ia`); vazio = flags
>   manuais. Código, `.env.example` e `docker-compose.yml` compartilham os
>   mesmos defaults (`MARITACA_ENABLED=true`; sem chave, permanece inelegível).
> - **Cadeias por tarefa**: `resumo/chat_rapido` promovem Groq; tarefas de
>   mérito (`analise_juridica`, `estrategia`, `elaboracao_peca`,
>   `analise_contrato`, `jurimetria`) promovem Maritaca. Claude entra apenas
>   com `provider_override="anthropic"` ou no modo agêntico deliberado.
> - **Modelos e custo**: `ANTHROPIC_MODEL_COMPLEXO=claude-opus-4-8`,
>   `ANTHROPIC_MODEL_RAPIDO=claude-haiku-4-5-20251001`; tabela de preços em
>   `services/ai_cost.py` (inclui tokens de prompt caching).
> - **Painel de verdade**: `GET /ia-governanca/provedores`.

A `AIProviderPolicy` (provider_policy.py:43) decide, ANTES de qualquer chamada de modelo: quais providers são elegíveis, em que ordem tentar, se o conteúdo exige sanitização para destino externo e se a chamada é permitida. É **decisão pura** — não chama modelo; o despacho continua no `ai_gateway`.

## 1. Entrada e saída

```python
AIProviderPolicy().avaliar(texto_completo, task_type, *,
                           ja_sanitizado=False, exige_fonte=False,
                           provider_override=None) -> PolicyDecision
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

CSV em Settings: `groq,maritaca,ollama,anthropic`. A ordem é filtrada pela
elegibilidade. Se `ANTHROPIC_EXPLICIT_ONLY=true`, Claude é removido do
automático. Um `provider_override="anthropic"` válido cria uma cadeia explícita
somente com Claude, ainda sujeita aos gates de chave, LGPD e sigilo.

## 4. Priorização por perfil de tarefa (provider_policy.py:21-29, 112-119)

- `TAREFAS_COMPLEXAS` → Maritaca/Sabiá à frente para leitura, análise,
  estratégia, redação e pesquisa jurídica.
- `TAREFAS_ECONOMICAS` = {resumo, triagem, chat_rapido} → Groq à frente;
  Ollama pode servir de fallback local quando habilitado.
- Anthropic não é promovido automaticamente; só entra por requisição explícita.
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
| Análise, leitura, minuta, dossiê ou pesquisa jurídica | maritaca → (ollama) → groq | Maritaca é o motor automático de mérito PT-BR |
| Resumo/triagem/chat rápido | groq → (ollama) → maritaca | Groq atende rotina; fallback preservado |
| Solicitação explícita "Claude" | anthropic | Sem fallback silencioso na policy; se inelegível, a solicitação é bloqueada com motivo seguro |
| Qualquer tarefa com PII residual após sanitização | somente ollama | Externos removidos (LGPD) |
| PII residual e `OLLAMA_ENABLED=false` | (vazia) → HTTP 422 | Bloqueio com motivo seguro |
| `AI_EXTERNAL_PROVIDERS_ALLOWED=false` | somente ollama | Modo soberania total |
| `ANTHROPIC_ENABLED=false` (kill-switch) | automático inalterado | Claude explícito fica indisponível sem apagar a chave |
