# EJC — Guia do repositório para assistentes de IA

## Visão geral

EJC (Ecossistema Jurídico Clovis) v3 — sistema de gestão jurídica full-stack do escritório De Paula Teixeira Advogados. Cobre gestão de casos/processos, clientes, prazos, documentos, financeiro/honorários, portal do cliente e um núcleo de IA jurídica (RAG com pgvector, geração de peças, governança/HITL).

- **Stack**: FastAPI (Python 3.11, SQLAlchemy 2 async) + React 19/TypeScript/Vite + PostgreSQL 16 com pgvector + Redis/Celery + Docker Compose, atrás de Nginx no host.
- **Produção**: VPS Contabo, domínio `https://ejc.depaulateixeira.adv.br`. Deploy via GitHub Actions (`deploy-vps.yml`) ou scripts em `scripts/`.
- **Idioma**: código, rotas, entidades de banco e documentação são em português brasileiro (vocabulário jurídico: `casos`, `prazos`, `honorarios`, `pecas`, `intimacoes`). Siga esse padrão em código novo e commits.

## Papel e regras de execução (governança)

Você é o **executor técnico** do EJC. A especificação e a auditoria são de outro papel (ChatGPT/revisor); merge e deploy são **automáticos** quando todos os gates estiverem verdes (governança §6-A) — o titular intervém apenas nas exceções fechadas dessa seção. As regras canônicas de governança estão em **`docs/GOVERNANCA_IA.md`** — em qualquer divergência entre este arquivo e ele, o canônico prevalece.

**Regras obrigatórias**

1. Nunca alterar a `main` diretamente (sem commit, push ou force push nela).
2. Nunca iniciar uma tarefa sem ler por inteiro o pedido que a originou — a Issue, quando existe; a mensagem do titular, quando a tarefa chega por chat (ver "Regras de decisão") — e sem verificar os PRs abertos que tocam os mesmos arquivos.
3. Nunca criar migration sem conferir o head atual e reservar o número em `backend/alembic/MIGRATION_RESERVATIONS.md`.
4. Nunca modificar arquivos que pertencem a outro PR ativo.
5. Toda regra jurídica precisa de fonte oficial, vigência e teste.
6. Toda correção entra com teste de regressão.
7. Não alterar escopo sem registrar a justificativa no PR — achado fora do escopo vira Issue nova.
8. Merge é automático via `auto-integracao.yml` quando todos os gates estiverem verdes e o diff
   não tocar exceção do §6-A da governança; o agente não força integração de PR retido.
9. Deploy ocorre somente pela esteira automatizada (CI verde na `main` → `deploy-vps.yml`, com
   backup, health e rollback); não acessar o banco de produção nem trabalhar no diretório de produção.
10. Encerrar cada tarefa com relatório: arquivos, comandos, testes, evidências, riscos residuais, limitações e pontos que exigem decisão humana.
11. PR vinculado à Issue e com o template preenchido; no fluxo autônomo o PR nasce **pronto para
    integração** (draft apenas quando cai em exceção do §6-A ou o trabalho está incompleto);
    correções de review vão na mesma branch e no mesmo PR.
12. Não usar `git push --force`, `git reset --hard`, `git clean -fd`, `rm -rf`, `docker compose down -v`, `docker volume rm`, `dropdb`, `alembic downgrade base` nem `--dangerously-skip-permissions`.
13. Respeitar LGPD, RBAC, isolamento de dados e revisão humana; jamais enfraquecer HITL, gate de citações, sanitização de PII ou kill-switch de IA.

Leitura de apoio: `AGENTS.md` (regras comuns a qualquer agente), `docs/FLUXO_DE_DESENVOLVIMENTO.md` (ciclo Issue → merge), `docs/CRITERIOS_DE_ACEITE.md` (o que o review cobra), `docs/RELEASE_CHECKLIST.md` (o que trava um release).

## Regras de decisão

O que trava trabalho não é a regra restritiva — é a regra que não diz o que fazer no caso
concreto. Esta seção fecha as três lacunas que mais produzem hesitação ou improviso.

