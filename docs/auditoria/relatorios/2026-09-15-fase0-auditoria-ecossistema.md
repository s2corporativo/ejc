# FASE 0 — Auditoria do Ecossistema EJC (base de execução do Plano Mestre)

Data: 2026-09-15 · Base auditada: `main` `9da62f0e0` (pós-#1659) · Método: inspeção direta do código (front + back + migrations) sem alterações

---

## 1. Sumário executivo

O EJC encontra-se em maturidade incomum para o porte: backend FastAPI com ~169 mil linhas, ~879 endpoints em 162 routers, 132 tabelas, 151 migrations com head único, RBAC em duas camadas, auditoria WORM, núcleo único de IA com HITL e barreira dupla de PII, RAG pgvector com governança. O frontend React 19/Vite/Tailwind tem app shell de referência 2026, registry central de módulos e kit UI próprio. Os riscos dominantes **não são de falta de controle, mas de escala e duplicação residual**: 12 camadas CSS sobrepostas, 3 fontes de verdade na navegação, famílias de teses/jurisprudência/entrada/google-drive duplicadas, e ausência de camada de services no frontend. Este relatório consolida a auditoria que serve de mapa para as fases 1-9 do Plano Mestre (finalização, consolidação e evolução profissional).

## 2. Frontend (React 19 + Vite + Tailwind 3 + Zustand 4)

### 2.1 Dashboard canônico e pilha de gerações

A rota `/` (canônica, `essential: true`) aponta para `frontend/src/pages/Dashboard.tsx`, que é um wrapper (`<DeadlineRiskStrip />` + banner PJe + `<DashboardUltra />`). A implementação real é `DashboardUltra.tsx` (406 linhas; consome `GET /atividades/alertas-inteligentes`, embute `DashboardAiChat.tsx` e `JurisprudentialAlertsStrip.tsx`). Comentários no próprio arquivo admitem "implementações anteriores preservadas para rollback". Redirects legados confirmam o acúmulo: `/dashboard → /`, `/dashboard-executivo → /`, `/financeiro-dashboard → /financeiro`. Há dois `Kpi` paralelos (`components/Dashboards.tsx` e um local redefinido em `DashboardIA.tsx:24`). Outros painéis: `FinanceiroDashboard.tsx` (573 linhas, só embutido), `DashboardIA.tsx` (saúde da IA), `portal/PortalDashboard.tsx`, `dpt360/Dpt360Workspace.tsx`, `Produtividade.tsx`, `CentralDiagnostico.tsx`.

### 2.2 Navegação com três fontes de verdade

1. `frontend/src/config/moduleRegistry.tsx` — `STAFF_ROUTES` (~50 módulos com flags `showInNav`, `essential`, `roles`, `order`, grupos);
2. `frontend/src/components/LayoutReference.tsx:46-56` — `PRIMARY_NAV_KEYS` hardcoded (ignora a flag `essential`, que só é usada por `CommandPalette.tsx:131`);
3. `NAV_LABELS` sobrescrevendo rótulos do registry (`IA Jurídica` vs `Pesquisa e IA`; `Prazos e Agenda` vs `Agenda e Prazos`).

Os grupos `MODULE_GROUP_ORDER` ("Trabalhar um caso", "Pesquisar & IA", "Gerir o escritório", "Administrar") são computados **mas nunca renderizados** como cabeçalhos. `PermissionOnly` (`RouteGuards.tsx:64`) está exportado e morto — o RBAC de frontend se apoia só em papéis (`RoleOnly`) espelhando manualmente as matrizes do backend.

### 2.3 Design system e camadas CSS

Kit único em `frontend/src/components/UI.tsx` (~1.400 linhas, 40+ componentes) com todos os componentes canônicos exigidos pelo Plano Mestre já existentes: `Button`, `Card`, `SectionCard`, `Badge`, `StatusBadge`, `RiskBadge`, `PriorityBadge`, `Input/Select/Textarea/SearchBar`, `PageHeader`, `StatCard`, `Table*`, `Tooltip`, `Modal`, `ConfirmModal`, `Drawer`, `Alert`, `EmptyState`, `ErrorState`, `Spinner`, `SkeletonTable`, e o bloco de IA (`IANotice`, `AISurface`, `ConfidenceBadge`, `HumanValidationStatus`, `SourceCitation`, `AIFactualityLegend`, `VisualLawDocument`). **Não há shadcn/ui** — por decisão do shell 2026, o kit é próprio.

Tokens: `tailwind.config.js` define paleta institucional ouro (`primary.600 #8F7117`), `ai` violeta, `legal` azul-marinho, com paletas legadas `navy`/`bronze`/`gold` mantidas e pares duplicados `warn≡warning`, `danger≡error`. `index.css` (1.575 linhas) define `--ejc-*`; `styles/legal-tech-premium.css` (871 linhas) define um **segundo sistema** `--lt-*` com ação azul (`#2563eb`) que conflita com a ação ouro. `main.tsx` importa 11 folhas empilhadas (`fonts.css` → … → `ejc-reference-systemwide.css`), com comentários admitindo camadas legadas "preservadas para rollback visual isolado" (`bronze-elegance.css`, `premium-shell.css`, `premium-dashboard.css`). `UI.tsx:66-72` documenta cascata vencendo utilities via `::before` para escapar `!important` global — sintoma do débito.

### 2.4 Serviços e estado

`frontend/src/lib/api.ts` concentra cliente HTTP (`baseURL /api/v1`, refresh em cookie httpOnly `ejc_refresh`, access em `localStorage.ejc_access`), interceptores com efeitos colaterais globais (redirects de senha/2FA, toast de 403 acoplado a `Toast.tsx`) e funções de domínio avulsas (orquestrador, extração, raio-x). **Não há camada `services/` por domínio**; páginas chamam `api.get("/clientes"…)` com paths string repetidos em dezenas de arquivos (ex.: `/ai/skills/execute` em `RaioXProcesso.tsx:771`, `FerramentasIA.tsx:300`, `ContextualAIAssistant.tsx:199`). Stores Zustand: `auth`, `theme`, `preferences` (homeRoute pós-login), `caseContext` (modo caso), `moduleLifecycle` (overrides do backend), `cadastroManual` (fila offline LGPD-consciente).

### 2.5 Superfícies de IA já integradas (não criar backend novo)

`DashboardAiChat` (home), `ContextualAIAssistant` (global, `POST /ai/skills/execute` + HITL `PATCH /ai/logs/{id}/hitl`), `SalaJuridica` (estado probatório), `AgenteIA` (SSE `/ia/agente/stream`), `AssistenteIA` (`/ia/conversar|resumir|redigir|analisar`), `IA.tsx`/`FerramentasIA.tsx`, agregador `InteligenciaWorkspace` (abas assistente/produção/honorários/jurimetria/conhecimento/saúde), governança `GovernancaIA` + `PainelProvedoresIA`. UX de IA transversal: `useIaStatus`, `IaStatusBanner`, `AISurface` etc.

### 2.6 Principais problemas (ordenados por custo/benefício de correção)

| # | Problema | Evidência |
|---|---|---|
| 1 | Sem camada de services; endpoints como strings espalhadas | `lib/api.ts` + dezenas de páginas |
| 2 | Navegação com 3 fontes de verdade; grupos não renderizados | registry vs `LayoutReference` |
| 3 | Pilha de dashboards com rollback vivo e KPI duplicado | `Dashboard.tsx`→`Ultra`; `Kpi` em `DashboardIA` |
| 4 | Workspaces importam páginas inteiras (code-splitting anulado) | `InteligenciaWorkspace` importa 7 páginas |
| 5 | 12 camadas CSS sobrepostas + 2 sistemas de tokens conflitantes | `main.tsx`, `index.css`, `legal-tech-premium.css` |
| 6 | Rotas canônicas duplicadas (registry vs `canonicalRoutes.ts`) | paridade por teste, não por construção |
| 7 | Navegação fora do registry (portal inline; DPT360 triplo no registry) | `PortalLayout.tsx`, `moduleRegistry` |
| 8 | Tipagem fraca em superfícies centrais (`useState<any[]>`) | `LayoutReference.tsx:111` |
| 9 | `PermissionOnly` morto; sem permissão granular no router | `RouteGuards.tsx` |
| 10 | Gigantes monolíticos (`Casos.tsx` 1.797 l., `Pecas.tsx` 1.559 l.) | `pages/` |

## 3. Backend (FastAPI, ~879 endpoints)

### 3.1 Superfície

162 arquivos de routers (167 instâncias de APIRouter), 163 `include_router` em `main.py` (687 linhas), ≈879 endpoints (GET 420, POST 339, PATCH 59, DELETE 57, PUT 2). Domínios completos: auth/users, clientes (dossiê, sociedade, portal), casos (orquestrador, kanban, workflow, checklists), documentos (GED, Data Room, assinaturas, provas), peças (`legal-docs` HITL, `pecas`, `motor-peca`), prazos/agenda (deadlines, agenda-eventos, intimações, DJEN), financeiro (fees, consolidado, despesas, NFSe, PIX, timesheet), IA/RAG (17 routers), DataJud/integrações (PDPJ, PJe-MNI, eproc, Infosimples, NFS-e, Drive, dados públicos), admin/governança (audit, backup, cofre, LGPD, diagnóstico) e verticais (8 ramos + matrizes + jurimetria).

### 3.2 Autenticação e RBAC (duas camadas)

`core/auth_middleware.py` (middleware global registrado em `main.py:385`) valida JWT em toda rota não-pública; `PREFIXOS_PUBLICOS` isenta textualmente `/api/auth/*`, `/api/health`, `/api/webhooks/`, `/api/data-rooms/acesso/`, `/api/rag/knowledge-base/` e feed ICS HMAC. Aplica gates extras (`pwd_change_required`, 2FA obrigatório, isolamento do portal para `cliente_externo` com allowlist de prefixos). `core/security.py`: `get_current_user` (linha 207) revalida usuário no banco por request; `require_roles` (248) com fallback hierárquico por `ROLE_LEVEL`; `require_roles_exact` (266); `require_admin` (292); `EQUIPE_JURIDICA` (57) com helpers para uso no corpo do handler (padrão do fechamento do vazamento do papel `financeiro`, Issue #694). Ownership: `core/ownership.py` (`is_gestao`), `core/client_ownership.py`, `dpt360/access_scope.py`. Enforcement: 570 `get_current_user`, 165 `require_roles`, 116 `require_roles_exact`, 10 `require_admin`. JWT HS256, access 2h, refresh 7d revogável por JTI.

### 3.3 Auditoria

Tabela WORM `audit_logs` (`models/audit_log.py`, mig 131, "IMUTÁVEL — nunca editar/deletar (LGPD art. 37)"), helper `criar_audit_log()` grava na mesma transação, IP via `ClientIPMiddleware`, 105 referências em ~30 módulos. IA audita em `ai_logs` via `services/ai_guard.py::registrar_ai_log` com **propagação de falha** ("IA sem trilha de auditoria deve falhar"). Consulta read-only `GET /api/audit` para sócio+. Purga LGPD semanal no scheduler.

### 3.4 IA/RAG — Núcleo Único

`services/ai/core/orchestrator.py` ("TODA tarefa de IA passa por aqui": intenção → agente → RBAC/ABAC → dossiê/RAG → sanitização LGPD → provider policy → gateway → validação → HITL → AILog). Gateway `services/ai_gateway.py` (~1.500 linhas) com cadeia de providers e fallback (Ollama local default OFF, Anthropic, Groq, Maritaca), níveis de inteligência (padrão/FIRAC/adversarial), custo BRL, pseudonimização reversível consistente (`[CLIENTE_1]`) com reidratação local e mapa nunca persistido. Skills: catálogo `ejc_skill_catalog.py` + tabela `ejc_skills` + seeds. **Legal Brain** (`services/legal_brain/`, 1.804 linhas): `brain.py` (plano determinístico), `skill_factory.py` (fail-closed, semver — recém-mergeado #1659), `research_loop.py` (critérios objetivos de parada), `evidence.py` (estados epistemológicos), `precedent_validity.py`, `shadow.py` (opt-in). Prompts: ~45 módulos em `services/system_prompts/`. RAG: pgvector (`knowledge_docs/chunks/fontes`), embeddings locais fastembed `multilingual-e5-large`, ingestores oficiais (planalto, STJ, TJMG, DJEN…), governança de vigência, eval (`app/eval/`, `legal_bench.py`).

### 3.5 Migrations e modelos

151 arquivos, 151 revision IDs únicos, **head único `160_activity_alert_states`**, 1 merge revision (104 — reconciliação de fork dos PRs #284/#285). Readiness bloqueia se `alembic_version` ≠ head (`core/observability.py::check_migrations_head`). 72 arquivos de models, 132 tabelas, zero `__tablename__` duplicado. Compat arquivado: `models/dataroom_teses_v4_compat.py` mantido só para Alembic.

### 3.6 Duplicações residuais (consolidação FASE 7)

| Família | Arquivos vivos duplicados |
|---|---|
| Teses | `models/tese.py` × `models/matriz_teses.py` × `dataroom_teses_v4_compat.py`; routers `teses.py` × `matriz_teses.py` |
| Data room | `models/data_room.py` × `dataroom_salas` (metadata órfã) |
| Jurisprudência | 4 superfícies: `jurisprudencia_externa.py`, `jurisprudencia_interna.py`, `precedentes_jurisprudencia.py`, `juris_import.py` |
| Entrada/intake | 6 portas: `entrada`, `entrada_universal`, `intake`, `triagem_entrevista`, `ficha_triagem`, `document_intake*` |
| Google Drive | `services/google_drive.py` × `services/google_drive_service.py` |
| Analytics | `dashboard.py` × `analytics.py` × `produtividade.py` × `relatorio*.py` (agregadores diferentes para os mesmos dados) |
| IA | 17 routers apesar do núcleo único; `core/ai_brain.py` shim (~16 consumidores); `core/skill_router.py` só usado por `cerebro.py` |

### 3.7 Riscos técnicos principais

1. Monólito de registro de rotas (`main.py` com 163 includes manuais, ordem sensível).
2. ~879 endpoints sem versionamento real (`APIVersionCompatibilityMiddleware` só reescreve `/api/v1`→`/api`).
3. `require_roles` com fallback hierárquico (padrão do bug do papel financeiro) ainda em 165 usos; 570 endpoints só com `get_current_user`.
4. Papel do JWT confiada por até 2h no middleware (isolamento do portal usa role do token).
5. Isenção pública textual por prefixo (bypass silencioso se composição errada).
6. Scheduler de 42+ jobs APScheduler no processo da API (ponto único operacional).
7. Embeddings in-process já causaram OOM global (incidente 2026-08-27 documentado; contenção por `EMBED_BATCH`; reembed horário com `RAG_AUTO_REEMBED_ENABLED=True`).
8. Duplicações residuais (§3.6) com risco de divergência de dados.
9. `OLLAMA_ENABLED=False` por padrão → fluxo padrão usa providers externos; garantia LGPD depende da barreira dupla de pseudonimização; política overridável por config (piso preservado para sigilo reforçado).
10. **Rate limit ausente em `routers/cerebro.py` e `routers/ai_skills.py`** (irmãos canônicos usam `rate_limit(nome, max)`; slowapi sem default_limits) — quick-win de segurança já identificado.

## 4. FASE 1 — Proteção da main (verificada e completada nesta data)

Ruleset `Proteção da main - EJC` (id 19288626), enforcement **active**, bypass nenhum:

| Regra | Estado |
|---|---|
| PR obrigatório com resolução de todos os review threads | ✓ (`required_review_thread_resolution: true`) |
| Dismiss de reviews obsoletas a cada push | ✓ |
| Aprovação extra para mudanças não-atribuídas | ✓ |
| CI obrigatório com strict head check | ✓ (`ci/woodpecker/pr/woodpecker`, `strict_required_status_checks_policy: true`) |
| Deleção da branch bloqueada | ✓ |
| **Force push (non_fast_forward)** | ✓ **adicionado em 2026-09-15 via API** |
| Aprovação numérica (required_approving_review_count) | 0 — decisão deliberada: o Titular mergeia pessoalmente (§6-A); elevar a 1 quando houver segundo revisor humano |

Observação: `allowed_merge_methods: [merge, squash, rebase]` — merge commit preserva rastreabilidade dos PRs no histórico.

## 5. FASE 2 — Estoque de PRs (estado real em 2026-09-15)

Lista do Plano Mestre vs realidade: **todos os 10 PRs citados já estão integrados ou supersedados** — #1633 merged; #1635/#1638/#1644/#1647 fechados (integrados pela release #1657); #1650/#1652/#1654/#1655 fechados como superseded da família legal-brain; #1659 **merged em 2026-09-15** (Skill Factory, CI 1471 verde). Estoque restante (6 abertos, todos draft exceto #1641):

| PR | Título | Avaliação |
|---|---|---|
| #1626 | test(legal-docs): provar gates HITL do endpoint revisar | test-only, baixo risco, integrar cedo |
| #1639 | fix(ui): responsividade da central e alinhamento de clientes | fix pequeno de UI, integrar |
| #1307 | fix(rag): fail-closed normativo com kill-switch | valor direto de robustez RAG, integrar após retarget |
| #1449 | refactor(clientes): Ficha Mestra reconstruída | já reconstruído localmente (tsc+19 testes verdes), retarget e integrar |
| #1606 | refactor(documents): upload GED → streaming | refactor maior, retarget pós-release e validar |
| #1641 | fix(qualidade): correções da homologação total (#1640) | exige reconstrução (N+1 financeiro, MNI savepoint, timeouts, CPF) |

Ordem proposta de integração: #1626 → #1639 → #1307 → #1449 → #1606 → reconstrução #1641, sempre com retarget na main corrente, CI verde e rollback possível (merge commit).

## 6. Plano de execução derivado (mapa para as próximas fases)

- **FASE 3 (fluxo jurídico)**: a suíte backend no CI (7.824 testes, 65 skipped, `RUN_DB_TESTS=1` contra pgvector efêmero) cobre o homologável sem ambiente local; homologação viva ponta-a-ponto permanece na VPS (runbook de deploy FASE 9).
- **FASE 4/7 (design canônico + saneamento)**: unificar navegação derivando `PRIMARY_NAV_KEYS` da flag `essential` e renderizando grupos do registry; consolidar pilha de dashboards (remover gerações mortas); podar camadas CSS legadas após inventário de classes; unificar tokens `--lt-*`→`--ejc-*`; converter abas de workspaces em sub-rotas lazy; extrair `services/` por domínio no frontend (começando por `ai/`, `cases/`, `clients/`).
- **FASE 5 (Legal Brain)**: base já operacional (§3.4); evolução incremental por área com skills versionadas via `skill_factory.py`.
- **FASE 6 (jurimetria)**: router `jurimetria.py` (21 endpoints) já existe; fase 2 = indicadores de êxito/tempo/teses sobre DataJud.
- **FASE 8 (segurança/LGPD)**: quick-wins imediatos — rate limit em `cerebro.py`/`ai_skills.py`; revisão dos 570 endpoints só-com-`get_current_user` por criticidade; documento de política de isenções públicas.
- **FASE 9 (deploy)**: runbook `git status → pull → docker compose config → backup → build → up -d → logs → /api/health + /api/health/ready` já padronizado no repo (`scripts/deploy_manual.sh`, gate host-level); restore drill do backup cifrado (#1572) segue pendente como critério de encerramento.
