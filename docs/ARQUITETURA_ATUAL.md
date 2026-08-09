# ARQUITETURA ATUAL — EJC

> Gerado por `scripts/governanca/inventario-repo.sh` em 2026-07-29, commit `eb1ebfb4`.
> Descreve o estado observado, nao o estado desejado.

## 1. Dependencias declaradas — backend

```
--- backend/requirements.txt ---
# EJC backend dependencies
#
# REPRODUTIBILIDADE DO INSTALL (relatório de melhoria 2026-07-22): `pip install`
# deve completar limpo num venv novo (Debian/Python 3.11). Pin sensível a isso:
#   * pywebpush==1.14.1 (NÃO 2.0.0) — ver o bloco "Web Push" abaixo: o 2.0.0
#     arrasta `aiohttp` (C-extension) como dependência DURA, único pacote do
#     conjunto a puxar aiohttp sem `extra`; compila do zero onde não há wheel e
#     era a causa provável do "pip install não completa em Debian limpo por
#     http-ece/pywebpush". O EJC só usa a API SÍNCRONA do pywebpush.

# API
# FastAPI/Starlette atualizados em 19/07/2026 para eliminar a série de
# vulnerabilidades de parsing, streaming e middleware apontada pelo pip-audit.
# FastAPI 0.139.2 declara starlette>=0.46.0 sem limite superior.
fastapi==0.139.2
starlette==1.3.1
uvicorn[standard]==0.29.0
python-multipart==0.0.31

# Database
asyncpg==0.29.0
sqlalchemy[asyncio]==2.0.30
alembic==1.13.1
pgvector==0.3.2
psycopg2-binary==2.9.9  # driver SYNC exigido por alembic/env.py — ausente causava
                         # falha de "alembic upgrade head" em instalação limpa (Etapa 6D)

# Validation and settings
pydantic==2.13.4
pydantic-settings==2.3.1
email-validator==2.3.0
python-dotenv==1.2.2
validators==0.28.3
python-dateutil==2.9.0

# Security
# Item 7 da auditoria: python-jose[cryptography] e passlib REMOVIDOS — sem
# nenhum import em app/ (o código usa PyJWT p/ JWT e bcrypt puro p/ senha,
# ver core/security.py). A remoção também elimina `ecdsa` (transitiva do
# python-jose, sem correção para CVE-2024-23342/Minerva) do ambiente.
slowapi==0.1.9
bcrypt==4.0.1
pyotp==2.9.0
PyJWT==2.13.0
cryptography==48.0.1

# HTTP and integrations
httpx==0.27.0
requests==2.34.2
groq==1.5.0
boto3==1.34.144
botocore==1.34.144
tenacity==8.2.3  # datajud_service.py, djen_service.py (retry)

# Google Drive (documents.py)
google-api-python-client==2.198.0
google-auth==2.55.1

# Web Push (notification_service.py) — usa SÓ a API síncrona (webpush/WebPushException).
# PIN em 1.14.1 (último 1.x, pré-aiohttp) por REPRODUTIBILIDADE: pywebpush 2.0.0
```

## 2. Dependencias declaradas — frontend

```
  "dependencies": {
    "axios": "^1.7.2",
    "date-fns": "^3.6.0",
    "lucide-react": "^1.24.0",
    "qrcode": "^1.5.4",
    "react": "^19.2.7",
    "react-dom": "^19.2.7",
    "react-router-dom": "^7.18.1",
    "zustand": "^4.5.2"
  },
```

## 3. Servicos em Docker Compose

```
2:  db:
6:    image: pgvector/pgvector:pg16
17:    volumes:
25:  redis:
27:    image: redis:7-alpine
32:    volumes:
40:  backend:
45:    ports:
99:    volumes:
110:    depends_on:
117:    # OBRIGATÓRIO: o frontend usa depends_on: backend: service_healthy —
127:  worker:
155:    volumes:
157:    depends_on:
173:  frontend:
178:    ports:
186:    depends_on:
199:  langfuse-db:
200:    image: postgres:16-alpine
202:    profiles: ["observability"]
212:    volumes:
220:  langfuse:
221:    image: langfuse/langfuse:2
223:    profiles: ["observability"]
225:    depends_on:
230:    ports:
257:  ollama:
259:    image: ollama/ollama:0.31.1
261:    profiles: ["ia-local"]
280:    volumes:
290:  ollama-init:
296:    image: ollama/ollama:0.31.1
298:    profiles: ["ia-local"]
301:    depends_on:
333:  default:
335:  ia:
337:volumes:
338:  postgres_data:
339:  uploads_data:
340:  backups_data:
341:  redis_data:
342:  langfuse_db_data:
343:  ollama_models:
```

