---
name: arquiteto-automacao-n8n
description: >
  Projeta e implementa workflows de automação usando n8n para conectar os sistemas EJC, Verde Limp e Licitação (S2). Use SEMPRE que precisar eliminar tarefas manuais repetitivas, criar fluxos automáticos, integrar sistemas diferentes, configurar triggers, webhooks, cron jobs ou qualquer automação entre os ecossistemas. Cobre: instalação n8n via Docker, arquitetura de workflows, templates de automação prontos, integração com APIs, WhatsApp, email, banco de dados, Google Sheets, e agendar processos recorrentes. Cinco pipelines pré-configurados: (1) alerta de prazo EJC → WhatsApp; (2) radar PNCP → notificação S2; (3) OS Verde Limp concluída → relatório cliente; (4) vencimento certidão → alerta responsável; (5) novo lead EJC → triagem automática. Acionado por: "automação", "workflow", "n8n", "fluxo automático", "conectar sistemas", "eliminar tarefa manual", "integrar EJC com", "agendar processo", "trigger automático", "pipeline automação", "n8n configurar", "n8n instalar".
---

# Arquiteto de Automação n8n — Ecossistema S2/EJC/Verde Limp

## Contexto

```
FERRAMENTA: n8n (workflow automation, self-hosted, open-source)
DEPLOY: Docker container — integra com Docker Compose existente
SISTEMAS CONECTADOS: EJC (FastAPI) | Sistema-S2 (Node.js/TS) | Verde Limp (Flask/FastAPI) | WhatsApp Business | Email (SMTP) | Google Sheets | PNCP API
URL LOCAL: http://localhost:5678 (ou http://n8n.dominio.com.br)
LICENÇA: n8n Community (grátis self-hosted)
```

---

## 1. Instalação n8n via Docker

### Adicionar ao docker-compose.yml existente

```yaml
# Adicionar no docker-compose.yml do EJC ou standalone
services:
  n8n:
    image: n8nio/n8n:latest
    container_name: n8n
    restart: unless-stopped
    ports:
      - "5678:5678"
    environment:
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=${N8N_USER:-admin}
      - N8N_BASIC_AUTH_PASSWORD=${N8N_PASSWORD}
      - N8N_HOST=${N8N_HOST:-localhost}
      - N8N_PORT=5678
      - N8N_PROTOCOL=https
      - WEBHOOK_URL=https://${N8N_HOST}:5678/
      - GENERIC_TIMEZONE=America/Sao_Paulo
      - TZ=America/Sao_Paulo
      # Banco próprio para persistência
      - DB_TYPE=postgresdb
      - DB_POSTGRESDB_HOST=db
      - DB_POSTGRESDB_PORT=5432
      - DB_POSTGRESDB_DATABASE=n8n_db
      - DB_POSTGRESDB_USER=${POSTGRES_USER}
      - DB_POSTGRESDB_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - n8n_data:/home/node/.n8n
    depends_on:
      db:
        condition: service_healthy

volumes:
  n8n_data:
```

### .env additions
```env
N8N_USER=admin
N8N_PASSWORD=SENHA_FORTE_AQUI
N8N_HOST=n8n.seudominio.com.br
```

---

## 2. Pipeline 1 — Alerta de Prazo EJC → WhatsApp

```
TRIGGER: Cron (a cada 1 hora)
FLUXO:
  1. HTTP GET /api/v1/deadlines?status=pendente&days_ahead=2
  2. Filter: prazos com ≤ 2 dias úteis
  3. For each deadline:
     a. GET /api/v1/cases/{case_id} → pegar responsável
     b. GET /api/v1/users/{user_id} → pegar WhatsApp
     c. Send WhatsApp via Z-API ou Meta
  4. Log resultado no EJC: POST /api/v1/notifications/log
```

```json
{
  "name": "EJC - Alerta Prazo Crítico",
  "nodes": [
    {
      "type": "n8n-nodes-base.scheduleTrigger",
      "parameters": {"rule": {"interval": [{"field": "hours", "hoursInterval": 1}]}}
    },
    {
      "type": "n8n-nodes-base.httpRequest",
      "name": "Buscar prazos críticos",
      "parameters": {
        "url": "={{$env.EJC_API_URL}}/api/v1/deadlines",
        "method": "GET",
        "queryParameters": {"status": "pendente", "days_ahead": 2},
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth"
      }
    },
    {
      "type": "n8n-nodes-base.filter",
      "name": "Apenas urgentes",
      "parameters": {
        "conditions": {"number": [{"value1": "={{$json.days_remaining}}", "operation": "smallerEqual", "value2": 2}]}
      }
    },
    {
      "type": "n8n-nodes-base.splitInBatches",
      "name": "Por prazo"
    },
    {
      "type": "n8n-nodes-base.httpRequest",
      "name": "Enviar WhatsApp",
      "parameters": {
        "url": "={{$env.ZAPI_URL}}/send-text",
        "method": "POST",
        "jsonParameters": true,
        "bodyParameters": {
          "phone": "={{$json.advogado_whatsapp}}",
          "message": "⚠️ PRAZO CRÍTICO EJC\n\nCaso: {{$json.case_number}}\nAto: {{$json.description}}\nVence: {{$json.deadline_date}}\nCliente: {{$json.client_name}}\n\nAcesse: {{$env.EJC_URL}}/casos/{{$json.case_id}}"
        }
      }
    }
  ]
}
```

---

