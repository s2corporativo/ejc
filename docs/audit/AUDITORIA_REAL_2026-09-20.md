# EJC — AUDITORIA REAL, INVENTÁRIO E PLANO FECHADO DE LIMPEZA

**Data**: 2026-09-20 (UTC) · **Executor**: auditoria técnica sobre o estado real do repositório
**Regra desta etapa**: NENHUMA exclusão física foi executada. Nenhuma funcionalidade nova. Nenhuma terceira implementação. Este documento é a lista fechada baseada em evidência para a limpeza futura.

---

## 0. ESTADO BASE DA AUDITORIA

| Item | Valor |
|---|---|
| Repositório | `s2corporativo/ejc` (monorepo: `frontend/` + `backend/`) |
| Branch auditada | `main` |
| SHA | `c1be692557c5176c5f784c47a7e2d865e296bb51` |
| Data/hora | 2026-09-20 01:47 UTC |
| Diferenças locais | 0 (`git status` limpo; main == origin/main) |
| Última entrega merged | PR #1724 (reconstrução visual canônica, squash `c1be69255`) — **em produção**, validado por `/api/health` + CSS byte-idêntico |
| PRs abertas relacionadas | #1723 (sanitização str(e) gateway/ai_service — CRITICAL), #1722 (deep_research modo_sanitizacao — CRITICAL LGPD), #1721 (RBAC cliente_externo no-op — CRITICAL), #1719 (PostgreSQL hardening fase 2), #1715 (integrações externas / falsos verdes), #1713 (remove premium-dashboard.css órfão), #1720 (stale-bot triage) |
| Inventário regenerado | `python scripts/generate_architecture_inventory.py --check` → **8.077 itens**, fingerprint `39582ab0c8103c11…`, gate `all_items_classified: true`, `needs_review: 7.531` |
| Graphify | `graphify` binário indisponível no sandbox de execução → NÃO EXECUTADO (índice auxiliar; nada foi classificado com base nele — todo achado abaixo foi confirmado no código-fonte) |
| Produção em execução | `https://ejc.depaulateixeira.adv.br` — commit `c1be69255`, health `ok` |

Artefatos do inventário (regenerados nesta auditoria): `docs/audit/inventory/manifest.json`, `architecture_inventory.csv`, `architecture_inventory.json`, `duplicate_families.json`, `classification_review.csv`. O fingerprint do manifesto corresponde ao commit versionado nestes artefatos (`39582ab0…`); qualquer alteração futura no código exige regeneração para manter os números sincronizados.

---

## 1. ESTADO REAL DA ARQUITETURA

### 1.1 Frontend (React 19 + Vite + react-router + Zustand)

- **142 páginas**, ~110 rotas declaradas, **98,2% lazy** (56/57 roteadas lazy; única eager: `LoginModern`).
- Menu canônico atual: **11 domínios** (`config/canonicalNavigation.ts:16-28`) aplicados no shell `LayoutReference.tsx` — Início, Agenda e Prazos, Clientes, Casos, Financeiro, Documentos, Inteligência Jurídica, Banco de Teses, Radar Operacional, Relatórios, Configurações.
- Registry: `moduleRegistry.tsx` (1.425 linhas) com 44 módulos staff + portal (7 páginas) + **48 redirects legados**.
- Stores: 6 Zustand (`auth, caseContext, cadastroManual, moduleLifecycle, preferences, theme`). Services formais: 2 (`services/ai.ts`, `services/legalResearch.ts`) + `lib/api.ts` (axios) — porém existem **7 módulos HTTP de facto concorrentes** (`lib/stream.ts`, `lib/cofre.ts`, `lib/iaStatus.ts`, `lib/areas.ts`, `pages/dpt360/api.ts`, `radarApi.ts`, `reportApi.ts`).
- Imports circulares runtime: **0** (única aresta reversa é type-only: `lib/moduleLifecycle.ts:2`).
- **11 camadas CSS legadas** importadas em `main.tsx:5-30` (bronze-elegance, site-system, workspace-executive, premium-shell, premium-dashboard, saas-ultra-v2, saas-ultra-accessibility, ejc-reference-2026, ejc-reference-systemwide, ejc-dashboard-premium, ejc-tokens) — preservadas "para rollback visual"; `ejc-tokens.css` declarado como fonte única.

### 1.2 Backend (FastAPI + SQLAlchemy + Alembic + PostgreSQL/pgvector + Redis + Celery)

- **161 chamadas `include_router`** em `app/main.py:408-588` → **894 endpoints**, **0 colisões método+path** (verificado por AST com montagem real). **0 routers órfãos não montados** (o número "18 unmounted" do manifest é artefato de contagem por agregador — confirmado em código que todos montam direto ou via `ramos.py:17-132`).
- Middlewares (ordem): `AuthMiddleware` (JWT global + confinamento `cliente_externo` + 2FA gate), `APIVersionCompatibilityMiddleware`, `ClientIPMiddleware`, GZip, CORS.
- **355 arquivos de service**, 72 arquivos de model, 133 tabelas ORM, 33 arquivos de schema, 700 arquivos de teste.
- Scheduler: 1 × APScheduler (`ENABLE_SCHEDULER`, único dono = container backend; desligado no worker) com **42 jobs**. Celery sem beat: 6 tasks sob demanda.
- Healthchecks Docker em db/redis/backend/worker; timer systemd `ejc-deploy-approved` (5 min) + cron `monitor_health.sh` no host.

### 1.3 Banco

