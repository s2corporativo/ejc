# RELATÓRIO — Análise Multi-Agente do Mapeamento Graphify do Sistema EJC

Data: 2026-07-02
Método: grafo regenerado com `graphify update . --force` (graphifyy 0.9.5) e analisado por 4 agentes em paralelo — (1) arquitetura geral e god nodes, (2) backend, (3) frontend, (4) relações cross-file e integridade do grafo.

## 1. Números do grafo

| Métrica | Valor |
|---|---|
| Arquivos analisados | 572 (~95% dos 611 versionados) |
| Nós | 4.436 |
| Arestas | 8.587 (48% cross-file) |
| Comunidades | 358 |
| Extração | 79% EXTRACTED · 21% INFERRED (confiança média 0,67) · 0% AMBIGUOUS |
| Diagnóstico multigraph | 0 endpoints ausentes, 0 duplicatas, 0 self-loops, 0 colapsos |
| Ciclos de import | **Nenhum detectado** |
| Componentes conexos | 171 (principal com 3.433 nós = 77%) |

## 2. Visão geral da arquitetura

- **Backend**: FastAPI 0.111 + SQLAlchemy 2.0 async + PostgreSQL 16 + pgvector. **115 routers**, **81 services**, **42 models**. Núcleo transversal em `backend/app/core/` (database, security, auth_middleware, ownership, rate_limit). Scheduler APScheduler in-process (~17 cron jobs) e event bus outbox (`services/event_bus.py`).
- **Frontend**: React 18.3 + TypeScript 5.4 + Vite 5 + Zustand. **63 páginas** roteadas em `frontend/src/App.tsx` (lazy-loading), cliente HTTP único em `frontend/src/lib/api.ts` (interceptors de Bearer token e refresh automático com deduplicação), kit de UI interno em `components/UI.tsx`.
- **Infra**: `docker-compose.yml` (db/backend/frontend), nginx servindo o SPA com proxy `/api/`, deploy VPS via `scripts/` e `vps-tools/`, migrações Alembic com guarda no autogenerate.

## 3. God nodes (top 10)

| # | Nó | Grau | Arquivo | Função |
|---|-----|------|---------|--------|
| 1 | `User` | 155 | `backend/app/models/user.py` | Modelo de usuário + RBAC (`UserRole`); injetado como `current_user` em quase todos os routers |
| 2 | `Base` | 121 | `backend/app/core/database.py` | DeclarativeBase; maior betweenness do grafo (0,037) |
| 3 | `Case` | 97 | `backend/app/models/case.py` | Entidade central do domínio jurídico |
| 4 | `criar_audit_log()` | 86 | `backend/app/models/audit_log.py` | Trilha de auditoria chamada em ~29 módulos |
| 5 | `api` | 77 | `frontend/src/lib/api.ts` | Cliente HTTP único do frontend |
| 6 | `verificar_acesso_caso()` | 73 | `backend/app/core/ownership.py` | Gate canônico anti-IDOR (Fase 3A) |
| 7 | `AILog` | 59 | `backend/app/models/ai_log.py` | Governança/HITL de toda chamada de IA |
| 8 | `PageHeader()` | 40 | `frontend/src/components/UI.tsx` | Cabeçalho padrão de todas as páginas |
| 9 | `Client` | 38 | `backend/app/models/client.py` | Base do escopo LGPD/RAG |
| 10 | `sanitizar_pii()` | 34 | `backend/app/services/sanitizer.py` | Sanitização LGPD antes de qualquer envio à IA |

Padrão: o backend forma um "quadrilátero de compliance" (User → ownership → audit → PII); o frontend tem dois pontos únicos de integração (`api.ts` e `UI.tsx`).

Ressalva de confiança: os god nodes concentram arestas INFERRED — `User` (153/155), `Base` (119/121), `Case` (96/97). As ligações rota→modelo dependem majoritariamente de inferência, não de AST.

## 4. Backend — domínios e fluxos

