# RELATÓRIO ETAPA 6D — AMBIENTE DE VALIDAÇÃO ROW-LEVEL (Postgres + pgvector)

Data: 2026-07-02
Branch: `audit-ejc-graphify-etapa1`

## Objetivo

Fechar as validações que não podiam rodar sem banco: (1) o isolamento do RAG por cliente (Bloco 5) no nível de linha real, e (2) a comparação `Base.metadata × schema real` (Camada 2 do teste de schema, Etapa 6B/H3). Como esta máquina não tem Docker/Postgres, o entregável é o **ambiente pronto para rodar** — em CI e localmente — não a execução aqui.

## O que foi preparado

### 1. Teste row-level real de isolamento do RAG — `backend/tests/test_rag_isolation_dblevel.py`
Prova, com dados reais no banco, que:
- `precedente_interno` (categoria RESTRITA) do cliente A **nunca** aparece numa busca escopada ao cliente B (e vice-versa);
- sem escopo (`scope_client_id=None`), nenhum conteúdo restrito é recuperado (fail-closed);
- conteúdo **público** (súmula) aparece independentemente do escopo (o isolamento não quebrou a busca de legislação/jurisprudência).

Determinístico: usa o caminho **textual** (`ILIKE`) do `buscar_contexto_rag` (embeddings off = padrão), então dois docs com o mesmo termo mas `client_id` diferentes são diferenciados **apenas** pelo filtro de escopo — sem depender de tuning de similaridade semântica. Insere e limpa seus próprios dados (UUIDs únicos, `DELETE` no `finally`).

Gate: roda só com `RUN_DB_TESTS=1`. Sem isso, faz `skip` — nunca conecta em ambiente sem banco nem em produção.

### 2. Job de CI `db-validation` — `.github/workflows/ci.yml`
Sobe `pgvector/pgvector:pg16` como service, cria as extensões (`vector`, `pg_trgm`, `pgcrypto`), roda `alembic upgrade head` e executa:
- `tests/test_schema_sync.py` (com `SCHEMA_CHECK_DATABASE_URL` → Camada 2 comparando metadata × banco real);
- `tests/test_rag_isolation_dblevel.py` (com `RUN_DB_TESTS=1` → isolamento row-level).

Roda em todo push/PR para `main`, junto dos jobs existentes (`backend-tests`, `frontend-build`).

### 3. Recipe local (se você tiver Docker)
```bash
# 1) Subir Postgres com pgvector
docker run -d --name ejc-validacao \
  -e POSTGRES_USER=ejc_user -e POSTGRES_PASSWORD=ejc_pass -e POSTGRES_DB=ejc_db \
  -p 5432:5432 pgvector/pgvector:pg16

# 2) Extensões
docker exec ejc-validacao psql -U ejc_user -d ejc_db \
  -c "CREATE EXTENSION IF NOT EXISTS vector;" \
  -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" \
  -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

# 3) Migrations + testes (no diretório backend/)
cd backend
pip install -r requirements.txt psycopg2-binary
export DATABASE_URL="postgresql+asyncpg://ejc_user:ejc_pass@localhost:5432/ejc_db"
export DATABASE_URL_SYNC="postgresql://ejc_user:ejc_pass@localhost:5432/ejc_db"
export SCHEMA_CHECK_DATABASE_URL="postgresql://ejc_user:ejc_pass@localhost:5432/ejc_db"
export APP_ENV=development RUN_DB_TESTS=1
python -m alembic upgrade head
python -m pytest tests/test_schema_sync.py tests/test_rag_isolation_dblevel.py -v

# 4) Limpar
docker rm -f ejc-validacao
```
> Este é um banco EFÊMERO de validação — **não** é o banco de produção (que fica só na VPS). Nenhum dado real é tocado.

## Lacuna encontrada ao preparar (não corrigida — fora de escopo/prod)

**`psycopg2` (driver SYNC) ausente do `requirements.txt` e do Dockerfile.** O `alembic/env.py` usa driver sync e o `check` de schema também. O `.venv-codex` local tem `psycopg2-binary` (instalado à mão), mas produção **não** — um deploy limpo que rode `alembic upgrade head` falharia com `ModuleNotFoundError: psycopg2`. O job de CI contorna instalando `psycopg2-binary` explicitamente. **Recomendação:** adicionar `psycopg2-binary` ao `requirements.txt` (mudança de dependência de produção — deixei para sua aprovação).

## Limitações honestas

- **Não executei** nada disto aqui (sem Docker local). A primeira rodada do job `db-validation` no GitHub é a validação real; se algo falhar (ex.: uma migration não idempotente em banco limpo, ou o teste row-level precisar de um ajuste fino), será um achado legítimo a corrigir — não um falso negativo.
- O teste row-level cobre o `precedente_interno` via caminho textual. O caminho **semântico** (pgvector, com `EMBEDDINGS_ENABLED=true`) não é exercitado — está dormente por padrão (achado M11). Quando embeddings forem ativados, vale estender o teste para o caminho vetorial.

## Próximos passos
1. Fazer o push da branch e observar o job `db-validation` no GitHub Actions (é onde a validação de fato roda).
2. Se verde: o isolamento do RAG (lotes já feitos) e a coerência schema×banco ficam comprovados em banco real — base sólida para retomar os demais call sites do Bloco 5 com segurança.
3. Decidir sobre adicionar `psycopg2-binary` ao `requirements.txt`.
