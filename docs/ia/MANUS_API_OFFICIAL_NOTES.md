# Notas oficiais consultadas — Manus API v2

Fontes consultadas em 2026-09-21:

- https://open.manus.ai/docs/v2/task.create
  - POST https://api.manus.ai/v2/task.create
  - tarefa executa de forma assíncrona;
  - autenticação por `x-manus-api-key` ou OAuth;
  - `agent_profile`: `lite`, `standard`, `max`;
  - texto de mensagem limitado a aproximadamente 5.000 tokens; arquivos não contam para esse limite;
  - `structured_output_schema` aceito; objetos exigem `additionalProperties=false` e todos os campos em `required`.

- https://open.manus.ai/docs/v2/task-lifecycle
  - acompanhar com `task.listMessages` ou webhooks;
  - estados: `running`, `stopped`, `waiting`, `error`;
  - `stopped` pode retornar `structured_output_result`.

- https://open.manus.ai/docs/v2/webhooks-overview
  - eventos principais: `task_created` e `task_stopped`;
  - webhook deve responder HTTP 200 e em até 10 segundos;
  - `task_stopped` pode conter `structured_output` com `success`, `value` e `error`.

- https://open.manus.ai/docs/v2/webhooks-security
  - assinatura RSA-SHA256 com `X-Webhook-Signature` e `X-Webhook-Timestamp`;
  - conteúdo assinado: `{timestamp}.{url}.{sha256(body)}`;
  - documentação recomenda janela de cinco minutos e cache da chave pública.

- https://open.manus.ai/docs/v2/rate-limits
  - `task.create`: 10/min por usuário;
  - `task.listMessages`: 100/min;
  - a documentação recomenda webhooks em produção e backoff com jitter para HTTP 429.

- https://manus.im/pricing
  - página pública mostra planos e créditos, mas não apresenta uma tarifa universal por análise via API.
  - custo por análise deve ser medido no piloto e confirmado no painel/Help Center da conta.