**Tarefa sem Issue.** `docs/FLUXO_DE_DESENVOLVIMENTO.md` diz que nenhum trabalho começa sem
Issue, e o desenho é esse mesmo. Mas o titular também pede direto por chat, e aí a regra
literal proibiria executar qualquer pedido dele. O pedido do titular **é** a autorização para
começar — não espere alguém abrir a Issue. Só que a tarefa precisa terminar registrada: abra
você mesmo a Issue (problema, escopo, fora do escopo, critérios de aceite) e vincule o PR com
`Closes #NNN`. Não é burocracia — a trava `.github/workflows/governanca.yml` **reprova PR sem
`#<numero>` no corpo**, e o CI é quem tem a última palavra. Quando a Issue já existe, ela manda.

**O que decidir sozinho.** Decida e siga, sem perguntar: como implementar dentro do escopo
pedido; qual arquivo tocar; como testar; nomes, estrutura e refatoração local; corrigir o que
o próprio pedido quebra. `docs/GOVERNANCA_IA.md` §10 exige autorização explícita para migration,
auth/RBAC, contrato público de API, CI/CD, exclusão de código e troca de dependência — e o
pedido do titular que **implica** um desses itens já é essa autorização (pedir "corrija o
cadastro de cliente" autoriza a migration que a correção exige). Autorização não se estende
ao vizinho: ela cobre o que o pedido implica, não o que você achou pelo caminho.

**Quando parar e perguntar.** Só quando seguir sem resposta produziria trabalho inútil ou
irreversível: duas leituras plausíveis do pedido levam a resultados materialmente diferentes;
a mudança apaga dado ou quebra contrato já em uso; o achado contraria uma decisão permanente
do titular (§11). Nos demais casos, assuma a leitura mais provável, **escreva a suposição no
PR** e siga. Achado fora do escopo não interrompe a tarefa: termina o que foi pedido e reporta
o achado no relatório final.

**Quando as regras conflitam.** Ordem de precedência: `docs/GOVERNANCA_IA.md` → este arquivo →
`AGENTS.md` → skills e agentes. Conflito encontrado não se resolve escolhendo em silêncio:
corrige-se no mesmo PR, ou vira apontamento no relatório.

## graphify — índice auxiliar, não fonte da verdade

`graphify-out/` guarda um grafo de símbolos do código (nós, comunidades, relações entre
arquivos). Serve para **localizar** código gastando pouco contexto: `graphify query
"<pergunta>"`, `graphify explain "<conceito>"`, `graphify path "<A>" "<B>"`.
`graphify-out/GRAPH_REPORT.md` só para revisão arquitetural ampla.

**O que ele não é.** Não é a fonte da verdade e não substitui ler o arquivo. O grafo é AST,
indexa símbolo — não indexa prosa, e por isso não ajuda em `.md`. Ele também envelhece: em
2026-08-02 o grafo versionado estava 6 dias e 147 commits atrás do repositório, e uma consulta
por "onde fica o registro de rotas do backend" devolveu 294 nós truncados em 51, nenhum deles o
`backend/app/main.py` que era a resposta. **Confirme no arquivo antes de editar ou concluir** —
principalmente ao afirmar que algo não existe.

Automação (hooks em `.claude/settings.json`):
- **SessionStart** instala o graphify (`pip3 install graphifyy`) e roda `graphify update .`
  (incremental, AST-only, sem custo de API) — antes só gerava o grafo quando ausente, o que
  deixava o índice envelhecer indefinidamente.
- **PostToolUse** (`Write|Edit` em arquivo de código) atualiza o grafo; não rode à mão.
- **PreToolUse** (`.claude/hooks/orienta_graphify.py`) lembra do graphify **uma vez por sessão**,
  só em arquivo de código, e avisa quando o grafo está mais velho que o último commit.

## Agentes do projeto (.claude/agents/)

Delegue quando a delegação paga o próprio custo: trabalho que cruza várias áreas, exploração
ampla de código, ou uma frente que cabe inteira num especialista. Para uma edição pontual,
uma pergunta sobre o repositório ou uma correção de duas linhas, fazer na thread principal é
mais rápido e mais rastreável — subagente custa contexto e devolve resumo, não o diff.

`ejc` é o orquestrador quando a tarefa é grande e ainda não está fatiada; quando já se sabe
qual é a área, acione o especialista direto. Frentes independentes vão em paralelo, na mesma
mensagem. Quem responde pelo resultado continua sendo o executor — o relatório do subagente
é insumo, e achado de subagente que você não conferiu não vira afirmação sua no PR:

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
.claude/            Agentes (agents/), skills (skills/) e hooks (hooks/) do Claude Code
docker-compose.yml  Stack de produção completa
RUNBOOK_*.md        Procedimentos operacionais (deploy, backup, monitoramento)
RELATORIO_*.md      Relatórios históricos de auditoria/execução — leitura, não procedimento
```

## Backend (backend/app)

- **Entrypoint**: `backend/app/main.py`. Todos os 163 routers de `app/routers/` são registrados manualmente com prefixo `API = "/api"`. Docs (`/api/docs`) desabilitadas em produção. Ordem de middlewares importa: `AuthMiddleware` (mais interno) → `ClientIPMiddleware` → GZip → CORS.
- **Camadas**: routers finos → lógica de negócio em `app/services/` (~150 módulos) → models SQLAlchemy em `app/models/` → schemas Pydantic em `app/schemas/` (muitos routers definem schemas inline). Pacotes de feature autocontidos em `app/modules/` (auditoria, case_partes, indice_risco, score_juridico). Tarefas Celery em `app/tasks/`.
- **Domínios principais**: auth/2FA (`auth.py`, `users.py`), clientes (`clients.py`, `dossie_cliente.py`, `intake.py`), casos (`cases.py`, `processes.py`, `jornada_caso.py`), prazos/agenda (`deadlines.py`, `tasks.py`, `intimacoes.py`), documentos (`documents.py`, `data_room*.py`, `signatures.py`), IA/RAG (`rag.py`, `ai_core.py`, `peca_geracao*.py`, `ia_governanca.py`), financeiro (`fees.py`, `honorarios_*.py`, `nfse.py`), integrações externas (`datajud.py`, `infosimples_*.py`, `whatsapp.py`, `diario_oficial.py`).
- **Banco**: SQLAlchemy **async** (`asyncpg`) via `app/core/database.py`; dependency `get_db()` fornece `AsyncSession`. Duas URLs: `DATABASE_URL` (async, app) e `DATABASE_URL_SYNC` (psycopg2, Alembic).
- **Config**: `app/core/config.py` (pydantic-settings, `.env`, `get_settings()` com cache). Em produção o boot FALHA se `SECRET_KEY`/chaves PII estiverem ausentes/placeholder ou CORS for wildcard. Exemplo anotado completo em `.env.example`.
- **Auth/segurança**: JWT HS256 (PyJWT) — access token curto + refresh token com JTI revogável em cookie httpOnly; 2FA TOTP (`pyotp`); senhas com `bcrypt` puro (passlib/python-jose foram removidos deliberadamente — não reintroduzir). RBAC hierárquico (superadmin 9 → cliente_externo 1) via `require_roles()`/`require_admin`. Rate limit próprio em `app/core/rate_limit.py` (janela fixa 60s, memória ou Redis) + slowapi. CPF/CNPJ criptografados em repouso (Fernet + índice HMAC cego, `services/pii_crypto.py`).
- **IA/RAG**: TODA chamada de IA passa pelo `services/ai_gateway.py` (política de provedores, kill-switch, sanitização de PII antes de provedor externo, fallback ollama→anthropic→maritaca→groq). Providers isolados em `services/providers/`. Embeddings `intfloat/multilingual-e5-large` 1024d (configurável por `EMBEDDINGS_MODEL`) em `knowledge_chunks.embedding vector(1024)`; retrieval híbrido (pgvector + pg_trgm + FTS português, fusão RRF, rerank opcional). HITL (`AI_REQUIRE_HITL`) e gate anti-alucinação de citações (`citation_gate.py`) são obrigatórios — não contorne.
- **Idioma de design dominante**: tudo que é externo (DataJud, Infosimples, NFSe, WhatsApp, embeddings, Celery, Redis) é opt-in via flag de env, default OFF, e degrada graciosamente sem derrubar o app. Mantenha esse padrão em integrações novas.
- **Premissa de worker único**: rate-limit em memória e APScheduler assumem `uvicorn --workers 1`. Para escalar: `RATE_LIMIT_REDIS_ENABLED=true` e `ENABLE_SCHEDULER=false` nos workers extras (o worker Celery já roda com scheduler desligado).

### Migrations (Alembic)

- Vivem em `backend/alembic/versions/`, numeradas sequencialmente (`049_totp_2fa.py`, ..., `150_indices_fk_espinha_dominio.py`). O head muda a cada merge: **confirme com `cd backend && python -m alembic heads`** em vez de confiar neste número. Gerar: `python -m alembic revision --autogenerate -m "..."`; aplicar: `python -m alembic upgrade head` (roda automaticamente no boot do container quando `RUN_MIGRATIONS=1`).
- `alembic/env.py` lê `DATABASE_URL_SYNC` e tem guarda `include_name()`: ~30 tabelas existem só em SQL bruto (sem model ORM) — nunca confie apenas em `Base.metadata` para o schema completo, e nunca aceite `drop_table` espúrio do autogenerate.
- Seeds: `backend/seeds/seed_all.py` (bootstrap idempotente do admin, roda no boot) e `backend/app/seeds/` (conteúdo: skills de IA, templates, checklists). Base de conhecimento em `backend/seeds/biblia_ejc/`.

## Frontend (frontend/src)

- **Stack**: React 19, react-router-dom 7, Vite 8, TypeScript 5, Tailwind 3 (`darkMode: "class"`, design system dourado "De Paula Teixeira" no `tailwind.config.js`), Zustand 4, axios, lucide-react. Sem biblioteca de componentes externa — UI própria em `components/`.
- **Rotas**: a fonte da verdade é `src/config/moduleRegistry.tsx` (`STAFF_ROUTES`, `LEGACY_REDIRECTS`, RBAC por rota via `canRoleAccessPath`). `App.tsx` só consome o registry; páginas são lazy-loaded. Área staff sob `Layout` + `StaffOnly`; portal do cliente sob `/portal` (`PortalLayout` + `PortalOnly`). Para módulo novo, registre no registry — não adicione rota solta no App.tsx.
- **API client**: `src/lib/api.ts` — axios com `baseURL: "/api/v1"` (constante `API_BASE_URL`, linha 9). O interceptor de request **remove** prefixo repetido (`/api/v1/`, `/api/`, `/v1/`) do `config.url`, então dentro do cliente `api` os caminhos se escrevem sem prefixo (`/casos`, não `/api/casos`). Quem usa `axios` cru — como `refreshAccessToken` — precisa do path REAL do backend (`/api/auth/refresh`, sem `v1`). Access token em `localStorage` (`ejc_access`) injetado por interceptor; refresh token em cookie httpOnly gerenciado pelo backend; 401 dispara refresh single-flight com retry; 403 `must_change_password` redireciona para `/trocar-senha`.
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

Frontend (Node 22 — `package.json` exige `>=22.22.0`; o CI usa 22.22.2):
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

- Workflows em `.github/workflows/`. Os que declaram `on: pull_request` são `ci.yml`, `ejc-release-gate.yml`, `governanca.yml`, `continuity-ui-gates.yml`, `architecture-inventory.yml`, `backup-gdrive-activation.yml` e `rag-production-activation.yml`. Só operação de ambiente (`deploy-vps.yml`, `producao-prova-continuidade.yml`, `frontend-ci.yml`) é `workflow_dispatch`, no runner self-hosted `ejc-vps`.

  > **Declarar o gatilho não é o mesmo que rodar — não confie no `grep`.** A orientação anterior aqui mandava conferir com `grep -A4 '^on:' .github/workflows/*.yml`, e esse método **não detecta o defeito mais comum**: um workflow desligado pela UI fica `disabled_manually` na API do GitHub, com o arquivo versionado intacto e o `on:` correto. Foi assim que `governanca.yml`, `continuity-ui-gates.yml`, `architecture-inventory.yml` e `auto-integracao.yml` passaram semanas sem rodar em PR nenhum sem ninguém notar (Issue #1235) — inclusive recebendo melhorias enquanto estavam desligados. A verificação que vale é o **estado na API**, não o arquivo:
  >
  > ```bash
  > gh api repos/s2corporativo/ejc/actions/workflows \
  >   --jq '.workflows[] | select(.state != "active") | "\(.state)\t\(.path)"'
  > ```
  >
  > Um segundo modo de falha não aparece em nenhum dos dois: com a cota de Actions esgotada, workflow `active` e com gatilho certo simplesmente **não aloca runner** — os runs ficam `queued` indefinidamente ou terminam em `startup_failure` com `jobs: []`. Vale o critério canônico já usado no repositório: `startup_failure`, `jobs=[]`, `steps=null` ou ausência de logs é **infraestrutura, não sucesso**. Antes de afirmar que um PR está verde, confirme que os checks existem — PR sem check algum não é PR aprovado.

  Referência dos gatilhos declarados:
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
- `docs/CLAUDE_CODE_PERMISSOES.md` — lista de permissões proposta para `.claude/settings.json`
  (reduz aprovação de comando de rotina); aplicação é decisão do titular.
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

> **Revarredura de 2026-08-22 (Issue #1237).** Esta lista descreve a auditoria externa de
> **julho, contra produção**, e o repositório andou desde então. Seis itens foram remedidos
> com a stack local de pé (Postgres 16 + pgvector, migrations do zero, backend e frontend
> rodando) e **já não reproduzem**: prefixo `/v1/` duplicado, `?status=all` → 500, exclusão de
> caso sem cascata, smoke E2E contra produção, `system-modules/mapa` e o monitoramento do
> DJEN. Cada um está marcado abaixo com o que a medição mostrou. **Não re-audite os marcados
> como resolvidos sem antes reproduzir** — foi assim que esta rodada gastou tempo.
>
> A lição que se repetiu: **item de auditoria carrega o tamanho que o problema tinha aos olhos de
> quem passou correndo por ele.** A nota errou nas duas direções — subestimou (o gate de citações
> era mais cego do que ela dizia: não enxergava diploma por extenso) e superestimou (`chance de
> êxito` e `system-modules/mapa` não eram defeito, eram desenho). Confirme no código **antes** de
> agir sobre qualquer item desta lista.

- ~~**Prefixo `/v1/` duplicado.**~~ **RESOLVIDO.** Medido em 2026-08-22 nas cinco rotas citadas
  pela auditoria (`despesas`, `office-contracts`, `partner-withdrawals`, `kanban-columns`,
  `regulatorio/digest-semanal`): todas respondem 200 em `/api/X` **e** em `/api/v1/X`, e 404 em
  `/api/v1/v1/X` — que é o comportamento correto. Histórico: a auditoria de julho viu
  `/api/v1/v1/despesas` → 200 e `/api/v1/despesas` → 404, com o frontend compensando ao chamar
  `/v1/x`. `src/lib/api.ts` linha 9 usa `baseURL: "/api/v1"` e o interceptor de request apara
  prefixo repetido (`/api/v1/`, `/api/`, `/v1/`); dentro do cliente `api` os caminhos se escrevem
  **sem** prefixo. Se a duplicação voltar a aparecer, comece pelo interceptor, não pelo `baseURL`.
- **Superfície dupla.** Toda rota responde em `/api/` e em `/api/v1/`. Regras por path
  (rate limit, WAF, log, cache) precisam cobrir as duas.
- **Painéis de diagnóstico divergem entre si.** Sobre provedores/modelos de IA, a fonte de verdade
  é a telemetria de `GET /ia-governanca/provedores` — não `/ai/status` nem `/diagnostico/central`.
  O `/diagnostico/central` chega a reportar `backup_offsite` como ligado e desligado na mesma resposta.
- **`GET /system-modules/mapa` é DIAGNÓSTICO, não inventário** — e se declara assim
  (`"modo": "diagnostico"`, `dry_run`, `requer_revisao_humana`). Ele percorre
  `autofix_scanner.EXPECTED_MODULES`, lista curada de módulos de PRODUTO com rota de frontend,
  não os routers de API. Comparar a cobertura dele com `app.routes` é comparar coisas
  diferentes — foi o erro de enquadramento da revarredura de 22/08. Continua valendo: pista,
  não verdade.
- **Gravação não transacional entre registros relacionados é uma classe de defeito recorrente.**
  A regra geral continua valendo — ao tocar em fluxo que grava em duas tabelas, verifique a
  transação. Dos quatro exemplos que a auditoria deu, três foram medidos em 22/08 e **nenhum é
  o que a nota dizia**:
  - *exclusão de caso que não cascateia para as peças* — **protegido**: `DELETE /cases/{id}`
    devolve 422 listando as pendências e manda arquivar.
  - *conversão Sala Jurídica → Caso que perde `descricao_fatos`* — **era real, corrigido**, mas
    não no backend: `legal_chat_service` sempre gravou o campo. O buraco estava no
    pré-preenchimento do wizard, cujos dois degraus (`estado.resumo || workspace_texto`) podiam
    faltar juntos, porque `resumo` vem de extração de IA fail-soft e IA nasce desligada. Terceiro
    degrau agora lê as mensagens do advogado.
  - *chance de êxito que fica no log e não no caso* — **mal enquadrado, não é defeito.** Não
    existe (nem deve existir) coluna `cases.chance_exito`: o valor é persistido no snapshot
    versionado (`case_intelligence_snapshots.payload.riscos.chance_exito`) e num `CaseMovimento`
    legível, e `GET /cases/{id}/movimentos` não filtra por tipo, então o `chance≈X%` chega ao
    advogado. Gravar estimativa de IA não revisada como atributo de primeira classe do caso seria
    **violar HITL**, não corrigir nada — o snapshot nasce de propósito com `criado_por=None`
    ("automático — nunca nasce aprovado").
  - *validação que não vincula ao documento* — **resolvido**, pela saída (b) que o próprio
    `plano-correcao-v2.md` §2.1 propunha: o campo denormalizado `validacao_juridica.ai_log_id`
    deixou de existir e `_ultima_validacao_peca` resolve por **FK** (`ai_logs.legal_doc_id`) mais
    `legal_doc_validation_current` e SHA-256 do conteúdo. Medido em 22/08 contra a stack local,
    cinco casos: peça nova bloqueia (422); AILog com FK + flag + hash correto libera
    (`validada`, `/aprovar` → **200**); e o fail-closed segura os três desvios — hash defasado
    (peça editada depois de validar), flag de atualidade desligada e validação de **outra** peça.
    Nenhum marcador textual correlaciona os dois registros. O critério de aceite da auditoria
    ("criar peça → validar → aprovar") passa sem intervenção no banco; a etapa `validar` em si
    exige provedor de IA e, sem ele, devolve **503 explicado** (não 500 mudo) — correção anterior,
    achado #672.

  Com isso os **cinco** exemplos da classe estão medidos, e a lição vale mais que eles: a classe
  é real e a regra geral continua valendo, mas **nenhum dos cinco casos citados era, hoje, o que
  a nota dizia**.
- **Monitoramento afere execução, não resultado.** A regra continua valendo para job novo, mas
  o caso citado **foi corrigido**: `heartbeat_service._normalizar_resultado_djen` "troca o
  status nominal pela produtividade real da task" e marca `falha_job` quando há OABs elegíveis
  sem métrica de execução. Atenção: o tratamento é específico do `JOB_DJEN` — os demais jobs
  ainda registram o status nominal, então **job novo ou corrigido deve monitorar resultado**.
- ~~**Vocabulário de status inconsistente.**~~ **RESOLVIDO**: `validar_status_caso` devolve
  **422** com a lista de valores aceitos (o próprio comentário em `routers/cases.py` registra
  "era o caso de `?status=all`"). "Todos" é a AUSÊNCIA do parâmetro.
- **`qa/e2e/run_fictitious_smoke.py`: o script JÁ SE PROTEGE** (linha ~1025 recusa alvo fora
  de staging/homolog/localhost sem `EJC_ALLOW_PRODUCTION_E2E=true`). O que permanece é o
  **rastro em produção**: os casos `HOMOLOG-FICTICIO-*` e a conta `homolog.qa` (superadmin,
  ativa) criados antes do guard — limpeza é operação de ambiente, não de código.
  Ponto fraco anotado: o guard testa substring na URL inteira, então
  `https://…adv.br/?x=staging` passaria; verificar o **hostname** seria mais firme.
- **Numeração de migrations envelhece rápido — inclusive dentro de um PR aberto.** A
  auditoria viu `122_route_usage_metrics`; em 2026-08-02 o head já era
  `126_case_status_quatro_estados`; em 2026-08-22 este PR reservava `147`/`148`; e ao mesclar
  a `main` em 2026-08-23 o `147` já estava ocupado por outro PR mesclado primeiro
  (`147_pendencia_impacto_providencia`), forçando renumeração para `149`/`150` antes do
  merge. Nenhum número escrito em documento é confiável, **inclusive este**: rode
  `cd backend && python -m alembic heads`.

### Critério de lançamento

Um advogado leva um caso real do início ao protocolo dentro do sistema e considera que foi
**mais fácil do que fazer fora dele**. Enquanto isso não acontecer, o trabalho não está pronto.
Nenhum caso, até a data da auditoria, passou da triagem; nenhuma peça foi protocolada.

## Diretrizes para operações Git/GitHub

- Antes de qualquer sequência de comandos `gh`, rode `gh auth status` uma única vez no início da tarefa; se retornar não autenticado, pare e reporte ao usuário — nunca tente `gh auth login` de forma autônoma, pois esse comando abre fluxo interativo de navegador e trava a sessão.
- Nunca execute `gh pr create`, `gh issue create` ou comandos `gh` equivalentes sem todas as flags necessárias (`--title`, `--body`, `--base`, `--head` conforme o caso); chamadas sem flags entram em modo interativo de terminal e travam aguardando entrada que não será fornecida.
- Para consultas em lote de múltiplos PRs ou issues, prefira uma única chamada via `gh api graphql` a N chamadas sequenciais de `gh pr view`/`gh issue view`, reduzindo requisições contra o rate limit da API do GitHub.
- Para clonagem apenas de inspeção pontual, sem necessidade de histórico completo, use `git clone --depth 1` em vez de clone completo.
- Se qualquer comando `git` ou `gh` não retornar em tempo razoável, não repita a mesma chamada indefinidamente: interrompa, verifique se há prompt interativo pendente (autenticação, GPG, hook) e reporte a causa provável ao usuário.
- Não use `git commit --no-verify`, `git push --force` ou `git reset --hard` sem confirmação explícita do usuário para aquele comando específico.

A recomendação de `gh api graphql` acima vale **só para leitura**: a allowlist libera
`gh api graphql -f query=*` e nega `gh api` com método de escrita (`-X`, `--method`, `-F`,
`--input`). As travas de governança continuam valendo sobre todo comando desta seção —
merge acontece pela esteira automatizada com gates verdes (regra 8), não se empurra nada para
a `main` diretamente (regra 1) e deploy só pela esteira (regra 9).