## 4. Variaveis de ambiente esperadas

```
ACCESS_TOKEN_EXPIRE_HOURS
ADMIN_EMAIL
ADMIN_NAME
ADMIN_PASSWORD
AI_ACCEPT_EXTERNAL_WITHOUT_SANITIZATION
AI_AGENT_ENABLED
AI_AGENT_MAX_STEPS
AI_AGENT_MAX_TOKENS
AI_BUDGET_ALERTA_BRL
AI_ENABLED
AI_EXTERNAL_PROVIDERS_ALLOWED
AI_LONG_DOCUMENT_CHUNK_CHARS
AI_LONG_DOCUMENT_MAX_CHARS
AI_LONG_DOCUMENT_MAX_CHUNKS
AI_PROMPT_CACHING_ENABLED
AI_PROVIDER
AI_PROVIDER_PRIORITY
AI_REQUIRE_HITL
AI_REQUIRE_SANITIZATION_FOR_EXTERNAL
AI_RESPONSE_CACHE_ENABLED
AI_RESPONSE_CACHE_TTL
AI_SANITIZATION_MODE_MAP
AI_WEB_SEARCH_CUSTO_USD_POR_1000
AI_WEB_SEARCH_ENABLED
AI_WEB_SEARCH_MAX_USES
ANTHROPIC_API_KEY
ANTHROPIC_EFFORT
ANTHROPIC_ENABLED
ANTHROPIC_MAX_TOKENS
ANTHROPIC_MODEL_COMPLEXO
ANTHROPIC_MODEL_RAPIDO
ANTHROPIC_TIMEOUT_SECONDS
APP_ENV
AUDIO_TRANSCRIPTION_DPA_APPROVED
AUDIO_TRANSCRIPTION_ENABLED
AUDIO_TRANSCRIPTION_MAX_MB
AUDIO_TRANSCRIPTION_TIMEOUT
BACKUP_DB_MAX_MB
BACKUP_DESTINO
BACKUP_DIR
BACKUP_DRIVE_FOLDER_ID
BACKUP_ENABLED
BACKUP_ENCRYPTION_KEY
BACKUP_GOOGLE_DRIVE_AUTH_MODE
BACKUP_GOOGLE_DRIVE_OAUTH_CLIENT_ID
BACKUP_GOOGLE_DRIVE_OAUTH_CLIENT_SECRET
BACKUP_GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN
BACKUP_GOOGLE_DRIVE_OAUTH_USER_FILE
BACKUP_GOOGLE_DRIVE_OAUTH_USER_JSON
BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE
BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
BACKUP_HORA_UTC
BACKUP_OFFSITE_OBRIGATORIO
BACKUP_PG_DUMP_TIMEOUT
BACKUP_RCLONE_REMOTE
BACKUP_RCLONE_TIMEOUT
BACKUP_REMOTE
BACKUP_RETENCAO_DIAS
BACKUP_RETENTION_DAYS
BACKUP_UPLOADS_MAX_MB
CELERY_ENABLED
CITACOES_MODO_ESTRITO
CITACOES_POLITICA
COBRANCA_ENABLED
CONECTA_CLIENT_ID
CONECTA_CLIENT_SECRET
CONHECIMENTO_INGEST_ENABLED
CORS_ORIGINS
DATAJUD_API_KEY
DATAJUD_BASE_URL
DATAJUD_ENABLED
DATAJUD_SYNC_ENABLED
DATAJUD_SYNC_HORA_UTC
DATAJUD_TIMEOUT_SECONDS
DEBUG
DIAGNOSTICO_ENABLED
DJEN_INGEST_ENABLED
DJEN_INGEST_JANELA_DIAS
DJEN_OABS_MONITORADAS
DUAS_IAS_ENABLED
DUAS_IAS_TASK_TYPES
EMAIL_ENABLED
EMBEDDINGS_DIM
EMBEDDINGS_ENABLED
EMBEDDINGS_MODEL
EMBEDDINGS_PROVIDER
ENABLE_SCHEDULER
ESCRITORIO_CEP
ESCRITORIO_CIDADE
ESCRITORIO_CNPJ
ESCRITORIO_EMAIL
ESCRITORIO_ENDERECO
ESCRITORIO_ESTADO
ESCRITORIO_NOME
ESCRITORIO_OAB
EVOLUTION_API_KEY
EVOLUTION_API_URL
EVOLUTION_INSTANCE
EVOLUTION_WEBHOOK_SECRET
FERIADOS_BRASILAPI_ENABLED
FORCE_SKILLS_UPDATE
FORCE_TEMPLATES_UPDATE
FRONTEND_URL
GOOGLE_DRIVE_ALLOWED_MIME_TYPES
GOOGLE_DRIVE_AUTH_MODE
GOOGLE_DRIVE_AUTO_CATEGORIZAR
GOOGLE_DRIVE_DEFAULT_CATEGORIA
GOOGLE_DRIVE_ENABLED
GOOGLE_DRIVE_FOLDER_ID
GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID
GOOGLE_DRIVE_MAX_FILE_MB
GOOGLE_DRIVE_OAUTH_CLIENT_ID
GOOGLE_DRIVE_OAUTH_CLIENT_SECRET
GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN
GOOGLE_DRIVE_SHARED_DRIVE_ID
GROQ_API_KEY
GROQ_MODEL
GROQ_MODEL_LARGE
GROQ_PRECO_INPUT_BRL_POR_MILHAO
GROQ_PRECO_OUTPUT_BRL_POR_MILHAO
GROQ_TIMEOUT
GROQ_TRANSCRIPTION_MODEL
GROQ_ZDR_VERIFIED
INDICES_BCB_ENABLED
INDICES_BCB_TIMEOUT
INTAKE_EXTERNAL_FALLBACK
JURIS_IMPORT_FONTES
LANGFUSE_CAPTURE_CONTENT
LANGFUSE_DB_PASSWORD
LANGFUSE_ENABLED
LANGFUSE_HOST
LANGFUSE_NEXTAUTH_SECRET
LANGFUSE_NEXTAUTH_URL
LANGFUSE_PUBLIC_KEY
LANGFUSE_SALT
LANGFUSE_SECRET_KEY
LEXML_INGEST_ENABLED
LEXML_INGEST_MAX_POR_TEMA
LEXML_INGEST_TEMAS
LOG_JSON
LOG_LEVEL
MARITACA_API_KEY
MARITACA_BASE_URL
MARITACA_ENABLED
MARITACA_EXIGIR_SOBERANIA
MARITACA_MODEL
MARITACA_MODEL_RAPIDO
MARITACA_TIMEOUT
MAX_UPLOAD_MB
NORMAS_RFB_TERMOS
OLLAMA_BASE_URL
OLLAMA_ENABLED
OLLAMA_KEEP_ALIVE
OLLAMA_MEM_LIMIT
OLLAMA_PULL_MODELS
PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED
PII_ENCRYPTION_KEY
PII_HASH_KEY
POSTGRES_DB
POSTGRES_PASSWORD
POSTGRES_USER
PUSH_ENABLED
RADAR_LEGISLATIVO_ENABLED
RADAR_LEGISLATIVO_TERMOS
RAG_EXIGIR_APROVADO
RAG_EXIGIR_VIGENCIA_VERIFICADA
RAG_RERANK_ENABLED
RAG_RERANK_MODEL
RAG_SUMULAS_QUARENTENA
RAG_SUMULAS_SEED_ENABLED
RATE_LIMIT_REDIS_ENABLED
REDIS_URL
RELATORIO_DONO_ENABLED
REQUIRE_2FA_ROLES
ROTEAMENTO_INTELIGENTE_ENABLED
ROTEAMENTO_LIMIAR_MEDIO
ROTEAMENTO_LIMIAR_PESADO
ROTEAMENTO_PROVIDER_LEVE
ROTEAMENTO_PROVIDER_MEDIO
ROTEAMENTO_PROVIDER_PESADO
SALARIO_MINIMO_BRL
SALA_JURIDICA_AUTO_ESTADO
SECRET_KEY
SENTRY_DSN
SMTP_HOST
SMTP_PASSWORD
SMTP_PORT
SMTP_USER
TJMG_INGEST_ENABLED
TJMG_INGEST_JANELA_DIAS
TJMG_INGEST_MAX_POR_TEMA
TJMG_INGEST_TEMAS
USD_BRL_RATE
VAPID_CLAIM_EMAIL
VAPID_PRIVATE_KEY
VAPID_PUBLIC_KEY
WHATSAPP_ENABLED
```

