# EJC — Guia do repositório para assistentes de IA

## Visão geral

EJC (Ecossistema Jurídico Clovis) v3 — sistema de gestão jurídica full-stack do escritório De Paula Teixeira Advogados. Cobre gestão de casos/processos, clientes, prazos, documentos, financeiro/honorários, portal do cliente e um núcleo de IA jurídica (RAG com pgvector, geração de peças, governança/HITL).

- **Stack**: FastAPI (Python 3.11, SQLAlchemy 2 async) + React 19/TypeScript/Vite + PostgreSQL 16 com pgvector + Redis/Celery + Docker Compose, atrás de Nginx no host.
- **Produção**: VPS Contabo, domínio `https://ejc.depaulateixeira.adv.br`. Deploy via GitHub Actions (`deploy-vps.yml`) ou scripts em `scripts/`.
- **Idioma**: código, rotas, entidades de banco e documentação são em português brasileiro (vocabulário jurídico: `casos`, `prazos`, `honorarios`, `pecas`, `intimacoes`). Siga esse padrão em código novo e commits.

## Papel e regras de execução (governança)

Você é o **executor técnico** do EJC. A especificação e a auditoria são de outro papel (ChatGPT/revisor); o merge e o deploy são atos humanos do titular. As regras canônicas de governança estão em **`docs/GOVERNANCA_IA.md`** — em qualquer divergência entre este arquivo e ele, o canônico prevalece.

**Regras obrigatórias**

1. Nunca alterar a `main` diretamente (sem commit, push ou force push nela).
2. Nunca iniciar uma tarefa sem ler a Issue por inteiro e sem verificar os PRs abertos que tocam os mesmos arquivos.
3. Nunca criar migration sem conferir o head atual e reservar o número em `backend/alembic/MIGRATION_RESERVATIONS.md`.
4. Nunca modificar arquivos que pertencem a outro PR ativo.
5. Toda regra jurídica precisa de fonte oficial, vigência e teste.
6. Toda correção entra com teste de regressão.
7. Não alterar escopo sem registrar a justificativa no PR — achado fora do escopo vira Issue nova.
8. Não fazer merge.
9. Não executar deploy de produção, não acessar o banco de produção, não trabalhar no diretório de produção.
10. Encerrar cada tarefa com relatório: arquivos, comandos, testes, evidências, riscos residuais, limitações e pontos que exigem decisão humana.
11. PR sempre em **draft**, vinculado à Issue, com o template preenchido; correções de review vão na mesma branch e no mesmo PR.
12. Não usar `git push --force`, `git reset --hard`, `git clean -fd`, `rm -rf`, `docker compose down -v`, `docker volume rm`, `dropdb`, `alembic downgrade base` nem `--dangerously-skip-permissions`.
13. Respeitar LGPD, RBAC, isolamento de dados e revisão humana; jamais enfraquecer HITL, gate de citações, sanitização de PII ou kill-switch de IA.

Leitura de apoio: `AGENTS.md` (regras comuns a qualquer agente), `docs/FLUXO_DE_DESENVOLVIMENTO.md` (ciclo Issue → merge), `docs/CRITERIOS_DE_ACEITE.md` (o que o review cobra), `docs/RELEASE_CHECKLIST.md` (o que trava um release).

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

Automation (hooks em .claude/settings.json):
- SessionStart instala o graphify (`pip3 install graphifyy`) e gera `graphify-out/` automaticamente se estiverem ausentes — em ambientes novos (Claude Code web/remoto), apenas aguarde o hook concluir.
- PostToolUse (Write|Edit em arquivos de código) roda `graphify update .` automaticamente; não é preciso rodar manualmente dentro do Claude Code.

## Agentes do projeto (.claude/agents/)

Em toda sessão neste repositório, use o agente `ejc` como PRIMEIRO ponto de contato para qualquer tarefa não trivial — ele já sabe orquestrar os demais agentes e skills abaixo. Não faça o trabalho inteiro na thread principal quando `ejc` (ou um especialista mais específico) puder ser acionado.

SEMPRE delegue trabalho ao agente especialista pertinente em vez de fazer tudo na thread principal. Tarefas que cruzam áreas devem acionar TODOS os agentes pertinentes (em paralelo quando independentes):