## 3. Pipeline 2 — Radar PNCP → Notificação S2

```
TRIGGER: Cron (7h e 14h, dias úteis)
FLUXO:
  1. HTTP GET PNCP API (últimas 12h)
  2. Filter keywords (veterinário, ambiental, conservação, consultoria)
  3. Dedup: verificar se pncp_id já no sistema-s2
  4. Para cada novo edital:
     a. POST sistema-s2 /editais-radar (salvar)
     b. Send WhatsApp para Dr. Clovis
     c. Send email resumo diário
  5. Relatório: total de editais encontrados/filtrados
```

```json
{
  "name": "S2 - Radar PNCP Automático",
  "nodes": [
    {"type": "scheduleTrigger", "parameters": {"rule": {"cronExpression": "0 7,14 * * 1-5"}}},
    {
      "type": "httpRequest",
      "name": "PNCP API",
      "parameters": {
        "url": "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao",
        "queryParameters": {
          "dataInicial": "={{$now.minus(12, 'hours').format('yyyy-MM-dd')}}",
          "dataFinal": "={{$now.format('yyyy-MM-dd')}}",
          "tamanhoPagina": 50
        }
      }
    },
    {
      "type": "code",
      "name": "Filtrar keywords",
      "parameters": {
        "jsCode": "const keywords = ['veterinár','ambiental','tcfa','roçada','jardinagem','consultoria jurídica'];\nreturn items.filter(i => keywords.some(k => (i.json.objetoCompra||'').toLowerCase().includes(k))).map(i => ({json: {...i.json, relevante: true}}));"
      }
    }
  ]
}
```

---

## 4. Pipeline 3 — OS Verde Limp Concluída → Relatório Cliente

```
TRIGGER: Webhook (POST /webhook/os-concluida) ou Polling a cada 30min
FLUXO:
  1. Recebe OS concluída (contract_id, os_id, fotos, área executada)
  2. Busca dados do contrato → nome cliente, email, WhatsApp
  3. Gera PDF do relatório de execução (via endpoint /reports/os/{os_id})
  4. Envia email com PDF para cliente
  5. Envia WhatsApp para cliente: "OS {número} concluída — relatório em anexo"
  6. Atualiza status da OS → 'relatório_enviado'
```

---

## 5. Pipeline 4 — Vencimento de Certidão → Alerta

```
TRIGGER: Cron diário às 8h
FLUXO:
  1. Query documentos vencendo em ≤ 15 dias (Verde Limp + S2 + EJC)
  2. Agrupar por responsável
  3. Enviar WhatsApp + email com lista de documentos críticos
  4. Para vencimento ≤ 7 dias: marcar CRÍTICO + notificar Dr. Clovis diretamente
```

---

## 6. Pipeline 5 — Novo Lead EJC → Triagem Automática

```
TRIGGER: Webhook (POST /webhook/novo-lead) — disparado ao criar lead no EJC
FLUXO:
  1. Recebe dados do lead (nome, assunto, urgência, origem)
  2. Classifica por área jurídica (keyword matching no assunto)
  3. Verifica conflito de interesses via API EJC
  4. Se sem conflito: POST /api/v1/leads/{id}/assign → advogado disponível
  5. Envia WhatsApp para advogado designado: "Novo lead: {nome} | {área}"
  6. Envia WhatsApp para lead: "Recebemos seu contato. Retornaremos em breve."
```

---

## 7. Variáveis de Ambiente n8n

```env
# APIs dos sistemas
EJC_API_URL=http://ejc-backend:8000
EJC_API_TOKEN=TOKEN_JWT_SERVICO
SISTEMA_S2_URL=http://sistema-s2:3000
SISTEMA_S2_TOKEN=TOKEN_SERVICO
VL_API_URL=http://verde-limp:5000

# WhatsApp
ZAPI_URL=https://api.z-api.io/instances/SEU_INSTANCE/token/SEU_TOKEN
ZAPI_CLIENT_TOKEN=SEU_CLIENT_TOKEN
WHATSAPP_CLOVIS=5531999074546

# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=adm@vetmg.com.br
SMTP_PASS=APP_PASSWORD_GMAIL

# n8n
N8N_ENCRYPTION_KEY=CHAVE_ALEATORIA_32_CHARS
```

---

## 8. Boas Práticas n8n

- Nomear workflows descritivamente: `[SISTEMA] - Nome da Automação`
- Usar Error Workflow para capturar falhas e notificar por WhatsApp
- Sempre logar resultado de cada execução em tabela de automação_logs
- Usar variáveis de ambiente — nunca hardcodar tokens em nodes
- Backup dos workflows: exportar JSON semanalmente via /api/v1/workflows
- Separar workflows por sistema (pasta EJC, pasta S2, pasta VL)
- Idempotência: verificar se ação já foi executada antes de executar novamente

---

## 9. Comandos Úteis

```bash
# Backup workflows
curl -u ${N8N_USER}:${N8N_PASSWORD} http://localhost:5678/api/v1/workflows > workflows_backup.json

# Restaurar workflow
curl -u ${N8N_USER}:${N8N_PASSWORD} -X POST http://localhost:5678/api/v1/workflows \
  -H "Content-Type: application/json" -d @workflow.json

# Health check
curl http://localhost:5678/healthz

# Ver execuções recentes
curl -u ${N8N_USER}:${N8N_PASSWORD} http://localhost:5678/api/v1/executions?limit=10
```