1. **Gestão jurídica core**: `cases.py` (870 linhas), `clients.py`, `deadlines.py` + `deadline_calculator.py`, `processes.py`, `movimentos.py`, `intimacoes.py`, `kanban.py`, `checklists.py`.
2. **Financeiro**: `fees.py`, `despesas.py`, `extratos.py`, `financeiro_consolidado.py`, `partner_withdrawals.py`, `exito_rateio.py`, `pix.py` (BR Code EMV local), `rentabilidade.py`.
3. **IA/RAG (maior subsistema)**: gateway canônico `services/ai_gateway.py` (roteamento por tarefa, fallback Ollama→Groq→Anthropic, custo em BRL, AILog obrigatório); RAG fail-closed por cliente (`ai_service.py`, validado por `tests/test_rag_isolation.py`); pipeline de peças em 7 etapas com SSE (`peca_service.py`: sanitização PII → RAG → verificação de citações → padronização → AILog); governança HITL (`ia_governanca.py`); ingestão automática Planalto/STJ/Câmara/Senado.
4. **Societário**: `gestao_societaria.py`, `contratos_societarios.py`, `office_contracts.py`.
5. **Compliance/LGPD**: portabilidade e direito ao esquecimento em `clients.py`, `pii_crypto.py`, `client_anonimizacao.py`, purgas agendadas.
6. **Portal do cliente**: `routers/portal.py` + role `cliente_externo`.

**Autenticação**: middleware global (`core/auth_middleware.py`) valida JWT em todo `/api/*` com allowlist enxuta; refresh token persistido/revogável; RBAC de 6 roles em dupla camada (middleware + `Depends` por rota); ownership por caso via `verificar_acesso_caso()`; brute-force protection, detecção de novo dispositivo e 2FA TOTP em `auth.py`; tudo auditado.

**Integrações**: DataJud CNJ, DJEN, Diário Oficial, jurisprudência externa; WhatsApp (Z-API + Evolution); SMTP; web push VAPID; Google Drive; backup S3.

## 5. Frontend — estrutura e hubs

- ~60 rotas em `App.tsx` com guardas `Protected`/`StaffOnly`/`RoleOnly`; portal do cliente sob `/portal`; ramos do direito dirigidos por dados (`pages/ramos/ramosConfig.ts` + `RamoBase.tsx`).
- Hubs por in-degree: `api.ts` (77), `UI.tsx` (44), `Toast.tsx` (26), `Markdown.tsx` (12), `stores/auth.ts` (10).
- **Sem camada de dados**: ~258 chamadas axios inline em `useEffect`/handlers, sem cache/retry padronizado; um único hook customizado (`useTheme.ts`).

## 6. Integridade e lacunas do mapeamento

- **Excelente**: integridade estrutural (diagnose limpo), cobertura de arquivos (~95%), mapeamento intra-backend (routers→services→models), comunidades coerentes.
- **Fraca — fronteira frontend↔backend**: **zero arestas reais**. A única aresta existente é um falso positivo (`main.tsx --imports_from--> backend/app/schemas/client.py`, resolução errada de `react-dom/client`). O grafo **não modela a camada HTTP** (`api.get('/x')` → decorator FastAPI); não confiar em `graphify path` para relações frontend→backend.
- **Ausente**: infra (docker-compose.yml sem nó; `scripts/` e `vps-tools/` isolados), migrations↔modelos (61 migrations desconectadas), service worker/PWA.
- **Poluição**: ~20 comunidades formadas por relatórios .md da raiz dominam queries semânticas genéricas.

## 7. Cruzamento endpoints × consumo (análise complementar dos agentes)

- Backend expõe **545 endpoints**; frontend faz **212 chamadas distintas**.
- **~306 endpoints (56%) sem correspondente direto no frontend**; **43 routers com zero consumo detectado** — destaque: `ramos.py` (63 endpoints), `novos_modulos.py` (14), `atendimentos.py` (9), `calculadoras.py` (8). (`webhooks.py`, `evolution_webhook.py`, `calendar_feed.py` são legitimamente externos.)
- **Chamadas do frontend sem rota no backend (404 candidatos)**: `/api/v1/bank-analysis/upload` e `/{id}/documento|excel`, `/api/v1/financeiro/consolidado`, `/api/v1/relatorio/mensal`, `/api/v1/honorarios-exito/{id}/rateio` (prefixo `/v1/` divergente do backend), além de `/api/teses/busca-avancada` e `/api/extratos/casos/{id}` (inexistentes).
- Ressalva: comparação por normalização de path — números aproximados.