- `ejc` — orquestrador principal; ponto de entrada padrão para qualquer tarefa no repo.
- `backend-fastapi` — qualquer mudança em backend/app (endpoints, services, models, schemas, auth, RAG).
- `frontend-react` — qualquer mudança em frontend/src (páginas, componentes, stores, api client, estilos).
- `db-migrations` — schema, migrations Alembic, índices, seeds, pgvector.
- `security-auditor` — SEMPRE acione após mudanças em autenticação, permissões, uploads ou configuração (somente leitura, reporta achados). É o caminho canônico de revisão de segurança no EJC — não use a skill genérica `security-review` isolada, para não gerar relatórios duplicados/divergentes.
- `qa-tests` — escrever/rodar testes após mudanças de comportamento e diagnosticar falhas.
- `app-runner` — sobe e navega a stack (backend+frontend) para validar UI/UX no navegador.
- `ci-triage` — diagnostica falhas do CI (.github/workflows/ci.yml: pytest backend, validação schema/RAG com Postgres pgvector, typecheck+build frontend), lê logs e aplica a correção mínima.
- `code-reviewer` — skill `code-review`; revisa o diff atual em busca de bugs e simplificações.
- `verifier` — skill `verify`; exercita o fluxo alterado ponta a ponta antes de dar por concluído.
- `simplifier` — skill `simplify`; limpa reuso/eficiência/abstração depois que a feature já funciona.
- `researcher` — skill `deep-research`; pesquisa externa multi-fonte (nunca para entender o próprio código do EJC).

Fluxo padrão para uma feature: graphify query → `ejc` (ou agente(s) de implementação pertinente(s) diretamente) → `qa-tests` → `security-auditor` (se tocou área sensível) → `code-reviewer` → `verifier` → `simplifier`. Inclua a regra do graphify no prompt de todo subagente que explora código.

Também existem skills de projeto em `.claude/skills/` (ex.: `ejc-novo-modulo`, `ejc-nucleo-ia`, `gestor-migracao-banco`, `gestor-rag-ia-juridica`, `arquiteto-docker-deploy`, `debugger-sistematico`) — use-as quando a tarefa casar com o nome.

## Estrutura do repositório

```
backend/            FastAPI (app/), Alembic (alembic/), testes (tests/), seeds/
frontend/           React 19 + TypeScript + Vite + Tailwind (src/)
scripts/            Deploy seguro, backup/restore, CI local, guardas de release
nginx/              ejc.conf — proxy reverso do HOST (TLS, /api→8000, /→8080)
vps-tools/          Toolkit Node.js de SSH/SFTP para o VPS (credenciais em vps-tools/.env)
qa/                 Suíte de smoke E2E de homologação (qa/e2e/run_fictitious_smoke.py)
docs/               Documentação técnica; docs/ai/ = arquitetura e políticas de IA
graphify-out/       Grafo de conhecimento do código (ver seção graphify)
.claude/            Agentes, skills e hooks do Claude Code
docker-compose.yml  Stack de produção completa
RUNBOOK_*.md        Procedimentos operacionais (deploy, backup, monitoramento)
RELATORIO_*.md      Relatórios históricos de auditoria/execução — leitura, não procedimento
```

## Backend (backend/app)

