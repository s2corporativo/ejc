---
name: arquiteto-monitoramento-observabilidade
description: >
  Configura monitoramento, alertas e observabilidade para os sistemas EJC e S2 em produção. Use quando precisar implementar monitoramento de uptime, rastreamento de erros, métricas de performance, alertas de sistema caído. Cobre: Sentry (rastreamento de erros, gratuito), UptimeRobot (uptime monitoring, gratuito), healthcheck endpoints, logging estruturado, alertas por WhatsApp quando sistema cair. Stack mínima para MVP: Sentry free tier + UptimeRobot free + healthcheck endpoint. Stack avançada: Prometheus + Grafana (self-hosted). Acionado por: "monitoramento sistema", "Sentry EJC", "sistema caiu alerta", "uptime monitoring", "métricas sistema", "Prometheus Grafana", "logging estruturado", "healthcheck", "alerta sistema caído", "observabilidade EJC", "erro em produção alerta".
---

# Monitoramento e Observabilidade — EJC e S2

## Stack por Nível

```
MÍNIMO (custo zero, imediato):
  Sentry Free        — rastreamento de erros Python/JS
  UptimeRobot Free   — monitoramento de uptime (50 monitores, alertas WhatsApp/email)
  /health endpoint   — healthcheck interno para Docker e CI/CD

AVANÇADO (self-hosted):
  Prometheus         — coleta de métricas
  Grafana            — dashboards e alertas
  Loki               — agregação de logs
```

---

## 1. Sentry — Rastreamento de Erros

### Backend FastAPI

```python
# backend/app/main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
import os

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),  # dsn do projeto no sentry.io
    integrations=[FastApiIntegration(), SqlalchemyIntegration()],
    traces_sample_rate=0.1,      # 10% das transações rastreadas (performance)
    profiles_sample_rate=0.1,
    environment=os.getenv("ENVIRONMENT", "production"),
    release=os.getenv("GIT_SHA", "unknown"),
    send_default_pii=False,       # LGPD: não enviar dados pessoais
    before_send=scrub_sensitive_data,  # limpar dados sensíveis
)

def scrub_sensitive_data(event, hint):
    """Remove CPF, CNPJ, emails de erros antes de enviar ao Sentry"""
    import re
    if event.get("request", {}).get("data"):
        data_str = str(event["request"]["data"])
        data_str = re.sub(r'\d{3}\.\d{3}\.\d{3}-\d{2}', 'CPF_REDACTED', data_str)
        data_str = re.sub(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', 'CNPJ_REDACTED', data_str)
    return event
```

### Frontend React

```typescript
// frontend/src/main.tsx
import * as Sentry from "@sentry/react"

Sentry.init({
  dsn: import.meta.env.VITE_SENTRY_DSN,
  environment: import.meta.env.MODE,
  tracesSampleRate: 0.1,
  beforeSend(event) {
    // Não enviar erros de desenvolvimento
    if (import.meta.env.DEV) return null
    return event
  }
})
```

---

## 2. Healthcheck Endpoint

```python
# backend/app/routers/health.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from datetime import datetime
import os

router = APIRouter()

@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Healthcheck completo para Docker, CI/CD e UptimeRobot"""
    checks = {}

    # Banco de dados
    try:
        db.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:50]}"

    # Espaço em disco (uploads)
    try:
        import shutil
        total, used, free = shutil.disk_usage("/app/uploads")
        used_pct = (used / total) * 100
        checks["disk"] = "ok" if used_pct < 90 else f"warning: {used_pct:.0f}% used"
    except Exception:
        checks["disk"] = "unknown"

    status = "healthy" if all(v == "ok" for v in checks.values()) else "degraded"
    http_status = 200 if status == "healthy" else 503

    return {
        "status": status,
        "checks": checks,
        "version": os.getenv("GIT_SHA", "unknown"),
        "timestamp": datetime.utcnow().isoformat()
    }
```

---

## 3. UptimeRobot — Configuração

```
URL para monitorar:
  https://ejc.seudominio.com.br/health      → Tipo: HTTP(S) | Intervalo: 5min
  https://sistema-s2.seudominio.com.br/health

Alertas:
  Email: adm@vetmg.com.br
  WhatsApp: via webhook → n8n → WhatsApp (integrador-whatsapp-business)

Webhook UptimeRobot:
  URL: https://n8n.seudominio.com.br/webhook/uptime-alert
  Payload: {"monitor_url":"...", "status":"down", "reason":"..."}
```

---

## 4. Logging Estruturado

```python
# backend/app/logging_config.py
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, ensure_ascii=False)

def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # Silenciar loggers verbosos
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
```

---

## 5. Variáveis de Ambiente

```env
SENTRY_DSN=https://xxx@sentry.io/yyy
ENVIRONMENT=production
GIT_SHA=abc123  # injetado pelo CI/CD
```