- **152 migrations**, head único `161_fee_estornos`, guardas `test_migration_reservations_head.py` + `MIGRATION_RESERVATIONS.md` + `test_migration_numbering_guard.py`.
- **133 tabelas ORM**; ~25 tabelas vivas em SQL cru sem model (drift inverso); **6 tabelas criadas em runtime via `CREATE TABLE IF NOT EXISTS`** (invisíveis ao Alembic).
- pgvector: `knowledge_chunks.embedding` Vector(1024) + HNSW (histórico 768→1024 concluído, legacy dropado na 145).

### 1.4 Núcleo IA (verificado de ponta a ponta)

Fluxo canônico confirmado: `POST /api/ai/core/{chat|task|analyze|generate|report}` → `orchestrator.run()` → intent_classifier (determinístico) → RBAC/ABAC → context_builder (ownership fail-closed) → ai_guard.sanitizar → AIProviderPolicy → gateway (cadeia por prioridade de produção `anthropic→maritaca→groq→ollama` conforme `config.py:337`/compose, com `OLLAMA_ENABLED=false` no runtime atual — o item local fica indisponível no fim da fila, piso de sigilo, barreira LGPD única) → response_validator → AILog (erro PROPAGA) → hitl_policy. **Nenhum bypass de gateway encontrado** (único SDK de IA importado em todo `app/` está dentro de `services/providers/anthropic_provider.py`).

---

## 2. MAPA FUNCIONAL ATUAL

### 2.1 Superfícies frontend ativas (roteadas)

| Superfície | Rota | Módulo canônico hoje | Consumo principal | Status |
|---|---|---|---|---|
| DashboardUltra | `/` | Início | `/api/dashboard`, `/api/health` | MANTER |
| EntradaUnica (+3 subpáginas, CadastroManual embutido) | `/entrada` | gateway Entrada Única | `/api/entrada`, `/api/entrada-universal`, `/api/clients` | MANTER |
| Casos + Kanban + CasoDetalhe (13 tabs) + Jornada | `/casos`, `/casos/:id` | Casos | `/api/cases`, `/api/processes`, orquestrador, `/rag/buscar` | MANTER (núcleo) |
| Central (+CentralAtividades, +CentralRelacionamento) | `/atividades` | Agenda e Prazos | `/api/atividades`, `/api/agenda-eventos` | CONSOLIDAR |
| Clientes + DossieCliente | `/clientes`, `/clientes/:clientId` | Clientes | `/api/clients`, `/api/atendimentos` | MANTER |
| GestaoDocumental (embute Documentos + DataRoom) | `/documentos` | Documentos | `/api/documents`, `/api/data-rooms` | CONSOLIDAR |
| InteligenciaWorkspace (10 tabs lazy) | `/inteligencia` | Inteligência Jurídica | `/api/ai`, `/api/rag`, `/api/conhecimento`, `/api/jurimetria` | MANTER |
| BancoTeses | `/teses` | Banco de Teses | `/api/teses` | MANTER |
| Pecas (+5 modais, catálogo) | `/pecas` | fora do menu 11 | `/api/legal-docs`, `/api/templates` | MANTER → absorver em Casos (alvo) |
| Radar (modos Compliance/Regulatorio) | `/radar` | Radar Operacional | `/api/compliance/radar`, `/api/regulatorio` | MANTER |
| FinanceiroWorkspace (6 tabs lazy) | `/financeiro` | Financeiro | `/api/financeiro`, `/api/fees`, `/api/nfse` | MANTER |
| Produtividade | `/produtividade` | Relatórios | `/api/analytics/produtividade` | MANTER |
| Configuracoes (+AccountSecurity, Cofre, Lifecycle) | `/configuracoes` | Configurações | `/api/users`, `/cofre-credenciais` | MANTER |
| Portal do cliente (7 páginas) | `/portal/*` | Portal | `/api/portal` | MANTER |
| Ajuizamento (+Perfis) | `/ajuizamento` | fora do menu 11 | `/api/ajuizamento/filings` | MANTER (contexto de Caso) |
| Sala Jurídica / Raio-X | `/sala-juridica`, `/raio-x` | fora do menu 11 | `/api/sala-juridica`, `/api/raio-x` | MANTER (contexto) |
| DPT360 (DptFeatureRouter, 8 features) | `/dpt360/*` | fora do menu 11 | `/dpt360/*` (3 módulos api) | MANTER (radar do dashboard consome) |
| RamosHub + 14 guias + 7 workspaces de área | `/areas-de-atuacao/*`, `/tributario` | fora do menu 11 | por ferramenta | MANTER (catálogo /ferramentas) |
| Ferramentas (calculadoras, defesas, extratos) | `/ferramentas` | fora do menu 11 | calculadoras | MANTER |
| Catálogos: assinaturas, workflow, checklists, prompts, datajud, diário-oficial | rotas próprias | fora do menu 11 | por domínio | MANTER (hub Ferramentas) |
| Admin: usuarios, auditoria, mapa-modulos, diagnostico, lixeira, ia-governança(+provedores) | rotas próprias | fora do menu 11 (gestores/admin) | por domínio | MANTER → Administração (alvo) |
| CRMLeads | `/crm-leads` | hidden | `/api/clients` | INVESTIGAR (módulo oculto **sem RBAC de rota**) |
| 48 redirects legados + 3 dinâmicos | `LEGACY_REDIRECTS` | — | — | REDIRECIONAR (manter 90 dias c/ telemetria — expurgo condicionado à instrumentação frontend, ver §12.5) |

### 2.2 Backend — routers por domínio (principais; tabela completa no inventário CSV)