- **Entrypoint**: `backend/app/main.py`. Todos os ~180 routers de `app/routers/` são registrados manualmente com prefixo `API = "/api"`. Docs (`/api/docs`) desabilitadas em produção. Ordem de middlewares importa: `AuthMiddleware` (mais interno) → `ClientIPMiddleware` → GZip → CORS.
- **Camadas**: routers finos → lógica de negócio em `app/services/` (~150 módulos) → models SQLAlchemy em `app/models/` → schemas Pydantic em `app/schemas/` (muitos routers definem schemas inline). Pacotes de feature autocontidos em `app/modules/` (auditoria, case_partes, indice_risco, score_juridico). Tarefas Celery em `app/tasks/`.
- **Domínios principais**: auth/2FA (`auth.py`, `users.py`), clientes (`clients.py`, `dossie_cliente.py`, `intake.py`), casos (`cases.py`, `processes.py`, `jornada_caso.py`), prazos/agenda (`deadlines.py`, `tasks.py`, `intimacoes.py`), documentos (`documents.py`, `data_room*.py`, `signatures.py`), IA/RAG (`rag.py`, `ai_core.py`, `peca_geracao*.py`, `ia_governanca.py`), financeiro (`fees.py`, `honorarios_*.py`, `nfse.py`), integrações externas (`datajud.py`, `infosimples_*.py`, `whatsapp.py`, `diario_oficial.py`).
- **Banco**: SQLAlchemy **async** (`asyncpg`) via `app/core/database.py`; dependency `get_db()` fornece `AsyncSession`. Duas URLs: `DATABASE_URL` (async, app) e `DATABASE_URL_SYNC` (psycopg2, Alembic).
- **Config**: `app/core/config.py` (pydantic-settings, `.env`, `get_settings()` com cache). Em produção o boot FALHA se `SECRET_KEY`/chaves PII estiverem ausentes/placeholder ou CORS for wildcard. Exemplo anotado completo em `.env.example`.
- **Auth/segurança**: JWT HS256 (PyJWT) — access token curto + refresh token com JTI revogável em cookie httpOnly; 2FA TOTP (`pyotp`); senhas com `bcrypt` puro (passlib/python-jose foram removidos deliberadamente — não reintroduzir). RBAC hierárquico (superadmin 9 → cliente_externo 1) via `require_roles()`/`require_admin`. Rate limit próprio em `app/core/rate_limit.py` (janela fixa 60s, memória ou Redis) + slowapi. CPF/CNPJ criptografados em repouso (Fernet + índice HMAC cego, `services/pii_crypto.py`).
- **IA/RAG**: TODA chamada de IA passa pelo `services/ai_gateway.py` (política de provedores, kill-switch, sanitização de PII antes de provedor externo, fallback ollama→anthropic→maritaca→groq). Providers isolados em `services/providers/`. Embeddings `intfloat/multilingual-e5-large` 1024d (configurável por `EMBEDDINGS_MODEL`) em `knowledge_chunks.embedding vector(1024)`; retrieval híbrido (pgvector + pg_trgm + FTS português, fusão RRF, rerank opcional). HITL (`AI_REQUIRE_HITL`) e gate anti-alucinação de citações (`citation_gate.py`) são obrigatórios — não contorne.
- **Idioma de design dominante**: tudo que é externo (DataJud, Infosimples, NFSe, WhatsApp, embeddings, Celery, Redis) é opt-in via flag de env, default OFF, e degrada graciosamente sem derrubar o app. Mantenha esse padrão em integrações novas.
- **Premissa de worker único**: rate-limit em memória e APScheduler assumem `uvicorn --workers 1`. Para escalar: `RATE_LIMIT_REDIS_ENABLED=true` e `ENABLE_SCHEDULER=false` nos workers extras (o worker Celery já roda com scheduler desligado).

### Migrations (Alembic)

- Vivem em `backend/alembic/versions/`, numeradas sequencialmente (`049_totp_2fa.py`, ..., `096_...`). Gerar: `python -m alembic revision --autogenerate -m "..."`; aplicar: `python -m alembic upgrade head` (roda automaticamente no boot do container quando `RUN_MIGRATIONS=1`).
- `alembic/env.py` lê `DATABASE_URL_SYNC` e tem guarda `include_name()`: ~30 tabelas existem só em SQL bruto (sem model ORM) — nunca confie apenas em `Base.metadata` para o schema completo, e nunca aceite `drop_table` espúrio do autogenerate.
- Seeds: `backend/seeds/seed_all.py` (bootstrap idempotente do admin, roda no boot) e `backend/app/seeds/` (conteúdo: skills de IA, templates, checklists). Base de conhecimento em `backend/seeds/biblia_ejc/`.

## Frontend (frontend/src)

