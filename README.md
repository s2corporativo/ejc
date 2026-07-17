# EJC — Ecossistema Jurídico Clovis
## Sistema de Gestão Jurídica — De Paula Teixeira Advogados

Sistema full-stack de gestão jurídica com IA governada (Núcleo Único, RAG com
pgvector, barreira LGPD com pseudonimização reversível, trilha AILog obrigatória).

---

## Stack Técnica

| Camada | Tecnologia |
|--------|-----------|
| Backend | FastAPI (Python 3.11) + SQLAlchemy async + Pydantic v2 |
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS + Zustand |
| Banco | PostgreSQL 16 + pgvector (migrations Alembic — head `096`) |
| IA | Anthropic (Claude, principal) + Groq (fallback) + Ollama (opcional, off em prod) |
| Embeddings | intfloat/multilingual-e5-large — 1024d, local via fastembed (coluna `vector(1024)`, migration 096) |
| Reranker RAG | jinaai/jina-reranker-v2-base-multilingual (cross-encoder local, fail-safe) |
| Storage | Google Drive (Service Account — credenciais via `.env`, não versionadas) |
| E-mail | SMTP (configurado via `.env`) |
| Containers | Docker + Docker Compose |

---

## Acesso à VPS (Contabo)

| Item | Valor |
|------|-------|
| Domínio ativo | `https://ejc.depaulateixeira.adv.br` |
| IP / SSH User | definidos em secrets do GitHub (`VPS_HOST`/`VPS_USER`) e `.env` locais — não versionar |
| Caminho na VPS | `/opt/ejc` |

**Credenciais:** nunca registrar senhas reais neste README. Gerenciar acessos
pelo painel de usuários do EJC ou por procedimento administrativo seguro.

---

## Deploy (caminho canônico)

O deploy é feito pelo workflow **`.github/workflows/deploy-vps.yml`**
(disparo manual via `workflow_dispatch`; requer secrets `VPS_*`), que
sincroniza o código por rsync (sem `--delete`; nunca toca `.env`, `uploads/`,
`backups/`) e executa **`scripts/deploy_vps_safe.sh`** na VPS — com backup
automático do banco **antes** de aplicar migrations.

- Runbook de emergência/rollback do embedding: `RUNBOOK_MIGRACAO_EMBEDDING_1024.md`
- CI: `.github/workflows/ci.yml` (manual, runner self-hosted na VPS) e
  `scripts/ci-local.sh` (gate local via `.githooks/pre-push`) — ver `docs/CI_SEM_GITHUB.md`

Não use fluxos manuais de upload de arquivo avulso (o antigo `vps-tools/` é
legado de manutenção pontual, excluído do rsync do deploy).

## Backup

- **Rotina diária canônica:** `scripts/backup/backup_diario.sh` (pg_dump -Fc com
  verificação de integridade + rotação) — cron na VPS, ver `RUNBOOK_BACKUP.md`
  e `RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md` (envio ao Google Drive).
- **Restauração:** `scripts/backup/restaurar_backup.sh` (ou `scripts/restore.sh`).
- `scripts/backup.sh` permanece apenas como snapshot pré-deploy usado pelo
  `deploy_vps_safe.sh`.

## Testes

```bash
# Backend (Postgres+pgvector reais):
cd backend && RUN_DB_TESTS=1 python -m pytest -q

# Frontend:
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

---

## Documentação

- `docs/` — documentação técnica viva (IA, design system, CI, runner, etc.)
- `docs/historico/` — relatórios/laudos/planos de auditorias já concluídas (arquivo morto)
- Runbooks operacionais vivos na raiz: `RUNBOOK_BACKUP.md`,
  `RUNBOOK_MONITORAMENTO.md`, `RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md`,
  `RUNBOOK_MIGRACAO_EMBEDDING_1024.md`

## Alertas de Segurança

- **NUNCA** subir `.env` para o git.
- **NUNCA** fazer DROP sem backup prévio.
- Não subir uvicorn com `--workers N` sem Redis (rate limit/anti-brute-force
  são por processo — ver `entrypoint.sh`).
- `docker-compose.override.yml` é local da VPS (não versionado) — use
  `docker-compose.override.example.yml` como base.
