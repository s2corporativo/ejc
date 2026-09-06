# RUNBOOK — Monitoramento e Observabilidade (EJC)

Stack mínima e gratuita para o go-live: **Sentry** (erros) + **UptimeRobot**
(uptime) sobre os healthchecks nativos. Sem isso, uma queda em produção passa
despercebida até um usuário reclamar.

## Healthchecks nativos (já no backend)

- `GET /api/health` → `{"status":"ok","version":"3.0.0","database":true}`.
  Liveness simples; use para o UptimeRobot.
- `GET /api/health/ready` → `{"status":"ready","checks":{"database":...,
  "redis":...,"embeddings":...}}`. Readiness com dependências; use para
  diagnóstico e para o gate de deploy.

## Sentry (rastreamento de erros — free tier)

1. Crie um projeto Python em sentry.io e copie o DSN.
2. No `.env` de produção: `SENTRY_DSN=https://...ingest.sentry.io/...`
   (a chave já existe em `.env.example`; vazia = desabilitado). O backend liga
   o Sentry automaticamente na presença do DSN, com `send_default_pii=False`
   (não vaza PII — conformidade LGPD).
3. Valide forçando um erro controlado em staging e conferindo o evento no
   painel do Sentry.

## UptimeRobot (uptime — free tier)

1. Crie um monitor HTTP(s) para `https://SEU_DOMINIO/api/health`, intervalo
   5 min, esperando HTTP 200 e a string `"status":"ok"`.
2. Configure alertas (e-mail e/ou webhook → WhatsApp via integrador). Opcional:
   um segundo monitor em `/api/health/ready` para pegar degradação de
   dependência (banco/redis) antes de virar queda total.

## O que já roda na VPS (além do Sentry/UptimeRobot)

- **Uptime Kuma** self-hosted (`infra/monitoring/uptime-kuma/`, só em
  `127.0.0.1:3001`): monitores HTTP dos sistemas da VPS. Como roda na MESMA
  VPS, não detecta queda total do host — o UptimeRobot externo continua
  obrigatório. Adicione: monitor de certificado TLS com aviso a 14 dias
  (INF-09) e monitor *keyword* no badge do Woodpecker
  `https://ci.depaulateixeira.adv.br/api/badges/2/status.svg?branch=main`
  esperando `success` — `main` vermelha bloqueia o deploy automático e precisa
  virar alerta, não descoberta no próximo deploy.
- **Watchdog local** `scripts/monitor_health.sh` (cron): reinicia backend/
  frontend com cooldown e guarda log forense antes do restart. Registra só em
  `/var/log/ejc_health_monitor.log`; para receber o evento fora da VPS, aponte
  um monitor *push* do Kuma nesse script ou envie a linha ao WhatsApp via
  integrador.
- **Disco e memória do host** (INF-13): não há alerta nativo. Mínimo
  recomendado — cron de 5 min que chama um monitor *push* do Kuma quando
  `df /var/lib/docker` passar de 85% ou `free` mostrar swap acima de 50%. O
  incidente de 27/08 foi detectado por um humano olhando `free`.
- **Backup**: o scheduler produz resultado por ciclo (`backup_drive_state`,
  `/admin/backup/status`, com `offsite_ok` e `retencao_local_ok`); exponha
  como heartbeat *push* no Kuma para que dois ciclos sem offsite virem alerta.

## Sinais para observar no primeiro dia de operação

- **Erros 5xx** no Sentry — meta: zero. Qualquer pico investigar na hora.
- **`REFRESH_REUSE`** no audit log — reuso de refresh token. Um evento isolado
  pode ser corrida benigna de multi-abas (tratada com janela de graça de 60s);
  eventos repetidos para o mesmo usuário indicam token roubado — investigar.
- **`LOGIN_TOTP_PENDENTE`** em volume anômalo — sondagem de credenciais.
- **Fila de indexação RAG** — docs em `status_indexacao='pendente'` que não
  saem: checar `EMBEDDINGS_ENABLED` e o serviço de embeddings. O seed da Bíblia
  fica pendente até vetorizar (ver RUNBOOK do RAG / `scripts/seed_biblia_ejc.py`).
- **Latência/erros de banco** em `/api/health/ready` (`checks.database=false`).

## Avançado (pós-MVP)

Prometheus + Grafana self-hosted quando houver necessidade de métricas
históricas (throughput, latência p95, uso de recursos). Não é bloqueador para
o go-live — a stack Sentry + UptimeRobot cobre o essencial de detecção.
