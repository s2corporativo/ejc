# Observabilidade — EJC

Tudo aqui é **opcional e gated**: sem configurar nada, o EJC roda igual a hoje.
Duas camadas gratuitas cobrem o essencial: **UptimeRobot** (o sistema está no ar?)
e **Sentry** (o que quebrou?). Ambas têm _free tier_.

## Endpoints de saúde

| Endpoint | Tipo | Contrato | Uso |
|---|---|---|---|
| `GET /api/health` | Liveness | **Sempre HTTP 200** enquanto o processo respira (sem I/O externo) | Docker healthcheck, `post_deploy_check.sh`, UptimeRobot |
| `GET /api/health/ready` | Readiness | **200** quando pronto, **503** se o banco/migrations falham | Checagem de dependências (K8s-style, diagnóstico) |

Corpo do `/api/health`:

```json
{ "status": "ok", "version": "dev", "uptime_seconds": 12.34, "environment": "production" }
```

`version` vem das envs `APP_VERSION` ou `GIT_SHA` (senão `"dev"`). Use o
`/api/health` (liveness) para o monitor externo — ele não cai quando o banco
oscila, evitando alarme falso; e o `/api/health/ready` para diagnosticar
prontidão real (banco + alembic na head).

## UptimeRobot (uptime, gratuito)

1. Crie conta em <https://uptimerobot.com> (free tier: 50 monitores, intervalo 5 min).
2. **Add New Monitor** → _Monitor Type_: **HTTP(s)**.
3. **URL**: `https://ejc.depaulateixeira.adv.br/api/health`
4. **Monitoring Interval**: **5 minutos**.
5. **Alert Contacts**: adicione e-mail e/ou WhatsApp (via integração/webhook) para
   ser avisado quando o monitor detectar resposta ≠ 200.
6. Salve. O UptimeRobot passa a esperar **HTTP 200**; qualquer outra coisa
   (timeout, 5xx, DNS) dispara alerta.

## Sentry (rastreamento de erros, gratuito)

O Sentry fica **desligado** enquanto `SENTRY_DSN` estiver vazio (no-op no boot).

Para ligar no VPS:

1. Crie um projeto Python/FastAPI em <https://sentry.io> e copie o **DSN**.
2. No `.env` do VPS, defina:
   ```env
   SENTRY_DSN=https://<sua-chave>@o0.ingest.sentry.io/0
   SENTRY_ENVIRONMENT=production
   SENTRY_TRACES_SAMPLE_RATE=0.0   # 0.0 = performance tracing off (suba se quiser)
   ```
3. Redeploy (`docker compose up -d --build` ou o script de deploy).
4. No próximo boot, o log mostra `Sentry inicializado (...)`. Sem a env, mostra
   `Sentry desativado (SENTRY_DSN vazio)`.

### Privacidade / LGPD

- `send_default_pii=False` (obrigatório): o Sentry não anexa IP/cookies/corpo por padrão.
- Um `before_send` remove headers `Authorization`/`Cookie` e mascara campos
  sensíveis (`cpf`, `cnpj`, `senha`, `password`, `token`, ...) do request e dos
  extras antes de qualquer evento sair.

Config em `backend/app/core/observability.py` (`init_sentry`, `_before_send`).
