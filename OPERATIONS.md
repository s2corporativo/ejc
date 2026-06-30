# EJC — Manual de Operação

> Sistema de gestão jurídica do escritório De Paula Teixeira. Este documento permite
> que **qualquer desenvolvedor** entenda, rode, e faça deploy do sistema com segurança,
> sem depender de conhecimento prévio. Mantenha-o atualizado a cada mudança de processo.

## 1. Visão geral

- **Backend:** FastAPI (Python 3.11), SQLAlchemy assíncrono, PostgreSQL + pgvector.
- **Frontend:** React + TypeScript + Vite + Tailwind.
- **IA/RAG:** embeddings locais (serviço `ejc_embeddings`, e5-768d) + Groq (LLM) com
  base de conhecimento vetorizada (pgvector). Toda entrada de IA passa por
  sanitização de PII (LGPD) antes de ir ao LLM.
- **Infra:** Docker Compose numa VPS Contabo. Nginx (reverse proxy + HTTPS) na frente.
- **Domínio:** https://ejc.depaulateixeira.adv.br

## 2. Repositório e ambientes

- **GitHub (fonte de verdade do código):** `github.com/s2corporativo/ejc` (privado).
- **Produção:** VPS `/opt/ejc` (repo git local). O deploy leva o código do GitHub/local
  para a VPS via `vps-tools` (SFTP) + rebuild de imagem Docker.
- ⚠️ **Segredos NUNCA vão para o git.** Ver `.gitignore` (cobre `.env*`, `*.bak*`,
  `rclone.conf`, chaves). O `.env` de produção vive só em `/opt/ejc/.env` na VPS.

## 3. Containers (produção)

| Container | Imagem | Papel |
|---|---|---|
| `ejc_backend` | ejc-backend | API FastAPI (porta interna 8000) |
| `ejc_frontend` | ejc-frontend | Nginx servindo o build React (8080→80) |
| `ejc_db` | pgvector/pgvector:pg16 | PostgreSQL + pgvector |
| `ejc_embeddings` | ejc-embeddings | Geração de embeddings (e5-768d) |

> A VPS hospeda OUTROS sistemas (`evolution_api`, `deployment-*`, `mysql`). **Nunca**
> mexer em containers que não sejam `ejc_*` nem fora de `/opt/ejc`.

## 4. Ferramentas de operação (`vps-tools/`)

Rodar de uma pasta que tenha `vps-tools/.env` (host/usuário/senha/porta da VPS).
A senha root é gravada com segurança via `set-vps-password.ps1` (entrada oculta).

- `node vps-tools/run.js "<cmd>"` — executa comando na VPS via SSH.
  - Comandos com **aspas/parênteses** quebram o parser → use base64:
    `node vps-tools/run.js "echo <BASE64> | base64 -d | bash"`.
- `node vps-tools/upload.js <remoto> <local>` — envia 1 arquivo (SFTP).
- `node vps-tools/pull-file.js <remoto> <local>` — baixa 1 arquivo (SFTP).

## 5. Deploy (processo validado)

Pré-requisito: `vps-tools/.env` preenchido. **Sempre faça backup antes** (passo 0).

```powershell
# 0. Backup do banco (gera .sql.gz local + Google Drive)
node vps-tools/run.js "cd /opt/ejc && bash scripts/backup.sh"

# 1. Enviar arquivos alterados do backend (exemplo)
node vps-tools/upload.js /opt/ejc/backend/app/routers/x.py C:\...\backend\app\routers\x.py

# 2. Reconstruir a imagem do backend (inclui código + migrations alembic)
node vps-tools/run.js "cd /opt/ejc && docker compose build backend"

# 3. Trocar o container. O entrypoint.sh roda `alembic upgrade head` + seed
#    ANTES de iniciar o uvicorn → migração aplicada sem janela de erro.
node vps-tools/run.js "cd /opt/ejc && docker compose up -d --no-deps backend"

# 4. Validar
node vps-tools/run.js "curl -fsS http://127.0.0.1:8000/api/health"
node vps-tools/run.js "cd /opt/ejc && docker compose exec -T backend python -m alembic current"
```

- **Frontend:** `docker compose build frontend && docker compose up -d --no-deps frontend`.
- **Zero downtime:** se o build falhar, o container atual continua no ar (a imagem só
  é trocada no `up -d`).

## 6. Banco de dados (migrations)

- Alembic. Head atual: ver `backend/alembic/versions/`. O `entrypoint.sh` aplica
  `alembic upgrade head` automaticamente no boot do backend.
- **Criar migration nova:** adicionar arquivo em `alembic/versions/` com
  `down_revision` = head anterior. Preferir DDL idempotente
  (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`).
- **Nunca** `DROP`/`DELETE` sem backup + confirmação.

## 7. Backup e restauração

- **Backup:** `scripts/backup.sh` (cron diário 02h) → `.sql.gz` local + Google Drive (rclone).
- **Restaurar:** `scripts/restore.sh <arquivo.sql.gz>` — detecta o formato, cria uma
  rede de segurança automática do estado atual antes de sobrescrever, e restaura.

## 8. Modelo de segurança (LGPD / EOAB art. 25)

- **Ownership (IDOR):** `core/ownership.verificar_acesso_caso` é o gate canônico para
  sub-recursos de um caso. Gestão (sócio+) vê tudo; equipe vê seus casos
  (responsável/auxiliar) + casos sem dono. Aplicado em documents, cases, ramos, legal_docs.
- **Isolamento RAG:** conteúdo RESTRITO (`peca_interna`/`precedente_interno`) só é
  recuperável no escopo do próprio cliente (`knowledge_docs.client_id`). Fail-closed:
  sem escopo, conteúdo restrito é excluído da busca.
- **PII:** `services/sanitizer.sanitizar_pii` mascara CPF/CNPJ/processo/e-mail + nomes
  (cliente/parte contrária) ANTES de qualquer envio ao LLM. 2ª barreira `validar_sem_pii`.
- **Re-indexar peças** (aplicar PII/escopo retroativo): `scripts/reindex_pecas_rag.py`
  (idempotente) — `docker exec ejc_backend python reindex_pecas_rag.py`.

## 9. Testes e CI

- **CI (`.github/workflows/ci.yml`):** roda em cada PR. Backend = testes unitários +
  de segurança (sem banco); Frontend = `tsc` + build.
- **Local:** `cd backend && python -m pytest tests -q` (precisa das deps do
  `requirements.txt`). Testes de INTEGRAÇÃO (`test_auth`, `test_casos`, `test_seguranca`,
  etc.) precisam de Postgres+pgvector (banco `ejc_test`, `DATABASE_URL`) — pendente de
  um job de CI de integração com serviço de banco.

## 10. Regras invioláveis (do escritório)

- Nunca inventar leis/jurisprudência (a IA é ancorada no RAG — grounding obrigatório).
- Nunca prometer resultado jurídico.
- Nunca compartilhar dados de um cliente com outro (sigilo).
- Nunca subir segredos ao git. Nunca `DROP`/`DELETE`/`rm -rf` sem backup + confirmação.
