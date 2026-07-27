# Runbook de Deploy — Correção Total do EJC (2026-07-06)

Ações de **operação** necessárias para colocar em produção as correções dos
Blocos 1–6 (PRs #116 e #117 mergeadas). Tudo aqui é **idempotente e aditivo** —
mas por segurança, execute **fora do horário do escritório e com backup**.

Containers (docker-compose): `ejc_db` (Postgres+pgvector), `ejc_backend`,
`ejc_worker`, `ejc_redis`, `ejc_frontend`. WORKDIR do backend: `/app`.

---

## 0. Pré-requisitos e janela

- Janela: fora do expediente (o reprocessamento RAG e o seed tocam o banco).
- Ter as variáveis de ambiente do `.env` de produção (`POSTGRES_USER`,
  `POSTGRES_PASSWORD`, `POSTGRES_DB`, etc.).

## 1. BACKUP (obrigatório antes de qualquer passo)

```bash
# Banco (dump lógico completo)
docker exec ejc_db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc \
  > backup_ejc_$(date +%Y%m%d_%H%M).dump

# Uploads (documentos em disco) — ajuste o volume/host path do seu compose
docker run --rm -v ejc_uploads:/data -v "$PWD":/backup alpine \
  tar czf /backup/backup_uploads_$(date +%Y%m%d_%H%M).tgz -C /data .
```

Guarde os dois arquivos fora do host antes de prosseguir.

## 2. DEPLOY (migrations + seeds rodam automaticamente)

O `entrypoint.sh` do backend já roda, nesta ordem, a cada boot:
`alembic upgrade head` → `python seeds/seed_all.py`.

```bash
git pull                      # traz main com as correções
docker compose up -d --build  # rebuild + restart; entrypoint aplica migration 078 e seeds
```

Ao subir, o backend aplica automaticamente:
- **Migration `078_seed_kanban_columns`** (colunas padrão do Kanban — item 5.5).
- **Seeds idempotentes** via `seed_all.main()`:
  - `document_types_master` (item 4.3 — habilita a classificação de documentos),
  - `ejc_skills` + `ejc_skills_ferramentas` (item 5.6 — seletor de Ferramentas de IA).

> Os seeds são **não-fatais**: se um falhar, o boot continua (log `[seed] AVISO...`).

## 3. VERIFICAÇÃO PÓS-DEPLOY

```bash
# Head de migration deve ser 078
docker exec ejc_backend python -m alembic current            # → 078_seed_kanban_columns (head)

# Catálogos semeados (contagens > 0)
docker exec ejc_db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "SELECT (SELECT count(*) FROM document_types_master) AS tipos,
          (SELECT count(*) FROM ejc_skills)            AS skills,
          (SELECT count(*) FROM kanban_columns)        AS colunas_kanban;"
```

Na UI: `/documentos` classifica tipo (coluna "Tipo" ≠ "—"), `/ferramentas-ia`
lista opções, `/kanban` mostra colunas, `/auditoria` traz usuário/módulo/IP.

## 4. REPROCESSAMENTO RAG (item 3.1) — corrige "Sem vetor"

O bug do "100% sem vetor" já foi corrigido no código (o endpoint passou a expor
`status_indexacao`). Para alinhar rótulos defasados no banco:

```bash
# 1) Reconcilia rótulos com os embeddings que JÁ existem (idempotente, barato)
docker exec ejc_backend python -m scripts.reconciliar_status_rag

# 2) SÓ se ainda restarem docs realmente sem chunk vetorizado — re-embedda em lote
docker exec ejc_backend python -m scripts.vetorizar_documentos --batch-size 25
```

Validação: `/conhecimento` deixa de mostrar "Sem vetor" para docs indexados e a
busca semântica retorna resultados coerentes.

## 5. BACKFILL para deployments ANTIGOS (só se necessário)

O `seed_all.py` roda em **todo** boot, então o passo 2 já popula os catálogos.
Se por algum motivo precisar semear sem redeploy (deployment que subiu antes
desta correção e não reiniciou):

```bash
docker exec ejc_backend python -m app.seeds.redesign_seed
docker exec ejc_backend python -m app.seeds.skills_seed
docker exec ejc_backend python -m app.seeds.skills_ferramentas_seed
```

Todos idempotentes (não duplicam; pulam o que já existe).

## 6. ROLLBACK

Cada item é um commit atômico → reversível por `git revert <sha>` isolado. Para
reverter a migration do Kanban (dados aditivos):

```bash
docker exec ejc_backend python -m alembic downgrade 077_deadline_confirmado_doc
```

Rollback total (código + dados): `docker compose down`, restaure o dump do passo
1 (`pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean backup_ejc_*.dump`) e
os uploads, e volte o `git` ao commit anterior.

## 7. TESTE FUNCIONAL EM STAGING (recomendado antes de produção)

- **Fluxo 4.2 (Importação Inteligente):** Novo Caso → Importação Inteligente →
  subir um PDF de teste → criar o caso → conferir que o documento aparece na aba
  **Documentos** do caso (era "Documentos (0)"). Coberto por
  `test_intake_documento_caso_dblevel.py` (roda no job Postgres do CI).
- **Responsividade:** `cd frontend && npm run build && npm run test:responsive`
  (requer `npm i --no-save playwright` e um Chromium; no ambiente Claude web o
  navegador já está pré-instalado). Ou QA manual pelo checklist do
  `docs/historico/RELATORIO_EXECUCAO_BLOCO6_TESTES_EJC_2026-07-06.md`.

## 8. Decisões com default reversível (aplicadas; confirmar se quiser mudar)

- **1.2** métrica HITL mede cobertura de peças de IA revisadas (não o ratio de log).
- **5.11** radar mantém keyword "medicamento"; só "veterinario" foi removido.