- **Casos**: `cases.py` (20 ep, RBAC ✓), `case_partes`, `case_intelligence`, `matriz_teses`, `provas`, `kit_documental`, `motor_peca`, `orquestrador`, `conversao_caso`, `andamentos`, `etiquetas`, `sumulas`, `caso_areas`, `indice_risco`, `score_juridico`, `solicitacoes_documentos`, `kanban`, `processes`, `movimentos`.
- **Documentos/Peças**: `documents` (14), `legal_docs` (16), `peca_geracao` (5), `templates`, `export`, `data_room` (12), `anexos`, `procuracoes`, `processo_eletronico` (5).
- **Agenda/Prazos**: `deadlines` (8), `atividades`, `agenda_eventos`, `tasks`, `calendar_feed` (ICS HMAC), `intimacoes` (DJEN).
- **Financeiro**: `fees` (9), `nfse` (9), `despesas`, `despesas_processuais`, `financeiro_consolidado` (SUPERADMIN), `centro_custos`, `office_contracts`, `partner_withdrawals`, `pix`, `relatorio`, `timesheet`, `honorarios_oab` (14), `indices` (BCB).
- **Clientes**: `clients` (16), `pending_items`, `dossie_cliente`, `atendimentos` (12), `sociedades_cliente` (10), `relatorio_cliente`.
- **IA/RAG/Conhecimento**: `ai` (25), `ai_core` (9), `ai_skills`, `ai_tools`, `ia_capacidades`, `ia_citacoes`, `ia_adversarial`, `ia_agente`, `ia_saude`, `ia_especializada`, `ia_defensiva`, `rag` (12), `rag_governance`, `rag_public` (X-API-Key), `google_drive_knowledge`, `juris_import`, `teses` (15), `jurisprudencia_interna`, `precedentes_jurisprudencia`, `legal_chat` (14), `cerebro`, `ia_governanca` (13), `visual_law`.
- **Integrações**: `app/integrations/routers.py` (15 ep: datajud, djen, brasilapi/ckan), `datajud`, `datajud_intelligence`, `diario_oficial` (7), `infosimples_tjmg`, `car`, `evolution_webhook` (público + secret timing-safe).
- **Admin/compliance**: `users` (14), `auth` (9), `api_keys`, `audit`, `backup_admin`, `saneamento` (8), `system_modules`, `module_settings`, `module_help`, `trash`, `lgpd_registros`, `transparencia`, `observabilidade`, `diagnostico`, `compliance`, `regulatorio` (**sem testes — único "N" absoluto**), `workflow` (8), `checklists` (10), `signatures` (5), `search`, `notifications` (9), `whatsapp`, `utils`, `areas`.

---

## 3. MAPA FUNCIONAL ALVO (menu canônico de 9 módulos)

> Princípio: a entidade central continua sendo o **CASO**. Nada é removido por sair do menu — funções migram para contexto. Portal e Administração têm shell próprio.

```text
1. DASHBOARD
   └── DashboardUltra (atual) + radar DPT360 + notificações
2. CLIENTES
   ├── dossiê do cliente (DossieCliente)
   ├── sociedades do cliente (sociedades_cliente)
   ├── atendimentos, pendências, relatório financeiro do cliente
   └── CRMLeads (após definir RBAC; se ativo) + cadastro manual (via Entrada Única)
3. CASOS  ← workspace central (CasoDetalhe já tem 13 tabs)
   ├── dados, partes (case_partes), processos (Process 1:N), movimentos
   ├── documentos (documents + kit_documental + data room do caso)
   ├── prazos/tarefas/intimações do caso (deadlines, tasks, DJEN)
   ├── peças (legal_docs + peca_geração + motor_peça)  [absorve /pecas como tab]
   ├── estratégia: provas, matriz de teses, score, inteligência, defesas/revisões
   ├── ajuizamento → protocolo → acompanhamento (ajuizamento.py)
   └── financeiro do caso (fees, despesas processuais)
4. AGENDA E PRAZOS
   ├── Central (atividades + relacionamento), AgendaDia
   ├── deadlines globais, audiências, calendário ICS
   └── intimações DJEN, workflow SLA, checklists operacionais
5. PEÇAS (superfície de produção revisada; cada peça pertence a um Caso ou a um cliente — peças sem caso, ex.: contratos e procurações de admissão `geracao_documental_cliente.py:389-405`, continuam acessíveis nesta superfície global/por-cliente mesmo após W3/W5)
   ├── catálogo + geração (peca_geracao) + auditoria de peça
   └── HITL: ai_generated + human_reviewed obrigatórios (já no model)
6. CONHECIMENTO JURÍDICO
   ├── RAG governado (rag, rag_governance, conhecimento_ingest)
   ├── Banco de Teses (teses + matriz_teses como contexto de caso)
   ├── jurisprudência interna/externa, importação (juris_import)
   ├── jurimetria + pesquisa jurídica (tabs da Inteligência hoje)
   └── IA operacional (InteligenciaWorkspace) — portal único de IA
7. FINANCEIRO
   ├── fees/ledger (fee_payments + estornos), NFSe, despesas
   ├── honorários OAB, centro de custos, contratos do escritório
   └── relatórios financeiros, índices econômicos (BCB)
8. PORTAL DO CLIENTE (isolado; cliente_externo confinado por middleware)
   └── casos, financeiro, assinaturas, mensagens, documentos, solicitações
9. ADMINISTRAÇÃO (gestores/admin)
   ├── usuários, papéis, 2FA, api-keys, cofre de credenciais
   ├── auditoria, mapa de módulos, saneamento, lixeira
   ├── governança IA (ia-governanca, provedores, ia-saúde, diagnóstico)
   └── LGPD (registros, purga), backups, integrações, sistema
```