## 8. Riscos consolidados (por prioridade)

1. **Gateway de IA duplicado**: `services/ai_gateway.py` (canônico, com governança) coexiste com `core/ai_brain.py` (classe `AIGateway` legada com `_call_ollama` próprio) — risco de chamadas de IA fora do log/HITL.
2. **404s reais em produção**: os paths `/v1/` divergentes do item 7 devem ser corrigidos ou confirmados como mortos.
3. **Módulos-balde de baixa coesão**: `ramos.py` (1.505 linhas, comunidade de 105 nós, coesão 0,04 — a pior do repo), `App.tsx` (68 nós, 0,03), `novos_modulos.py` (54 nós, 0,07).
4. **Componente gigante no frontend**: `pages/CasoDetalhe.tsx` com **3.921 linhas e 85 `useState`** — maior risco de manutenção do frontend. Outros: `DossieCliente.tsx` (927), `Ajuda.tsx` (882), `Conhecimento.tsx` (854).
5. **Duplicação nos Guias**: 13 `components/Guia*.tsx` somam 5.444 linhas, todos redefinindo o mesmo acordeão `Sec()` — candidato a extração para `UI.tsx` + guia dirigido por dados.
6. **Router sprawl**: 115 routers com sobreposições já mapeadas no Plano Fase 4 (IA 7→2, honorários 4→1, dossiês 3 conceitos colidentes; `analise_bancaria.py` vs `bank_analysis.py`, `peca_geracao.py` vs `peca_geracao_router.py`).
7. **Funções transversais como ponto único de quebra**: `criar_audit_log()`, `verificar_acesso_caso()` e `sanitizar_pii()` chamadas de dezenas de módulos por convenção (não middleware) — mudança de assinatura tem raio de explosão enorme e segurança depende de cada endpoint lembrar de chamá-las.
8. **Código possivelmente morto**: ~28 serviços-ilha no backend (`war_room.py`, `motor_estrategico.py`, `rpa_peticionamento.py`, `video_memoriais.py`, `sentimento_magistrado.py` etc.), páginas órfãs no frontend (`Login.tsx`, `Documentos.tsx`, `DataRoom.tsx` sem rota), 712 nós isolados e 1.385 fracamente conectados.
9. **Auth no frontend via localStorage** (tokens não-httpOnly, roles hardcoded em arrays por rota) — mitigado pelo RBAC do backend, mas XSS = roubo de sessão.
10. **Scheduler acoplado ao processo web** (`ENABLE_SCHEDULER` + workers=1 obrigatório) — escalar workers duplicaria jobs.

## 9. Pontos positivos

- Zero ciclos de import em 572 arquivos.
- Segurança em camadas testada: middleware global JWT, RBAC duplo, ownership anti-IDOR, isolamento RAG fail-closed com teste dedicado, criptografia de PII, 2FA, brute-force protection, auditoria pervasiva.
- Governança de IA madura: gateway único (canônico), custo por chamada, AILog/HITL, verificação de citações e bloqueio de jurisprudência não validada.
- Sinais de maturação arquitetural: event bus outbox, `app/modules/` vertical, guarda Alembic, lazy-loading e ErrorBoundary no frontend, design system interno reutilizado.

## 10. Recomendações

1. Eliminar/reduzir `core/ai_brain.py` a shim do gateway canônico.
2. Corrigir os 6–8 paths `/v1/` divergentes (404s) — verificação rápida e de alto impacto.
3. Executar a consolidação de routers da Fase 4 e decompor `ramos.py`.
4. Quebrar `CasoDetalhe.tsx` e extrair o acordeão `Sec()` dos 13 Guias.
5. Auditar os ~28 serviços-ilha e 43 routers sem consumo para remoção de código morto.
6. Introduzir camada de dados no frontend (react-query ou hooks `useApi`).
7. No graphify: excluir os .md de relatório da indexação e não usar `graphify path` para relações frontend↔backend (camada HTTP não modelada).