- **Stack**: React 19, react-router-dom 7, Vite 8, TypeScript 5, Tailwind 3 (`darkMode: "class"`, design system dourado "De Paula Teixeira" no `tailwind.config.js`), Zustand 4, axios, lucide-react. Sem biblioteca de componentes externa — UI própria em `components/`.
- **Rotas**: a fonte da verdade é `src/config/moduleRegistry.tsx` (`STAFF_ROUTES`, `LEGACY_REDIRECTS`, RBAC por rota via `canRoleAccessPath`). `App.tsx` só consome o registry; páginas são lazy-loaded. Área staff sob `Layout` + `StaffOnly`; portal do cliente sob `/portal` (`PortalLayout` + `PortalOnly`). Para módulo novo, registre no registry — não adicione rota solta no App.tsx.
- **API client**: `src/lib/api.ts` — axios com `baseURL: "/api"`. Access token em `localStorage` (`ejc_access`) injetado por interceptor; refresh token em cookie httpOnly gerenciado pelo backend; 401 dispara refresh single-flight com retry; 403 `must_change_password` redireciona para `/trocar-senha`.
- **Estado**: stores Zustand em `src/stores/` (`auth.ts`/`useAuth` com `bootstrap()`, `caseContext.ts`, `moduleLifecycle.ts`, `preferences.ts`, `theme.ts`).
- **Layout de src/**: `pages/` (~70 páginas; `pages/portal/` e `pages/ramos/`), `components/`, `lib/` (api, SSE em `stream.ts`), `config/`, `stores/`, `contexts/`, `types/`, `utils/`. Testes co-localizados (`*.test.ts(x)`).

## Comandos essenciais

Backend (requer Python 3.11; deps nativas p/ OCR/PDF em CI: libmagic, poppler, tesseract, pango/cairo):
```bash
cd backend
pip install -r requirements.txt
pytest                    # suíte completa (~201 arquivos; testes de banco só com RUN_DB_TESTS=1)
ruff check app            # lint
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000   # dev local
```

Frontend (Node 20):
```bash
cd frontend
npm ci
npm run dev       # Vite em :5173, proxy /api → localhost:8000
npm run lint      # = tsc --noEmit (typecheck é o lint); eslint em npm run lint:eslint
npm test          # vitest run (jsdom)
npm run build     # tsc --noEmit && vite build
```

Stack completa: `docker compose up -d --build` (serviços: db pgvector/pg16, redis, backend :8000 loopback, worker Celery, frontend :8080 loopback; perfis opt-in `observability` = Langfuse e `ia-local` = Ollama). CI local sem GitHub: `scripts/ci-local.sh`.

## Testes

- **Backend**: `pytest.ini` com `asyncio_mode = auto`. Não há harness global de banco de teste — o padrão dominante é fake/factory local por arquivo (`_FakeDB`, `TestClient`, `aiosqlite`); alguns testes usam `app.dependency_overrides` para `get_db`/auth. Siga o padrão do arquivo vizinho ao escrever testes novos.
- **Frontend**: `vitest.config.ts` (jsdom, globals, `src/**/*.test.{ts,tsx}`), @testing-library/react. Há também testes de integridade de rotas/links em `src/config/`.
- **E2E/homologação**: `qa/e2e/run_fictitious_smoke.py` exercita auth→clientes→casos→docs→IA→financeiro→portal contra um ambiente de pé.

## CI/CD e deploy

- Workflows em `.github/workflows/`, quase todos **somente `workflow_dispatch`** (para economizar minutos; runner self-hosted `ejc-vps`):
  - `ci.yml` — job `db-validation` (Postgres pgvector de serviço, `alembic upgrade head`, `pytest tests -v`, ruff/pip-audit informativos) + job `frontend-build` (npm ci, test, build).
  - `deploy-vps.yml` — dispara manual ou após CI verde em `main`; rsync para `/opt/ejc` e executa `scripts/deploy_vps_safe.sh` (backup → build → health-poll → migrations/seeds opcionais → rollback automático em erro).
  - `ejc-release-gate.yml` — roda `scripts/ci_guard.sh` (bloqueia marcadores de merge, `.env`/segredos versionados, CORS wildcard).
- Runbooks operacionais: deploy → `RUNBOOK_DEPLOY_FASES_1-3.md`; backup → `RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md` (cron 02:00, pg_dump+uploads → Google Drive via rclone); monitoramento → `RUNBOOK_MONITORAMENTO.md`.

## Regras críticas (não negociar)

1. **Nunca** commitar `.env`, segredos, chaves ou credenciais (o `ci_guard.sh` bloqueia, mas não dependa dele). `vps-tools/.env` também é fora do versionamento.
2. **Nunca** rodar `DROP`/migração destrutiva sem backup — use `scripts/backup.sh` ou o runbook antes.
3. Mudanças em auth, permissões, uploads ou config → acionar `security-auditor` antes de finalizar.
4. Chamadas de IA sempre via `ai_gateway.py`; jamais chamar provider direto de um router, jamais enviar PII não sanitizada para provedor externo, jamais remover HITL ou o citation gate.
5. Rotas novas nascem protegidas: o `AuthMiddleware` + dependencies de RBAC são o caminho; endpoint público é exceção explícita e justificada.
6. Migrations: numeração sequencial, revisar autogenerate manualmente (tabelas raw-SQL!), nunca editar migration já aplicada em produção.
7. Integrações externas novas seguem o padrão do repo: flag de env default OFF + fallback gracioso.
8. Commits e código em português, mensagens descritivas; PRs criados como draft.

## Onde ler mais

- `README.md` — visão operacional (VPS, acesso, estado atual do sistema).
- `docs/ai/` — arquitetura do núcleo único de IA, política de provedores, roteamento de tarefas, LGPD/segurança de IA, HITL.
- `docs/CATALOGO_APIS_EJC.md` — catálogo de APIs; `docs/DESIGN_SYSTEM_EJC.md` e `docs/VISUAL_LAW_EJC.md` — design.
- `graphify-out/GRAPH_REPORT.md` — mapa arquitetural gerado (apenas para revisão ampla).
- `RELATORIO_*.md` na raiz — histórico de auditorias/estabilização; contexto, não procedimento.

---

## Auditoria externa (julho/2026) — achados e plano

Auditoria técnica de 12 rodadas sobre o ambiente de produção, feita **sem acesso ao código-fonte**
(apenas chamadas HTTPS à API e análise dos bundles publicados). Documentação em `docs/auditoria/`:

```
docs/auditoria/README.md                 índice e os 5 achados que não podem se perder
docs/auditoria/plano-lancamento-v3.md    PLANO ATIVO — 7 blocos, um prompt por bloco
docs/auditoria/plano-correcao-v2.md      backlog completo (40+ achados, com reprodução)
docs/auditoria/parecer-arquitetural.md   crítica de produto: o que cortar
docs/auditoria/reduzir-atrito.md         os 15 passos × 8 módulos do fluxo atual
docs/auditoria/relatorios/               as 12 rodadas, com evidência bruta
```

**Leia sob demanda** — apenas o bloco em execução. Itens marcados `[INVESTIGAR]` **não são
diagnóstico fechado**: a auditoria não viu o código. Confirme antes de agir.

### Armadilhas confirmadas em produção

Reproduzíveis pela API. Ao mexer nessas áreas, confirme o comportamento real antes de assumir:

- **Prefixo `/v1/` duplicado.** `/api/v1/v1/despesas` responde 200; `/api/v1/despesas` dá 404.
  Mesmo padrão em `office-contracts`, `partner-withdrawals`, `kanban-columns`,
  `regulatorio/digest-semanal`. O frontend compensa chamando `/v1/x`.
  *(Nota: este arquivo documenta `baseURL: "/api"` em `src/lib/api.ts`, mas o bundle de produção
  traz `baseURL: "/api/v1"`. Verificar qual está correto — pode ser a origem da duplicação.)*
- **Superfície dupla.** Toda rota responde em `/api/` e em `/api/v1/`. Regras por path
  (rate limit, WAF, log, cache) precisam cobrir as duas.
- **Painéis de diagnóstico divergem entre si.** Sobre provedores/modelos de IA, a fonte de verdade
  é a telemetria de `GET /ia-governanca/provedores` — não `/ai/status` nem `/diagnostico/central`.
  O `/diagnostico/central` chega a reportar `backup_offsite` como ligado e desligado na mesma resposta.
- **`GET /system-modules/mapa` subdetecta rotas** e documenta ao menos 5 caminhos incorretos.
  Pista, não verdade.
- **Gravação não transacional entre registros relacionados é uma classe de defeito recorrente:**
  validação que não vincula ao documento, exclusão de caso que não cascateia para as peças,
  conversão Sala Jurídica → Caso que perde `descricao_fatos`, chance de êxito que fica no log e
  não no caso. Ao tocar em fluxo que grava em duas tabelas, verifique a transação.
- **Monitoramento afere execução, não resultado.** Heartbeats checam `last_run_at`, não se o job
  produziu algo — por isso a captura DJEN reporta "ok" há meses sem nunca ter capturado nada.
  Job novo ou corrigido deve monitorar resultado.
- **Vocabulário de status inconsistente.** Backend usa `triagem`/`arquivado`; a interface oferece
  `ativo`/`all`. O primeiro retorna vazio, o segundo dá 500.
- **`qa/e2e/run_fictitious_smoke.py` roda contra produção.** É a origem dos casos
  `HOMOLOG-FICTICIO-*` e da conta `homolog.qa` (perfil superadmin, ativa em produção).
- **Numeração de migrations desatualizada neste arquivo:** a seção de migrations cita `~096`,
  mas o head em produção é `122_route_usage_metrics`.

### Critério de lançamento

Um advogado leva um caso real do início ao protocolo dentro do sistema e considera que foi
**mais fácil do que fazer fora dele**. Enquanto isso não acontecer, o trabalho não está pronto.
Nenhum caso, até a data da auditoria, passou da triagem; nenhuma peça foi protocolada.
