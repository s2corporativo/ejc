# EJC — Escritório Jurídico Clovis
## Sistema de Gestão Jurídica v3 — Painel Administrativo Local

---

## Acesso à VPS (Contabo)

| Item | Valor |
|------|-------|
| IP | (definido em `vps-tools/.env` → `VPS_HOST` — não versionar) |
| Domínio ativo | `https://ejc.depaulateixeira.adv.br` |
| SSH User | (definido em `vps-tools/.env` → `VPS_USER`) |
| Plano | Cloud VPS 20 SSD — US$ 7,20/mês |
| Painel | Contabo (acessar via painel/credencial pessoal — instance-id não versionado) |

**Credenciais EJC:**
- Nunca registrar senhas reais neste README.
- Gerenciar acessos pelo painel de usuarios do EJC ou por procedimento administrativo seguro.

---

## Estrutura desta Pasta

```
C:\Users\User\EJC\
├── README.md          ← este arquivo
├── backend/app/       ← código Python (FastAPI) — cópia do VPS /opt/ejc/backend/app
│   ├── main.py
│   ├── routers/       ← 95 routers
│   ├── services/      ← 49 serviços
│   ├── models/
│   ├── schemas/
│   ├── core/
│   └── modules/
├── frontend/src/      ← código React/TS — cópia do VPS /opt/ejc/frontend/src
│   ├── App.tsx
│   ├── pages/         ← todas as telas
│   └── components/
├── scripts/           ← scripts de manutenção (backup, etc.)
├── vps-tools/         ← ferramentas SSH/SFTP
│   ├── run.js         ← executa comando na VPS
│   └── upload.js      ← sobe arquivo local para VPS
└── deploy/            ← artefatos de deploy (docker-compose, configs)
```

---

## Operações Comuns

### Conectar na VPS e rodar comando
```powershell
cd C:\Users\User\EJC\vps-tools
node run.js "" "docker ps"
```

### Ver logs do backend
```powershell
node run.js "" "docker logs ejc_backend --tail 50"
```

### Verificar saúde do sistema
```powershell
node run.js "" "curl -s http://localhost:8000/api/health"
```

### Editar e subir arquivo para VPS
```powershell
# 1. Editar o arquivo local em C:\Users\User\EJC\backend\app\routers\arquivo.py
# 2. Subir para VPS:
node upload.js /opt/ejc/backend/app/routers/arquivo.py C:\Users\User\EJC\backend\app\routers\arquivo.py
# 3. Reiniciar backend:
node run.js "" "docker restart ejc_backend"
```

### Deploy de novo arquivo frontend
```powershell
node upload.js /opt/ejc/frontend/src/pages/NovaPage.tsx C:\Users\User\EJC\frontend\src\pages\NovaPage.tsx
node run.js "" "cd /opt/ejc && docker compose build frontend && docker compose up -d --no-deps frontend"
```

### Backup manual do banco
```powershell
node run.js "" "/opt/ejc/scripts/backup.sh"
```

### Reset de senha admin (se necessário)
> Defina a nova senha em uma variável de ambiente local (`$NOVA_SENHA`) — **nunca** escreva a senha em texto puro neste README nem em scripts versionados.
```powershell
# $NOVA_SENHA = "<defina-localmente>"
node run.js "" "HASH=`$(docker exec ejc_backend python3 -c \"import os; from passlib.context import CryptContext; c=CryptContext(schemes=['bcrypt']); print(c.hash(os.environ['NOVA_SENHA']))\") && docker exec ejc_postgres psql -U ejc_user -d ejc_db -c \"UPDATE usuarios SET senha_hash='`$HASH' WHERE email='admin@ejc.adv.br';\""
```

---

## Stack Técnica

| Camada | Tecnologia |
|--------|-----------|
| Backend | FastAPI (Python 3.11) |
| Frontend | React + TypeScript + Tailwind CSS |
| Banco | PostgreSQL 16 + pgvector |
| IA | Groq (principal) + Anthropic (opcional) |
| Embeddings | intfloat/multilingual-e5-large (local, pgvector) |
| Storage | Google Drive (Service Account — e-mail e projeto definidos em `.env`, não versionados) |
| E-mail | SMTP Gmail (contato@depaulateixeira.adv.br) |
| Containers | Docker + Docker Compose |

---

## Estado Atual (24/06/2026)

### Containers ativos na VPS
- `ejc_backend` — porta 8000 (healthy)
- `ejc_db` — porta 5432 (PostgreSQL, healthy)
- `ejc_frontend` — porta 8080→80
- `evolution_api` — porta 8080 (Evolution WhatsApp — não usada pelo EJC)

### Funcionalidades ativas
- 95 routers / 49 services / ~83 tabelas no banco
- RAG com ~11k chunks (embeddings locais e5-768d)
- Google Drive integrado (6 pastas por tipo de doc)
- E-mail SMTP configurado e testado
- Push notifications (VAPID configurado, backend pronto)
- DataJud integrado (DATAJUD_ENABLED=true)
- DJEN monitoramento (configurado, aguarda cadastro OAB no perfil)
- Análise Bancária de Extratos (OFX/CSV/PDF)

### Pendências (não fazer sem confirmação)
- `vw_atividades` DROP (view órfã)
- Fase 4 DROP de `cases.numero_processo/tribunal/comarca` — após soak, não antes de 2026-07-07
- `linked_judicial_case_id` deprecação
- Portal do Cliente (backend pronto, frontend pendente)
- Push subscription (usuário precisa clicar "ativar push" no SecurityMenu)
- DJEN alertas (usuário precisa cadastrar OAB no perfil)
- WhatsApp: descartado. Se retomar: Evolution self-hosted

### Migrations Alembic
- Última: `048` (alembic head)
- 3 tabelas adicionadas sem alembic: `bank_analyses`, `bank_transactions`, `bank_abusive_charges`

---

## Alertas de Segurança
- `NUNCA` subir .env para git
- `NUNCA` fazer DROP sem backup prévio
- Backup diário automático em `/opt/ejc/backups/` (retenção 30 dias)
- Último backup manual: `pre_correcao_20260623.sql.gz` (41MB) e `pre_fase1_proc_20260623_1928.dump`
