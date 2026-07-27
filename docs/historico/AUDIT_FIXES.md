# AUDIT_FIXES — Correção da Auditoria Funcional EJC (01/07/2026)

Rastreamento da correção dos 24 bugs identificados na Auditoria Funcional EJC.
Ambiente: backend FastAPI · frontend React/TS/Tailwind · PostgreSQL (pgvector) · Docker · VPS `13.140.167.153`.

Legenda de status: ⬜ pendente · 🟡 em andamento · ✅ código pronto · 🚀 aplicado em produção · ⛔ bloqueado (requer confirmação)

## Convenções de segurança adotadas
- **Banco de produção**: todo script SQL/migração é escrito e versionado; a execução em produção só ocorre após **backup (`pg_dump`)** e é registrada aqui.
- **DELETE físico**: nunca executado sem confirmação dupla e explícita. Preferência por *soft delete*/inativação.
- **Git**: commits semânticos por grupo; push em `main` conforme autorizado.

---

## GRUPO 1 — CRÍTICOS
| ID | Descrição | Status | Notas |
|----|-----------|--------|-------|
| BUG-01 | Aba "Societária" — tela branca (crash React) + ErrorBoundary | 🚀 | ErrorBoundary + guardas Number.isFinite em Sociedade |
| BUG-02 | Sala de Guerra — `[object Object]` em Fatores de Risco | 🚀 | `fatoresRiscoToText` (jsonb vazio → "Nenhum fator...") |
| BUG-03 | Título de caso com JSON bruto da IA (DPT-2026-0013) | 🚀 | ia_parser + 422 + dado corrigido |
| BUG-04 | Base RAG — 5.009 documentos "sem_vetor" | 🚀 | reconciliado (5009 vetorizado, 0 sem_vetor) + pipeline + /rag/status |
| BUG-05 | Botão WhatsApp redireciona para `/` | 🚀 | rota `/whatsapp` + página |

## GRUPO 2 — ALTOS
| ID | Descrição | Status | Notas |
|----|-----------|--------|-------|
| BUG-06 | Contagem inconsistente de casos | 🚀 | `/cases/stats` unificado (deleted_at IS NULL) |
| BUG-07 | Taxa de conversão = 10000% (div/0) | 🚀 | backend 0–100/null + front sem ×100 |
| BUG-08 | HITL 0% — fluxo formal de aprovação de peças IA | 🚀 | `PATCH /legal-docs/{id}/aprovar` (campos já existiam) + UI |
| BUG-09 | Perfis duplicados "Clóvis José Soares" | 🚀 | refs reatribuídas p/ af6e457a; f23aeeb8 inativada (soft) + índice uq_users_email |
| BUG-10 | Gráfico de áreas omite caso Trabalhista | 🚀 | por_area inclui trabalhista |

## GRUPO 3 — MÉDIOS
| ID | Descrição | Status | Notas |
|----|-----------|--------|-------|
| BUG-11 | Sala de Guerra sem rota no menu lateral | 🚀 | item na sidebar + toast |
| BUG-12 | Despesas recorrentes R$0,00 — validação | 🚀 | aviso âmbar em Despesas |
| BUG-13 | Dados de teste em produção | 🚀 | 6 casos de teste arquivados (soft); 3 casos reais vivos |
| BUG-14 | Casos encerrados sem mensagem ao adicionar | 🚀 | banner + reabrir |
| BUG-15 | IA "Gerar teses" — loading infinito | 🚀 | AbortSignal.timeout(30s) |
| BUG-16 | Prazos não importam do DataJud | 🚀 | sincronizar_prazos_datajud + endpoints + migração 057 |
| BUG-17 | Intimações sem status/timestamp de captura | 🚀 | `/intimacoes/status-captura` + card |

## GRUPO 4 — BAIXOS / UX
| ID | Descrição | Status | Notas |
|----|-----------|--------|-------|
| BUG-18 | Documento "ddd" | 🚀 | renomeado |
| BUG-19 | "1 cadastrados" — concordância | 🚀 | pluralização |
| BUG-20 | Nome de responsável truncado | 🚀 | tooltip + truncate |
| BUG-21 | Numeração de casos com lacunas — soft delete | 🚀 | delete já é soft (deleted_at); listagens filtram |
| BUG-22 | Modelo IA com/sem prefixo "groq/" | 🚀 | validator no ORM + write paths + dado normalizado |
| BUG-23 | Botões de ícone sem aria-label (Atividades) | 🚀 | aria-label/title |
| BUG-24 | Clientes sem deep link | 🚀 | rota `/clientes/:id` |

---