**Absorções-chave (sem perda de função)**: `/pecas` → tab de Caso (workspace) + atalho no menu 5; Data Room → contexto de Caso/Documento; Sala de Guerra (redirect dinâmico `/casos/:id/sala-de-guerra`) → já é contexto de caso; Teses → Conhecimento + panel no Caso; Jurimetria → Conhecimento; DataJud/Diário/Intimacoes → Agenda (prazos) + Conhecimento (conteúdo); IA dispersa → Conhecimento/IA operacional.

---

## 4. DUPLICAÇÕES CONFIRMADAS (evidência no código atual)

### 4.1 Frontend

| # | Família | Implementações | Canônica | Evidência | Ação |
|---|---|---|---|---|---|
| F1 | Dashboard | `Dashboard.tsx` (wrapper 1 linha) + `DashboardUltra.tsx` | Ultra (rota `/`) | `pages/Dashboard.tsx:1` | CONSOLIDAR (apontar registry direto) |
| F2 | Documentos | `GestaoDocumental` + `Documentos` + `DataRoom` | GestaoDocumental | `GestaoDocumental.tsx:3-4` | CONSOLIDAR (3→1) |
| F3 | Conhecimento | `Conhecimento.tsx` + `ConhecimentoGovernado.tsx` | ConhecimentoGovernado (tab) | `InteligenciaWorkspace.tsx:35` | CONSOLIDAR |
| F4 | Sociedade | `Sociedade.tsx` + `SociedadeWorkspace.tsx` | Workspace | `SociedadeWorkspace.tsx:1` | CONSOLIDAR |
| F5 | Central | Central + CentralAtividades + CentralRelacionamento | Central (tabs lazy) | `Central.tsx:15-16` | MANTER (conviver documentado) |
| F6 | HTTP | `lib/api.ts` (axios) vs `lib/stream.ts` (fetch+refresh próprio) | api.ts | `lib/stream.ts:15-28` | CONSOLIDAR |
| F7 | GET /areas | 3 caminhos (lib/areas.ts, RamosHub:331 raw, RaioXProcesso:368 raw) | lib/areas.ts | linhas citadas | CONSOLIDAR |
| F8 | /rag/buscar | service legalResearch:29 + 2 raw (Conhecimento:808, TabIndicadoresJuridicos:51) | service | idem | CONSOLIDAR |
| F9 | dpt360 api | api.ts + radarApi.ts + reportApi.ts | api.ts único | — | CONSOLIDAR |
| F10 | Taxonomia áreas | areaCatalog.ts estático vs taxonomia.ts gerada | gerada | comentário admite pendência PR #1387 | INVESTIGAR |
| F11 | AI raw calls | TabResumo:545/565, TabFerramentas:232/255, ContextualAIAssistant:204/268, Pecas (/ai/auditar-peca) | services/ai.ts | idem | CONSOLIDAR |
| F12 | CSS | 11 camadas em main.tsx:5-30 | ejc-tokens.css | main.tsx:12-14 | P3 (ver waves) |

### 4.2 Backend

| # | Família | Implementações | Canônico | Evidência | Ação |
|---|---|---|---|---|---|
| B1 | DataJud | 4 routers (datajud, integrations/datajud, datajud_intelligence, andamentos) + 4 services | `datajud_service` | main + services citados | CONSOLIDAR (aliases) |
| B2 | DJEN | `ing_djen` 05:00 + `djen` 06:30 consultam a MESMA API Comunica | unificar captura+ingest | scheduler.py:1421,1439 | CONSOLIDAR jobs |
| B3 | Peças/LegalDoc | 6 routers (peca_geracao, legal_docs, motor_peca, defesas_revisoes×2, advogado_estilo) + 6 services | peca_geracao + legal_docs | main:540 | CONSOLIDAR (longo prazo) |
| B4 | Teses | teses (ADR canônico) + matriz_teses + compat v4 | `teses` | ADR_BANCO_TESES_CANONICO | MANTER matriz como contexto; apagar compat v4 após telemetria |
| B5 | Ingestão RAG | `services/ingestors/` (scheduler) vs `services/juris_import/` (router) — overlap lexml/stj/tjmg | unificar pipeline | scheduler.py:1990-2087 vs juris_import/ | CONSOLIDAR |
| B6 | Brief/honorários | `_morning_brief`/`_alertar_honorarios` têm 2 corpos (scheduler.py:74/811 mortos em runtime; scheduler_financeiro.py:82/204 via monkey-patch) | scheduler_financeiro | event_subscribers.py:103 | CONSOLIDAR (remover corpos mortos) |
| B7 | Jurisprudência | `jurisprudencias_internas` vs `knowledge_docs.categoria=jurisprudencia` | runbook dedup existe | RUNBOOK_DEDUPLICACAO_BASE_CONHECIMENTO.md | INVESTIGAR |
| B8 | Ledger fees | `fees.status/data_pagamento` (legado) vs `fee_payments` (canônico) | fee_payments | `fee_ledger_compat.py:1-14` | MANTER compat até backfill |
| B9 | Case vs Process | campos homônimos legados em `cases` (numero_processo/tribunal/comarca/vara) vs `processes` | processes | process.py:34-41, processo_service.py:102 | CONSOLIDAR leitura |

---

## 5. CÓDIGO MORTO COMPROVADO (0 consumidores — remover APÓS migração, com PR próprio)