> Nunca listar valores. Apenas nomes de variavel.

## 5. Workflows de CI

| Workflow | Gatilhos | Jobs (nome do check) |
|---|---|---|
| `architecture-inventory.yml` | pull_request push workflow_dispatch | Generate complete architecture inventory |
| `architecture-refactor-wave1.yml` | push workflow_dispatch | Apply canonical contracts and compatible routes |
| `architecture-refactor-wave2.yml` | push workflow_dispatch | Apply Case and Process separation |
| `backup-gdrive-activation.yml` | pull_request workflow_dispatch | Validar backup, migration e rollback · Executar prova integral cifrada na VPS |
| `ci.yml` | pull_request push workflow_dispatch | Backend — suíte completa + schema/RAG (Postgres pgvector) · Eval — smoke dos gold sets (offline, bloqueante) · Frontend — testes + typecheck + build |
| `continuity-ui-gates.yml` | pull_request push workflow_dispatch | Continuidade — backup cifrado + restore em banco vazio · Frontend — ESLint + browser responsivo |
| `deploy-vps.yml` | workflow_dispatch | — |
| `ejc-release-gate.yml` | pull_request push workflow_dispatch | P0 guard — conflitos e segredos |
| `frontend-ci.yml` | workflow_dispatch | Typecheck, build and tests |
| `governanca.yml` | pull_request | Governança — travas de PR |
| `main-provenance.yml` | push | Governança — comprovar origem da atualização da main |
| `probe-apis.yml` | push workflow_dispatch | — |
| `producao-prova-continuidade.yml` | workflow_dispatch | Produção — flags efetivas, restauração e rollback |
| `production-backup-monitor.yml` | schedule workflow_dispatch | Produção — saúde do backup diário |

