# 01 — Arquitetura atual e inventário técnico (Fases 1 e 3)

## 1. Fase 1 — Proteção e reconhecimento do ambiente

```
Repositório:        /home/user/ejc  (git, remoto s2corporativo/ejc)
Branch:             claude/auditoria-ejc-graphify-aoa2hi
Commit atual:       aa65974c089dcdce91882f6b7ec3f398823989fe
                    "Merge pull request #643 … claude/code-analysis-improvements-y6f4ef"
                    2026-08-02 18:40:37 -0300
Worktree:           uma só (/home/user/ejc) — nenhuma paralela
Alterações pendentes: NENHUMA (git status limpo no início)
Containers:         NENHUM — daemon Docker indisponível (/var/run/docker.sock ausente)
Serviços:           NENHUM em execução
Banco:              INDISPONÍVEL — sem PostgreSQL, sem pgvector, sem Redis
Frontend:           código presente; node_modules ausente no início (instalado para rodar testes)
Backend:            código presente; deps Python ausentes (instaladas em venv isolado no scratchpad)
Ambiente:           checkout estático e efêmero, isolado da produção
```

**Ambiente é de análise estática.** Não há produção acessível a partir daqui — o que satisfaz a
regra 9 do `CLAUDE.md` por construção, mas **limita** o que pode ser afirmado. Os limites estão
declarados em cada documento; os principais:

- os **161 testes DB-level** não puderam rodar (ver `14-testes.md`);
- não foi possível confirmar o estado real do banco de produção — em especial a existência da conta
  `homolog.qa` (ver `07-banco-de-dados.md` §6.2);
- não foi possível validar planos de query, presença física de índices, nem o tag `gemma3:9b` no
  registry Ollama.

**Riscos para a auditoria — mitigados:** nenhuma alteração de outra sessão foi descartada
(worktree limpa); nada foi instalado no ambiente do repositório (venv e `node_modules` são
descartáveis e ignorados pelo git); `graphify-out/` já era ignorado.

## 2. Escala medida

| Camada | Quantidade |
|---|---|
| Arquivos Python no backend | 1 049 |
| **Módulos de router** | **162** (163 arquivos, incluindo `__init__.py`) |
| **Endpoints registrados** | **820** (166 objetos `APIRouter`; **830 rotas** no app montado, incl. app-level) |
| Services | 141 módulos, **56 988 linhas** |
| Models SQLAlchemy | 62 |
| Migrations Alembic | 121 (head: `126_case_status_quatro_estados`) |
| Tabelas no banco | 103 (**30 só em SQL bruto**, sem model ORM) |
| Arquivos de teste do backend | 342 (**4 629 testes**) |
| Arquivos `.ts`/`.tsx` no frontend | 269 |
| Páginas | 89 arquivos (54 roteados + 35 subcomponentes de aba) |
| Rotas de staff no registry | 42 (+ 35 redirects legados) |
| Testes do frontend | 54 arquivos, **343 testes** |
| Agentes Claude Code | 12 · Skills de projeto: 19 · **Skills globais: 163** |
| Agentes jurídicos internos | 37 · Skills do produto: 76 (código) + ~170 (banco) |

## 3. Árvore do sistema

```
EJC
├── Frontend         React 19 · Vite 8 · TS 5 · Tailwind 3 · Zustand 4 · axios
│                    moduleRegistry (fonte da verdade de rotas + RBAC de navegação)
│                    lib/api.ts (137 dependentes — todo tráfego HTTP)
├── Backend          FastAPI · SQLAlchemy 2 async (asyncpg) · Pydantic v2
│                    main.py registra 166 APIRouter sob /api
│                    middlewares: CORS → GZip → ClientIP → APIVersion → Auth → router
├── Banco            PostgreSQL 16 + pgvector · Alembic (121) · 103 tabelas
│                    knowledge_chunks.embedding vector(1024) + HNSW + GIN(FTS pt) + GIN(trgm)
├── IA               ai_gateway.py — ÚNICA saída de IA (invariante confirmada)
│                    providers/: ollama → anthropic → maritaca → groq
│                    sanitizer.py (PII) · pii_crypto.py (Fernet + HMAC cego)
│                    citation_gate.py · hitl_policy.py (rascunho incondicional)
├── RAG              ingestão → chunking (1200/150) → e5-large 1024d (fastembed ONNX)
│                    busca híbrida: pgvector + pg_trgm + FTS pt, fusão RRF k=60
│                    isolamento por client_id, fail-closed
├── Agentes          produto: 37 agentes jurídicos (metadado) + orchestrator + intent_classifier
│                    dev: 12 agentes Claude Code
├── Skills           produto: SKILL_REGISTRY (76) · EjcSkill em banco (~170) · SkillRouter (5)
│                            · tools do agente  ← QUATRO superfícies paralelas
│                    dev: 19 de projeto + 163 globais (17 duplicadas)
├── Integrações      DataJud · Infosimples · NFSe · WhatsApp/Evolution · DJEN/Diário Oficial
│                    Google Drive · Langfuse — todas opt-in por flag, default OFF
├── Workers          Celery + Redis · APScheduler (scheduler.py, 1 894 linhas)
│                    premissa: uvicorn --workers 1
├── Testes           backend 342 arq./4 629 testes · frontend 54/343 · qa/e2e (fora do CI)
├── Infraestrutura   Docker Compose · Nginx do host (TLS, /api→8000, /→8080) · VPS Contabo
│                    CI: ci.yml (3 jobs) + 6 workflows em pull_request
└── Documentação     docs/ · docs/ai/ · docs/auditoria/ (externa) · docs/auditoria-ejc/ (esta)
                     RUNBOOK_*.md · RELATORIO_*.md · graphify-out/ (não versionado)
```