| Arquivo | Evidência | Teste órfão junto |
|---|---|---|
| `frontend/src/pages/ConteudoJuridico.tsx` | rota virou redirect (moduleRegistry:1102); 0 imports | `ConteudoJuridico.test.tsx` |
| `frontend/src/components/DashboardAiChat.tsx` | 0 imports, 0 testes | — |
| `frontend/src/components/CaseClosureModal.tsx` | 0 imports | `CaseClosureModal.test.tsx` |
| `frontend/src/components/DeadlineRiskStrip.tsx` | 0 imports | `DeadlineRiskStrip.test.tsx` |
| `frontend/src/components/JurisprudentialAlertsStrip.tsx` | 0 imports | `JurisprudentialAlertsStrip.test.tsx` |
| `backend/app/services/visual_law_pdf.py` | 0 refs em app/ (só testes) | test dedicado |
| `backend/app/services/document_version_chain_readiness_service.py` | 0 refs em app/ | test dedicado |
| `backend/app/services/document_version_audit_service.py` | único consumidor é o service morto acima | 2 tests |
| `backend/app/services/scheduler.py:_verificar_sincronia_datajud` (1121) | função definida, nunca registrada em add_job | — |
| `backend/app/services/scheduler.py:74` e `:811` | corpos substituídos por monkey-patch (scheduler_financeiro) | — |
| `component: Casos` do módulo `caso-novo` (moduleRegistry.tsx:309) | App troca por LegacyRedirect | — |
| `moduleRegistry.tsx:186-190` | comentário cita KnowledgeHub/Biblioteca/Memoria/Wiki que não existem mais | — |

**Nota**: PR aberta #1713 já propõe remover `premium-dashboard.css` órfão — convergente com esta auditoria.

---

## 6. CÓDIGO SUSPEITO QUE NÃO PODE SER REMOVIDO AINDA (INVESTIGAR)

| Item | Motivo de cautela |
|---|---|
| Tabelas `dataroom_salas` + `teses_juridicas_v4` (models/dataroom_teses_v4_compat.py) | migradas para data_rooms/teses na 114, mas **origem permanece no banco** (retirada física condicionada); requer dump de evidência + telemetria antes de qualquer DROP |
| Tabelas `preliminares` + `preliminar_documentos` + `preliminar_mensagens` + `preliminar_estados` (migration 140) | "fundação" da fusão Sala+Raio-X **nunca ativada**; a própria docstring diz que `raio_x_*`/`legal_chat_*` seguem como fonte de verdade. Decidir: ativar cutover ou arquivar |
| `wiki_paginas` (models/wiki.py) | "LEGADO SEM SUPERFÍCIE" autodeclarado; só remover após confirmar que nenhum dado vale preservar (export antes) |
| ~25 tabelas em SQL cru sem model (agenda_eventos, areas, kanban_columns, score_juridico, memoria_institucional, portal_mensagens, etc.) | vivas e consumidas por routers via SQL — trazer para ORM antes de tocar |
| 6 tabelas criadas em runtime (`indices_bcb_cache`, `radar_legislativo_visto`, `infosimples_uso`, `transparencia_cache`, `google_drive_sync_state`, `backup_drive_state`) | invisíveis ao Alembic; trazer para migrations antes de qualquer refactor |
| `processes` (modelo sobre tabela criada por SQL cru na 048) | padrão documentado no cabeçalho; não mexer sem plano |
| `case_partes` plaintext legado + `trabalhista_cases.cid` | rollout de criptografia em curso (158); Fase B só após `legacy_plaintext_count=0` comprovado |
| Redirects `LEGACY_REDIRECTS` (48) + ramos de agregador com handler legado pulado (`ramos.py:87-98`) | manter por 90 dias antes de expurgo; `route_usage.py` monitora apenas 16 templates de backend e NÃO registra paths de frontend (legados nunca chegam ao service) — pré-condição: instrumentar navegação frontend (ou sinal visível ao servidor) antes de tratar métrica como prova de desuso |
| `/crm-leads` | módulo oculto sem RBAC de rota — decidir: ativar com RBAC, redirecionar ou desativar |
| `regulatorio.py` (router montado, 1 ep) | **sem nenhum teste** (único "N" absoluto); cobrir com teste antes de qualquer mudança |
| `document_persistence/document_hash` cadeias | vivas, mas cadeia version_* parcialmente morta — mapear dependências antes |
| `fees.status` legado | usado por compat — só remover após backfill controlado |

---

## 7. JOBS QUE CONSOMEM RECURSOS (42 APScheduler + 6 Celery)