> Os nomes de job desta tabela sao os contextos exigidos na protecao da
> branch `main` (`scripts/governanca/branch-protection.sh`). Renomear um
> job obriga a reaplicar a protecao, sob pena de nenhum PR ser mesclavel.

## 6. Integracoes externas detectadas

```
SEU
api-publica.datajud.cnj.jus.br
api.anthropic.com
api.bcb.gov.br
api.groq.com
api.infosimples.com
api.nuvemfiscal.com.br
api.opencnpj.org
api.portaldatransparencia.gov.br
app.seu-dominio.adv.br
auth.nuvemfiscal.com.br
brasilapi.com.br
busca.inpi.gov.br
calendar.google.com
carf.economia.gov.br
cav.receita.fazenda.gov.br
chat.maritaca.ai
comunica.pje.jus.br
comunicaapi.pje.jus.br
consulta-crf.caixa.gov.br
consultapublica.car.gov.br
dados.mj.gov.br
dadosabertos.almg.gov.br
dadosabertos.camara.leg.br
dadosabertos.web.stj.jus.br
datajud-wiki.cnj.jus.br
depaulateixeira.adv.br
drive.google.com
ejc.depaulateixeira.adv.br
embeddings
evil.com
evolution
example.test
infosimples.com
langfuse
legis.senado.leg.br
link1.com
local
meu.inss.gov.br
new.safernet.org.br
```

> Toda integracao externa do EJC e opt-in por flag de ambiente, com default
> OFF e degradacao graciosa. Dominio nesta lista sem flag correspondente e defeito.

## 7. Decisoes arquiteturais vigentes — PREENCHIMENTO HUMANO

| Decisao | Motivo | Data | Alternativa descartada | Reversivel |
|---|---|---|---|---|
| | | | | |

## 8. Debitos tecnicos conhecidos — PREENCHIMENTO HUMANO

| Debito | Impacto | Prioridade | Issue |
|---|---|---|---|
| | | | |