## 4. Divergências entre documentação, código e realidade

Esta é a entrega mais acionável da fase de inventário. Todas confirmadas em arquivo.

| # | O que a documentação diz | O que o código diz | Onde |
|---|---|---|---|
| 1 | *"163 routers"* | **162 módulos** — o 163º é o `__init__.py` | `CLAUDE.md` vs `ls app/routers/` |
| 2 | *"o frontend compensa chamando `/v1/x`"* e *"Resolvido em 2026-08-02"* | **A compensação virou a causa.** O interceptor apara `/v1/` e produz 404 em 27 chamadas | `CLAUDE.md` vs `lib/api.ts:23` — **P0** |
| 3 | *"ruff/pip-audit informativos"* | **Ambos bloqueantes** — não há `continue-on-error`; o passo se chama "Auditoria **bloqueante**" | `CLAUDE.md` vs `ci.yml:103,114` |
| 4 | CI descrito com **2 jobs** | **3 jobs** — falta `eval-smoke` | `CLAUDE.md` vs `ci.yml:157` |
| 5 | *"a conta `homolog.qa` vem de `qa/e2e/run_fictitious_smoke.py`"* | **Nenhum runner cria usuário**; e o marcador `HOMOLOG-FICTICIO` vem de **outro** arquivo | `CLAUDE.md:265` vs `qa/*` — **P1 operacional** |
| 6 | *"o grafo versionado"* | `graphify-out/` está **no `.gitignore`** e não é versionado | `CLAUDE.md` vs `.gitignore:61` |
| 7 | *"`env.py` tem guarda com ~30 tabelas"* | `env.py` **deriva dinamicamente**; a lista literal de 30 está em `tests/test_schema_sync.py:100-121` | `CLAUDE.md` vs `alembic/env.py:73-74` |
| 8 | *"Vocabulário de status inconsistente"* (armadilha) | **RESOLVIDO** pela migration 126 + `core/status_caso.py` como fonte única | `docs/auditoria/` vs código atual |
| 9 | *"`GET /system-modules/mapa` subdetecta rotas"* | mantido como pista — não reauditado nesta fase | `CLAUDE.md` |
| 10 | Agentes citam `python-jose`/`passlib` e React 18 | Ambos **removidos deliberadamente**; o projeto está em **React 19** | `.claude/agents/*.md` |
| 11 | `MIGRATION_RESERVATIONS.md:5` — *"head … `123_…`"* | head real é **`126_…`** (a própria tabela do arquivo já diz) | `backend/alembic/` |
| 12 | `requirements.txt:63-76` culpa `aiohttp`/`pywebpush` pela falha de instalação | O quebra-cabeça real é **`http-ece` com setuptools Debian-patched** | `14-testes.md` §1 |

## 5. Padrões de design confirmados

**Respeitados:**
- **Toda IA passa pelo `ai_gateway`** — zero bypass, verificado por busca de SDK e de URL de API.
- **Integrações externas opt-in por flag, default OFF, com degradação graciosa** — mantido em
  DataJud, Infosimples, NFSe, WhatsApp, DJEN, Drive, Langfuse.
- **HITL universal** — `is_rascunho=True` incondicional, não desligável por flag.
- **Boot fail-closed em produção** — falha sem `SECRET_KEY`, chaves de PII ou com CORS wildcard.
- **PII cifrada em repouso** com Fernet + índice cego HMAC, e barreira antes de provedor externo.

**Aspiracionais (não realizados):**
- **"Routers finos → services"** — **95 endpoints (11,6 %) executam SQL cru** e há **555
  `select()`** direto em routers, em 38 arquivos. Em ~1/3 dos routers a camada de service não existe.
- **"Registro explícito de rotas"** — 5 routers ainda são registrados por **efeito colateral de
  import** (`routers/__init__.py:24-30`), embora `main.py:427-443` documente a migração de cinco
  *outros* grupos para longe desse padrão.

## 6. Premissas operacionais que limitam escala

Registradas no `CLAUDE.md` e confirmadas no código:

| Premissa | Consequência se violada |
|---|---|
| `uvicorn --workers 1` | rate limit em memória e APScheduler duplicam |
| — | **e também o anti-brute-force de `security_service.py:33`, que não tem backend Redis**: com N workers, o teto de 5 falhas vira 5×N |
| `RATE_LIMIT_REDIS_ENABLED=true` nos workers extras | necessário para escalar |
| `ENABLE_SCHEDULER=false` nos workers extras | evita jobs duplicados |

`services/scheduler.py` tem **1 894 linhas** e é o maior módulo do sistema — ponto único de falha
operacional.