**Sempre ativos (intervalo)**: `telemetria_rotas` (15 min), `cofre_overlay_retry` (10 min; no-op pós-sucesso), `reembed_rag_orfaos` (1 h; no-op sem órfãos, batch 20).
**Agendados diários**: briefing 06:55/07:00, prazos 07:10/07:15, audiências 07:20, workflow_sla 07:30, solicitacoes 07:45, honorarios 08:00, regua 08:15, ambiental 08:30, regua_cliente 08:30*, societario 09:15, djen 06:30 (+ing 05:00), datajud 08:45/16:45, dou 06:00, radar_legislativo 07:00 UTC, feriados 00:05, expurgo_entrada 03:50*, telemetria_expurgo 03:40, purga_ia dom 02:00, purga_lgpd dom 02:30, backups 05:00 UTC*.
**Semanais**: planalto dom 03:00, stj sáb 03:00, camara 04:00, senado 04:20, djen_ing 05:00, tjmg sáb 04:30, lexml sáb 05:00, conhecimento dom 03:00 UTC, procuracoes/prescricao/contratos/relatorio_dono/auditoria seg 07-09h, relatorio_mensal dia 1.
**Celery (sob demanda, sem beat)**: indexar_documento (retry 3), ocr_documento (2), raio_x_processar (**max_retries=0 p/ não duplicar custo de IA**), sincronizar_processo (4), sincronizar_avisos (3), testar_credencial; hook vault_sync a cada task.
**Frontend**: notificações 60 s no layout global; painéis IA/diagnóstico 30/60 s; polling condicional Raio-X 3 s×100, MotorTeses 2 s, Conhecimento 2,5 s×72.
**Gates de desligamento por env**: `ENABLE_SCHEDULER`, `DATAJUD_ENABLED` (default False), `DATAJUD_SYNC_ENABLED` (False), `QUERIDO_DIARIO_MONITOR_ENABLED` (False), `RELATORIO_DONO_ENABLED` (False), `COBRANCA_ENABLED` (False), `BACKUP_ENABLED` (False), `ENTRADA_EXPURGO_ENABLED` (False), `TJMG_INGEST_ENABLED`, `LEXML_INGEST_ENABLED`, `CONHECIMENTO_INGEST_ENABLED`, `DJEN_INGEST_ENABLED`, `AI_RESPONSE_CACHE_ENABLED` (**False — ver gargalo G1**), `EMAIL/WHATSAPP/PUSH_ENABLED` (False).

Classificação completa (SEMPRE ATIVA/AGENDADA/SOB DEMANDA/CONDITION-BASED/DESABILITÁVEL/LEGADA/DUPLICADA) está no CSV de backlog e na seção 7 do relatório DOCX anexo.

---

## 8. GARGALOS PROVÁVEIS

