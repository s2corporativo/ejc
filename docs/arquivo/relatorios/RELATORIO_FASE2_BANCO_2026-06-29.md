# Relatório — FASE 2: Reprodutibilidade de Banco (EJC)

**Data:** 2026-06-29 · **Escopo:** tornar o schema reprodutível (Alembic operável + baseline + `processes` + seed + Dockerfile).
**Regra cumprida:** **nada foi executado contra banco algum.** Apenas criação/edição de arquivos, idempotentes e reversíveis. Nenhum `DROP`/`DELETE`. Produção intocada.

---

## 1. Problema (do laudo)

- Alembic **inoperante**: faltavam `alembic.ini`, `env.py`, `script.py.mako`.
- Cadeia de migrations **quebrada**: só existiam `049` e `050`; `049.down_revision="048_processes"` apontava para um arquivo **inexistente** (001–048 perdidas).
- **Sem driver Postgres síncrono** no `requirements.txt` (só `asyncpg`) → Alembic sync nunca rodaria.
- Tabela `processes` consultada em código mas **sem criação** versionada.
- `seeds/seed_all.py` chamado no `deploy.sh` mas **inexistente**.
- `Dockerfile` **não copiava** `alembic/` nem `seeds/` para a imagem.

## 2. O que foi feito (arquivos)

**Criados:**
| Caminho | Função |
|---|---|
| `backend/alembic.ini` | Config Alembic. URL **não** hardcodada (injetada pelo env.py a partir das settings). |
| `backend/alembic/env.py` | **Variante assíncrona** (usa asyncpg — evita depender de psycopg2). Importa **todos** os submódulos de `app.models` para completar `Base.metadata`. |
| `backend/alembic/script.py.mako` | Template padrão de migrations. |
| `backend/alembic/versions/048_processes.py` | **Baseline consolidado** (`down_revision=None`): `CREATE EXTENSION vector` + `Base.metadata.create_all(checkfirst=True)` + tabela `processes` (SQL cru). Materializa a revisão fantasma que a cadeia esperava. |
| `backend/seeds/seed_all.py` | Seed **idempotente** do admin (async). Sem senha hardcoded: lê `ADMIN_EMAIL/ADMIN_NAME/ADMIN_PASSWORD` do ambiente; se a senha faltar, gera aleatória e imprime uma vez. `must_change_password=True`. |

**Editados:**
| Caminho | Mudança |
|---|---|
| `backend/alembic/versions/049_totp_2fa.py` | `add_column` → `ADD COLUMN IF NOT EXISTS` (idempotente; o baseline já cria as colunas totp via create_all). |
| `backend/Dockerfile` | `COPY alembic`, `COPY alembic.ini`, `COPY seeds` (antes só `COPY app`). |

## 3. Validação executada (sem banco)

- ✅ **Sintaxe** (`py_compile`) OK em env.py, 048, 049, 050, seed_all.
- ✅ **Completude do metadata:** o importador do env.py popula **65 tabelas** em `Base.metadata` sem erros de import (antes o `__init__` cobria ~40). Logo o `create_all` do baseline cobre todo o schema ORM.
- ✅ **Cadeia Alembic resolve** (antes quebrada):
  `<base> → 048_processes → 049_totp_2fa → 050_novos_modulos (head)` — head único, sem erro de revisão ausente.
- ✅ Todas as migrations **idempotentes** (048 checkfirst/IF NOT EXISTS; 049 agora IF NOT EXISTS; 050 já era).

## 4. ⚠️ Procedimento seguro de aplicação (ação manual)

O banco de **produção já tem o schema**. NÃO rode `alembic upgrade` cru sem antes verificar o estado:

**Produção (uma vez):**
1. Conferir o estado do Alembic no banco:
   `docker exec ejc_postgres psql -U ejc_user -d ejc_db -c "SELECT version_num FROM alembic_version;"`
   (se a tabela não existir, o Alembic nunca foi inicializado neste banco)
2. **Alinhar sem executar** (recomendado): marcar a revisão atual como aplicada:
   `docker compose exec -T backend alembic stamp 050_novos_modulos`
   → a partir daí o Alembic está sincronizado; migrations futuras rodam normalmente.
3. (Tudo é idempotente, então um `alembic upgrade head` seria seguro **se** `version_num` já pertencer à cadeia; mas se contiver um id fora dela — ex.: `048` puro — o upgrade falha de forma inofensiva. Por isso `stamp` é a rota preferida.)

**Ambiente limpo / DR (agora funciona):** `deploy.sh` roda `alembic upgrade head` (cria todo o schema via baseline → 049 → 050) e depois `python seeds/seed_all.py` (cria o admin). Defina `ADMIN_EMAIL`/`ADMIN_PASSWORD` no `.env` antes.

## 5. Limitações / pendências honestas

- **Tabela `processes` é uma RECONSTRUÇÃO** a partir de `routers/processes.py` e `services/processo_service.py` (que divergem: um usa `is_principal`, outro `processo_principal_id` — incluí **ambas** as colunas). Como é `CREATE TABLE IF NOT EXISTS`, **não altera** a tabela real de produção. Antes de confiar nela para DR, validar contra:
  `pg_dump --schema-only -t processes` da produção e ajustar o baseline se houver diferença.
- **65 tabelas ORM vs ~83 citadas no README:** a diferença são as 5 tabelas SQL-cru da `050` (cobertas), `processes` (coberta) e possíveis **views/tabelas legadas** não modeladas (ex.: `vw_atividades`). Recomenda-se um `pg_dump --schema-only` de produção para fechar a diferença numa validação de DR.
- **As 5 tabelas da `050` e `processes` seguem sem modelo ORM** (criadas por SQL). Transformá-las em modelos ORM é desejável (autogenerate consistente) mas pertence à Fase 4/5 — não foi feito aqui para não arriscar divergência de schema.
- **Não criei modelos novos nem toquei em IA/RAG/layout.** `config.py` (default de dev `ejc_pass`) permanece intocado (é "banco"/credencial — tratar na rotação da Fase 0).

## 6. Próximas fases (não executadas)

- **Fase 3:** isolamento de dados (RAG por `client_id`/`case_id`; ownership em `documents`/`legal_docs`/`ramos`).
- **Fase 4:** consolidação de domínios duplicados (IA, honorários, dossiê).
- **Fase 5:** higiene (remover `.venv-codex`, `generated/`, órfãos; modelos ORM para as tabelas SQL-cru; testes).