## Recon produção (read-only) — 2026-07-01
- **BUG-02**: `cases.risco_fatores` é `jsonb` e vem como objeto vazio `{}` → frontend faz `String({})` = `[object Object]`. Fix no render (tratar objeto/vazio).
- **BUG-03**: apenas `DPT-2026-0013` tem título com ```json bruto. Correção pontual de dado.
- **BUG-04**: **reclassificado**. `knowledge_docs`=5022; `status_indexacao`: pendente=4886, indexado=136. `knowledge_chunks`=17967, **0 embeddings nulos**; TODOS os 5022 docs já têm chunk embeddado. Ou seja, a vetorização já ocorreu — o flag `status_indexacao` é que ficou obsoleto. Fix real = reconciliar status (UPDATE barato) + corrigir pipeline para marcar `indexado`. **Não** re-embedar 5k docs.
- **BUG-06**: inconsistência vem de filtro `deleted_at` inconsistente. `cases`=14 linhas, 9 com `deleted_at IS NULL`. Status(todas): triagem=8, encerrado=6. Área(todas): civil=11, trabalhista=2, ambiental=1 (trabalhista existe → BUG-10 é filtro no gráfico).
- **BUG-09**: `users` **não tem coluna cpf**. Nome = `full_name`. Dois "Clóvis" com emails distintos: `f23aeeb8…` (clovis@) e `af6e457a…` (admin@). Merge é manual; unique só em `email`.
- **BUG-13/18**: casos de teste = `DPT-2026-0001..0010` e `0014` (11 casos); doc `ddd` id `743ea7cb…`. ⚠️ maioria dos casos é teste → arquivar exige confirmação explícita.
- **BUG-21**: `cases.deleted_at` já existe (soft-delete parcial). Reusar; adicionar só `excluido_motivo`/`excluido_por`.
- **BUG-12**: `office_expenses` com valor 0/null = 30 (contexto; fix é validação no form).

## Log de execução
- 2026-07-01 — Início. Ambiente mapeado; SSH VPS OK; DB produção = container `ejc_db` (pgvector pg16). Tracker criado.
- 2026-07-01 — Agentes de código (frontend + backend) despachados em paralelo. Recon read-only de produção concluído (acima).
- 2026-07-01 — **PIVÔ CRÍTICO**: descoberto que o workspace local estava DEFASADO e divergente da produção (`/opt/ejc`). Fonte da verdade = produção (decisão do usuário). Ações:
  - Backup completo em `/opt/ejc/backups/audit_20260701`: `ejc_db.dump` (68M, custom format), `src_snapshot.tgz`, `uncommitted_hotfixes.diff` (22k linhas — hotfixes de prod preservados), `git_status.txt`.
  - SFTP download quebrado no servidor (só upload+exec funcionam) → source de prod trazido via base64/exec.
  - Local repo espelhado exatamente à produção (backend/app + frontend/src idênticos; alembic 52 migrações, head único `056_processes_is_principal`). Leftovers do snapshot antigo e migrações espúrias dos agentes anteriores movidos para quarentena (scratch).
  - Commit baseline local `47359b7`.
  - **Descoberta**: a maioria dos campos que a auditoria queria criar JÁ EXISTE em produção → BUG-08 (legal_docs.human_reviewed/revisor_id/notas_revisao/ai_generated), BUG-21 (cases.deleted_at) sem migração. Migrações novas mínimas: `users UNIQUE(email)` e `deadlines(origem, referencia_datajud)`.
  - Agentes de código relançados contra a árvore correta (head 056), migrações encadeadas a partir de `056`.
- 2026-07-01 — Deploy será por arquivo via `vps-tools/sync.js` (upload SFTP OK) + `docker exec ejc_backend alembic upgrade head` (não há auto-migrate) + rebuild frontend. Data-fixes SQL em `scripts/audit_2026-07-01/`.
- 2026-07-01 — **DEPLOY EXECUTADO E VERIFICADO EM PRODUÇÃO**:
  - Descoberto que containers rodam código EMBUTIDO na imagem (sem bind-mount) → deploy exige REBUILD, não só restart. `sync.js` (restart-only) não bastaria para o backend.
  - Backup fresco pré-deploy: `/opt/ejc/backups/audit_20260701_predeploy/ejc_db.dump` (68M).
  - 33 arquivos enviados (15 backend + 2 migrações + 16 frontend), normalizados p/ LF. Confirmado que nenhum hotfix de produção foi sobrescrito (hashes idênticos, exceto CRLF).
  - `docker compose build backend` + recreate + `alembic upgrade head` → head **058**. Colunas `deadlines.origem/referencia_datajud` e índice `uq_users_email` criados. Health `{"status":"ok","database":true}`.
  - Data-fixes aplicados (com backup): BUG-03 (título), BUG-04 (4886 docs → indexado; 0 sem_vetor), BUG-18 (doc ddd), BUG-22 (28 logs normalizados).
  - Smoke test autenticado (superadmin): `/cases/stats`={total:9,ativos:6,encerrados:3,por_area inclui trabalhista} ✓ · `/rag/status`={vetorizado:5009,sem_vetor:0} ✓ · `/intimacoes/status-captura` ✓ · rotas `/aprovar` registradas (401 sem auth).
  - `docker compose build frontend` + recreate. Público TLS 200. Chunk `Whatsapp-*.js` presente.
  - **22/24 bugs em produção.** Pendentes de confirmação explícita: **BUG-09** (merge/desativação de usuário duplicado) e **BUG-13** (arquivar ~11 casos de teste).
- 2026-07-01 — **CONCLUÍDO (24/24)**:
  - BUG-09 aplicado: refs de `f23aeeb8` reatribuídas p/ `af6e457a` (cases 1, case_checklists 2, socios 1, notifications 9); `f23aeeb8` inativada (is_active=false, deleted_at) — soft, reversível. Sem DELETE físico.
  - BUG-13 aplicado: 6 casos de teste arquivados (soft-delete); base agora com 3 casos reais vivos (DPT-0011/0012/0013). `/cases/stats`={total:3,ativos:1,encerrados:2,civil:3} consistente.
  - **GitHub** (conforme decisão do usuário): `origin/main` preservado em branch de backup `backup/main-pre-audit-20260701` (commit c97392f, 40 commits do time), depois **force-push** do baseline+fixes → `origin/main` = `e1ed767`. Recuperável via branch de backup.
  - Scripts SQL: `scripts/audit_2026-07-01/` (01–07). Backups do banco em `/opt/ejc/backups/audit_20260701*`.
  - ⚠️ Observação para o time: `origin/main` foi reescrito. Os 40 commits (PRs #6/#7/#8, portal chat, refatoração UI) estão em `backup/main-pre-audit-20260701` — reconciliar quando conveniente. CI (pytest) pode ficar vermelho pois exige banco.