| # | Gargalo | Evidência | Ganho esperado | Custo da correção |
|---|---|---|---|---|
| G1 | **Cache de IA implementado e DESLIGADO** — toda chamada repetida paga token de novo | `config.py:1097` (`AI_RESPONSE_CACHE_ENABLED=False`), gateway já implementa (ai_gateway.py:547-558,1245-1256) | redução direta de custo/latência de IA | **ligar 1 flag** (baixo) |
| G2 | **DJEN consultado 2×/dia na mesma API** (05:00 janela 2 dias + 06:30 re-consulta) | scheduler.py:1421,1439 | ~50% das chamadas CNJ | médio (unificar job) |
| G3 | **Polling de notificações 60 s em toda tela logada** | LayoutReference.tsx:121 | QPS constante → evento/on-focus | médio (SSE ou revalidate-on-focus) |
| G4 | **N+1 de escrita no scheduler** (UPDATE por linha de prazo; commit por destinatário) | scheduler.py:201-205,275-300,343,423 | DB writes −80% em janelas de pico | baixo (batch) |
| G5 | N+1 em DJEN (insert por item), MNI dedup (por documento), sumulas, case_intel, fee_proposal | djen_service.py:686-716; processo_eletronico_document_mapper.py:175-179; sumulas_ingestion.py:263-275; case_intelligence_service.py:57-58; fee_proposal_service.py:220-221 | latência de jobs | baixo/médio |
| G6 | **279 SQL cru** (top: scheduler 31, financeiro_consolidado 20, ai_service 18, despesas 14) | grep text( | manutenibilidade + risco de drift | longo prazo (padrão process_repository a replicar) |
| G7 | Cache DataJud em memória por processo (premissa worker único) | datajud_service.py:74-78,143-161 |失效 quando houver >1 worker | baixo (Redis) |
| G8 | Backoff fixo 2-3 s nos fluxos assíncronos do frontend | RaioXProcesso:196, MotorTeses:70, Conhecimento:573 | ~60% menos chamadas de acompanhamento | baixo |
| G9 | `backup_drive` grava heartbeat "erro" diário enquanto desligado | scheduler.py:1286-1291 | ruído diagnóstico | baixo (estado "desligado") |
| G10 | Embeddings ONNX ~2,3 GB RAM no processo API/worker | embedding_service.py:2-13; mem_limit compose | já contido por mem_limit; monitorar | nenhum (ponto de atenção) |

---

## 9. BACKLOG PRIORIZADO

Tabela fechada (ID, Módulo, Arquivo, Problema, Status, Ação, Risco, Dependências, Teste, Rollback, Ordem) em **`docs/audit/BACKLOG_LIMPEZA_2026-09-20.csv`**. Resumo de prioridades:

- **P0 (risco de segurança/dados)** — 2FA default: risco ACEITO por decisão permanente do Titular (ver P1/S1 — não é ação de backlog); 3 downloads de arquivo gerado sem titularidade (`ambiental_estrategia.py:239` sem gate; `trabalhista_liquidacao.py:337` capability-UUID; `previdenciario_beneficio.py:230-245` + `tributario_fiscal.py:364-383` idem — S10); PRs #1721/#1722/#1723 (CRITICAL) pendentes de merge.
- **P1 (duplicação com impacto operacional)** — G1 cache IA off; B2 DJEN duplo; G3 polling 60 s; B1 DataJud 3 rotinas; B6 corpos mortos de scheduler.
- **P2 (simplificação estrutural)** — F1-F11 (consolidações frontend), B3/B5 (peças/ingestão), módulo alvo de 9, routers "só JWT" sem gate de papel (60+), bundle eager (LoginModern, EntradaUniversalGlobal, CommandPalette, SecurityMenu, PortalLayout).
- **P3 (limpeza física)** — seção 5 (dead code), camadas CSS legadas, redirects expirados, tabelas órfãs após evidência.

Status de execução: **TODOS os itens NÃO INICIADO** nesta etapa (nenhuma limpeza executada — por design).

---

## 10. PLANO DE WAVES (execução futura, incremental)

| Wave | Escopo | Branch base | Riscos | Testes/condição de promoção | Rollback |
|---|---|---|---|---|---|
| W1 | Navegação/moduleRegistry → menu 9 | feat/w1-menu-9 | regressão de deep-links | tsc+vitest+test:navegacao; redirects intactos (telemetria de redirects exige instrumentação frontend prévia — §4/BE-10 associado) | revert PR |
| W2 | Dashboard | feat/w2-dashboard | baixo (já canônico) | visual 4 viewports | revert |
| W3 | Caso como workspace central (absorve peças/docs/prazos como tabs) | feat/w3-caso-workspace | médio: 13 tabs atuais + novas tabs | test:navegacao + e2e tabs + RBAC | feature flag por tab |
| W4 | Agenda/Prazos/Tarefas/Intimações | feat/w4-agenda | médio (jobs dependem) | testes de scheduler com frozen time | revert + flag |
| W5 | Peças/LegalDoc (consolida B3) | feat/w5-pecas | alto: 6 routers | contratos HTTP preservados + testes de geração | aliases temporários |
| W6 | Conhecimento/Teses/Jurimetria (B4, B7) | feat/w6-conhecimento | médio: RAG quente | testes de ingest + dedup runbook | aliases |
| W7 | Data Room/Sala de Guerra | feat/w7-dataroom | médio: acesso público por token | testes de grants HMAC | revert |
| W8 | IA/RAG (consolidar portas legadas: /ia/analisar-caso→core) | feat/w8-ia | alto: custo/sigilo | eval suite (app/eval) + AILog diff | flag de porta |
| W9 | Jobs e integrações (G1-G4, B2, cache Redis DataJud) | feat/w9-jobs | médio: cadências | dry-run 48 h com telemetria | env flags (todos os jobs têm gate) |
| W10 | Dead code comprovado (seção 5) | chore/w10-dead-code | baixo (0 consumidores provado) | build+testes verdes + grep CI anti-retorno | revert |
| W11 | Banco/backend otimização (N+1 batch, SQL cru→repo, tabelas runtime→migrations) | feat/w11-db | alto: dados | migrations aditivas + testes _dblevel | downgrade por migration |
| W12 | Homologação final + expurgo de redirects/tabelas com evidência | chore/w12-homologacao | — | checklist 9 módulos × 4 viewports × LGPD | — |

Cada wave: PR único, gates obrigatórios (tsc/eslint/vitest/test:responsive/build) + Woodpecker verde + squash-merge; telemetria `route_usage` antes/depois.

---

## 11. RISCOS LGPD/SEGURANÇA

| Prio | Risco | Caminho | Mitigação proposta |
|---|---|---|---|
| P1/S1 | 2FA desligado por default (`TWO_FACTOR_AUTH_ENABLED=false`, `REQUIRE_2FA_ROLES=""`) | `core/two_factor_policy.py:26,39-40`, `.env.example:34-35` | **RISCO ACEITO — decisão permanente do Titular** (`docs/GOVERNANCA_IA.md:224-233`: 2FA permanece OFF por default; auditorias registram o risco, sem convertê-lo em correção obrigatória). Só reabrir mediante NOVO pedido expresso do Titular. Infra de ativação permanece implementada e testada para uso futuro. |
| P0/S2 | Download de peça ambiental sem gate de papel/ownership (qualquer autenticado) | `routers/ambiental_estrategia.py:239` | replicar gate do análogo trabalhista + binding usuário↔arquivo |
| P1/S3 | Download planilha trabalhista: confidencialidade = não-guessabilidade do UUID | `routers/trabalhista_liquidacao.py:337` | idem |
| P1/S4 | PRs CRITICAL em aberto: RBAC cliente_externo no-op (#1721), sanitização deep_research (#1722), str(e) gateway (#1723) | PRs | merge imediato após CI |
| P2/S5 | CSP e Permissions-Policy JÁ versionadas e ativas no caminho do frontend (`frontend/nginx.conf:19-26`, replicadas em cada location que sobrescreve cache, instaladas no image via `frontend/Dockerfile:11-13`) | drift potencial entre `frontend/nginx.conf` e `nginx/ejc.conf` do host — reconciliar duplicidade | ação reduzida a verificar propagação real dos headers (evita headers duplicados conflitantes) |
| P2/S6 | JWT HS256 simétrico sem rotação por kid | `core/security.py:172` | aceito por design; planejar rotação documentada |
| P2/S7 | `GET /ia/logs` (sócio+) sem filtro de caso | `routers/ai.py:172-192` | revisar necessidade de filtro por caso |
| P3/S8 | Rate limit em memória é por-processo se Redis off | `core/rate_limit.py:7-10` | manter Redis on (compose já ativa) |
| P3/S9 | Comentário obsoleto "sanitizar_pii PASSTHROUGH" em langfuse_client pode induzir regressão | `observability/langfuse_client.py:10-11` | corrigir comentário |
| P1/S10 | IDOR por capability-UUID em arquivos gerados, além dos já listados em S2/S3: `previdenciario_beneficio.py:230-245` e `tributario_fiscal.py:364-383` autorizam só por papel e servem qualquer UUID gerado sem binding a criador/cliente/caso | `routers/previdenciario_beneficio.py`, `routers/tributario_fiscal.py` | replicar binding usuario↔arquivo dos análogos + teste de RBAC (backlog SEC-05) |

**Integridade confirmada (não simplificar)**: AuthMiddleware global + confinamento portal; ownership canônico (`core/ownership.py`, `client_ownership.py` — varredura anti-IDOR: nenhum endpoint de recurso sem gate; exceções conhecidas por capability-UUID estão em S2/S3 **e** S10, todas em backlog p/ binding); AuditLog WORM por trigger DB (migration 131); PII Fernet+HMAC cego; barreira LGPD única no gateway; HITL inegociável; sigilo reforçado com piso LOCAL_COMPLETO inão-rebaixável; sanitização de log; ICS HMAC; webhook público com secret timing-safe; rate limit Redis em ~260 endpoints.

---

## 12. ESTRATÉGIA DE ROLLBACK (global)

1. **Branch protection + squash-merge**: cada wave entra por PR revisável; revert = 1 commit.
2. **Feature flags/env**: todo job tem gate (`ENABLE_SCHEDULER`, gates por fonte); portas IA têm flag de roteamento; menu 9 atrás de flag até homologação.
3. **Banco**: regra para as waves futuras = migrations **aditivas** em upgrade (a base legada NÃO é totalmente aditiva — `145_drop_orphan_db_only_columns.py:92-96` e `112_client_pii_drop_plaintext.py:99-112` fazem drop em `upgrade()`); drops só em downgrade ou wave de expurgo com dump prévio + `MIGRATION_RESERVATIONS.md` atualizado + guardas de teste. Rollback de schema ≠ restauração de dados.
4. **CSS/UI**: camadas legadas preservadas até W12 (rollback visual por remoção de import em main.tsx).
5. **Aliases HTTP e redirects frontend**: consolidar endpoints mantendo alias por 90 dias com telemetria (`route_usage_metrics`/`ai_provider_metrics` implementados e limitados a 16 templates de backend — redirects legados do frontend EXIGEM instrumentação de navegação antes de qualquer expurgo) antes de REMOVER APÓS TELEMETRIA.
6. **Dados**: export obrigatório (`/api/export`, backup cifrado Drive) antes de qualquer saneamento/fusão. ⚠️ Hoje `routers/saneamento.py:220-221` só exige `confirmar=true` — NÃO há gate verificável de backup, e `services/saneamento/fusao.py:124-135,171-182` pode apagar linhas colidentes de forma irreversível. A fusão é, neste momento, **irreversível**: a implementação do gate de backup/restauração é pré-condição no backlog antes de qualquer fusão real.
7. **Produção**: deploy automático 5 min pós-merge; rollback de deploy = revert na main → CI → timer; `/api/health` expõe commit para verificação imediata.

---

## 13. MÉTRICAS BASELINE (pré-limpeza — 2026-09-20, commit c1be6925)

| Métrica | Valor | Fonte |
|---|---|---|
| Containers sempre-on / opt-in | 5 (db, redis, backend, worker, frontend) + 4 (langfuse×2, ollama×2) | docker-compose.yml |
| CPU/memória de produção | NÃO TESTADO (acesso SSH indisponível no sandbox; credenciais VPS registradas para execução futura) | — |
| Tamanho de imagens | NÃO TESTADO (idem) | — |
| Tempo de startup backend | gated por `_passo_de_boot` com timeout por passo (main.py:211-262); valor real NÃO TESTADO | main.py |
| Routers montados | 161 (main.py:408-588) | AST |
| Endpoints | 894 (0 colisões) | AST |
| Páginas frontend | 142 | ls |
| Rotas declaradas | ~110 (48 redirects legados) | App.tsx+registry |
| Serviços backend | 355 arquivos | ls |
| Serviços frontend formais | 2 (+7 módulos HTTP de facto) | grep |
| Models / tabelas ORM | 72 arquivos / 133 tabelas | grep __tablename__ |
| Migrations | 152 (head 161_fee_estornos) | alembic/versions |
| Jobs APScheduler | 42 (3 intervalo, ~39 agendados/condicionais) | scheduler.py |
| Tasks Celery | 6 sob demanda + 1 hook | app/tasks |
| Tamanho do bundle frontend | JS 2,32 MB em 189 chunks (entry 299 KB; maior RamoBase 335 KB; CasoDetalhe 251 KB); CSS 310 KB; dist 5,2 MB | vite build |
| Lazy loading | 98,2% das páginas roteadas | registry |
| Queries SQL cru | 279 ocorrências `text(` | grep |
| Chamadas externas periódicas | DJEN 2×/dia; DataJud 2×/dia (no-op se gate off); DOU 1×; QueridoDiário*; radar legislativo 1×; ingest 7 fontes semanais; BrasilAPI semanal | scheduler.py |
| Chamadas de IA | via gateway único; cache de resposta DISPONÍVEL mas OFF; embeddings locais (sem custo API) | ai_gateway/config |
| Testes | frontend vitest 818 ✓; backend 700 arquivos de teste | suites |
| PRs abertas | 7 (#1713-#1723) | GitHub API |
| Inventário geral | 8.077 itens classificados; needs_review 7.531; fingerprint 39582ab0… (artefatos regenerados e versionados neste PR) | manifest.json |

---

## CRITÉRIO DE CONCLUSÃO DA AUDITORIA

Todo item candidato a exclusão possui: (a) evidência técnica confirmada em código (0 consumidores / função morta / duplicação com canônico definido), (b) classificação na lista fechada (MANTER/CONSOLIDAR/MOVER PARA CONTEXTO/REDIRECIONAR/DESATIVAR/EXCLUIR APÓS MIGRAÇÃO/INVESTIGAR), (c) wave de execução, (d) teste e (e) rollback definidos. **Nenhuma exclusão foi executada nesta etapa.** A limpeza física só ocorre nas waves 10-12, condicionada à telemetria e às evidências aqui registradas.
