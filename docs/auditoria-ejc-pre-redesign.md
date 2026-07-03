# Auditoria Técnica Pré-Redesign — EJC (Ecossistema Jurídico Clovis)

**Data:** 2026-07-03
**Base analisada:** `C:\Users\User\ejc-canonical` (espelho de produção + fixes de segurança, GitHub `main` @ c97392f) — **working tree com 101 arquivos modificados não commitados** (refatoração visual "Fase 3").
**Método:** 4 agentes de mapeamento em paralelo (frontend, backend/API, banco de dados, gap analysis) + grafo Graphify (`C:\Users\User\EJC\graphify-out`, 4528 nós / 8626 arestas / 440 comunidades, commit 7592203).
**Regra vigente:** não regressão — nenhuma rota, integração, regra de negócio, dado, permissão ou módulo funcional é removido sem necessidade comprovada e registro neste relatório.

---

## 0. ESTADO CRÍTICO DO WORKING TREE (ler antes de qualquer alteração)

- O `main` local = `origin/main` (c97392f), que já contém o PR #6 `ui/refatoracao-visual` e o PR #8 (chat do portal).
- **Sobre o main há 101 arquivos modificados NÃO COMMITADOS** (+2.049/−2.318 linhas), incluindo `frontend/src/pages/Login.tsx` deletado (substituído por `LoginModern.tsx`, já roteado). É a **"Fase 3" do redesign visual**: `tailwind.config.js` desfaz o remap de `blue/violet/purple` e migra os literais legados para tokens `primary-*` (bronze) e `ai-*` (petróleo); sidebar migrada de espresso para **slate escuro `#0F172A`** — exatamente a base cromática tech/fria com bronze/gold do redesign.
- **Verificação:** `npx tsc --noEmit` passa sem erros no working tree. Migração de literais completa (0 ocorrências de `bg-blue-`, `violet`, `purple` em .tsx).
- **Risco:** trabalho não commitado = risco de perda. **Recomendação: commitar como `ui/fase-3-tokens` antes da Fase 2 do redesign.** (Decisão pendente do usuário — ver checkpoint.)
- Fonte da verdade de produção continua sendo a VPS `/opt/ejc`; deploy = upload + `docker compose build` + `up -d --no-deps` (containers rodam código embutido na imagem).

---

## 1. INVENTÁRIO FRONTEND

### 1.1 Números
- **73 páginas** em `src/pages` (67 + 6 do portal) + ramos dinâmicos; 57/62 rotas com lazy loading.
- **Rotas** definidas em `src/App.tsx` (330 linhas): públicas (`/login`, `/recuperar-senha`, `/redefinir-senha`), portal do cliente (`/portal/*`, 6 rotas, layout próprio `PortalLayout`), sistema interno (StaffOnly + `Layout` com 43 itens de menu em 7 grupos) e 5 redirects legados (`/ambiental`→`/ramos/ambiental`, `/data-room`→`/documentos`, `/dashboard-executivo`→`/`, `/financeiro-dashboard`→`/financeiro`, `/whatsapp`→`/`).
- RBAC no roteamento via guards `RoleOnly` (ex.: `/honorarios` restrito a superadmin/admin/socio/advogado/financeiro; `/usuarios` a superadmin/admin).

### 1.2 Design system atual (working tree — Fase 3)
- **Tokens** (`tailwind.config.js`): `primary-*` bronze (#8C6A33 DEFAULT, escala 50–950), `ai-*` petróleo (#266761), `sidebar-*` slate (#0F172A), `gold`/`bronze` auxiliares, status `success/warn/danger/info` no padrão Tailwind, semânticas `canvas/ink/muted/border/parchment`.
- **Tipografia**: DM Sans (sans) + Cormorant Garamond (serif), escala customizada 2xs→4xl. **Falta**: papel definido para display vs heading vs body vs caption e uma fonte mono para dados processuais.
- **Componentes** (`src/components/UI.tsx`, ~500 linhas): Button (primary/secondary/ghost/danger/ai), Badge/StatusBadge/PriorityBadge, Card/SectionCard/StatCard, PageHeader, FilterBar, SearchBar, FieldLabel/Input/Select/Textarea, Spinner, Empty, Tooltip, fmtDate/fmtCurrency/fmtPhone. `Toast.tsx` (CustomEvent + auto-dismiss). `CommandPalette.tsx` (Ctrl+K).
- **Render de IA**: `components/Markdown.tsx` (206 linhas, parser seguro sem `dangerouslySetInnerHTML`, preserva operadores) + `components/ai/AIResponse.tsx` (wrapper com badge de confiança e aviso OAB Prov. 205/2021). Usados em 9 páginas de IA.
- **Tema**: dark mode via classe (`useTheme`), toggle no Layout.

### 1.3 Problemas encontrados (frontend)
| # | Problema | Arquivo | Gravidade |
|---|----------|---------|-----------|
| F1 | `dangerouslySetInnerHTML` sem sanitização (risco XSS) | `src/pages/MemoriaInstitucional.tsx` | **Alta** |
| F2 | Componente experimental não roteado (candidato a remoção segura) | `src/components/DashboardModernLuxury.tsx` + `Dashboard_light_backup.tsx` e `Workflow.tsx.bak` na raiz do repo | Média |
| F3 | Tipografia sem escala formal (display/heading/body/caption/mono) | `tailwind.config.js` | Média |
| F4 | Ajuda 100% hardcoded em TSX (Ajuda.tsx, 882 linhas) — sem botão "?" contextual por tela, sem conteúdo estruturado atualizável | `src/pages/Ajuda.tsx` | Média |
| F5 | 4+ superfícies distintas de IA (`/ia`, `/assistente-ia`, `/inteligencia`, `/ferramentas-ia`) — funcionais, mas navegação confusa | App.tsx | Baixa |
| F6 | Sem Storybook/catálogo do design system | — | Baixa |

### 1.4 Responsividade
- Mobile-first presente: sidebar com hamburger + overlay (`md:hidden`), grids `grid-cols-1 sm:2 md:3`, padrão consistente nas 10 páginas principais (CasoDetalhe 13 breakpoints, Conhecimento 10, Casos 8…). Nenhuma página sem breakpoints. **Pendência**: teste real em 375px/768px de tabelas densas (Casos, Honorarios, Prazos) e modais — Fase 6.

---

## 2. INVENTÁRIO BACKEND

### 2.1 Números
- **534 endpoints** em **108 arquivos de router** (`app/routers`), FastAPI async + SQLAlchemy 2.0.
- Principais: `ramos.py` (63 endpoints, 10 ramos), `cases.py` (15), `ai.py` (15), `clients.py` (11), `legal_docs.py` (10), `teses.py` (10), `rag.py` (10), `atendimentos.py` (9), `auth.py` (9), `documents.py` (8), `workflow.py` (7), `diario_oficial.py` (6), `deadlines.py` (6), `portal.py` (6), `intimacoes.py` (3), `datajud.py` (2), `honorarios_oab.py` (2), `trash.py` (2).

### 2.2 Serviços-chave (fundação para o redesign)
- **IA**: `ai_gateway.py` (ponto único, TASK_ROUTING 8 tipos, Ollama local→Groq fallback), `ai_service.py` (pipeline LGPD completo: sanitizar_pii → validar_sem_pii → RAG fail-closed → gateway → AILog HITL), `sanitizer.py` (CPF/CNPJ/CNJ/RG/e-mail/telefone/CEP/cartão/PIX), `citation_check.py` (anti-alucinação de citações).
- **Documentos**: `ocr_service.py` (PyMuPDF, Tesseract pt, python-docx, TXT, limite 200K chars), `documento_service.py` (`extrair_e_analisar()`: OCR → IA estruturada → JSON com partes/CPF/área/valor/estratégia → honorários via RAG da tabela OAB).
- **Prazos**: `deadline_calculator.py` (dias úteis, feriados móveis, prescrição) + `calc/` (custas TJMG, trabalhista, tributário).
- **Integrações**: `datajud_service.py`, `djen_service.py`, `diario_oficial_service.py`, ingestors STJ/Câmara/Senado/Planalto.
- **Agendamento**: `scheduler.py` (APScheduler: morning brief 07h, alertas de prazo 07h15, honorários 08h, ambientais 08h30, procurações seg 09h; guard `ENABLE_SCHEDULER`).
- **Notificações**: `notification_service.py` multi-canal — interna (sino), e-mail SMTP, Web Push VAPID, WhatsApp (Z-API/Evolution). *(Nota: o gap analysis R12 apontou "e-mail ausente" olhando só os routers; o serviço de e-mail EXISTE em `notification_service.py` — a lacuna real é de GATILHOS automáticos e preferências por usuário.)*
- **Export**: `pdf_service.py` (weasyprint+Jinja2, Visual Law), `export.py`; `python-docx` instalado mas **não usado para gerar DOCX** (peças ficam em markdown/texto).

### 2.3 Segurança/permissões
- RBAC de 9 papéis (`core/security.py`): superadmin(9) → admin(8) → socio(7) → advogado(6) → advogado_auxiliar(5) → financeiro(4) → estagiario(3) → secretaria(2) → cliente_externo(1), com matriz de permissões explícita por papel.
- ABAC: `core/ownership.py` → `verificar_acesso_caso()` (gestão passa; equipe só se responsável/auxiliar; salvaguarda anti-lockout) aplicado em documents/legal_docs/ramos/case_partes.
- JWT access 8h + refresh 30d com JTI revogável; portal do cliente isolado por middleware + client_id do token.
- Sanitização PII confirmada em `teses.py` (correção da auditoria de 2026-07-02 aplicada).

### 2.4 Problemas encontrados (backend)
| # | Problema | Detalhe | Gravidade |
|---|----------|---------|-----------|
| B1 | ~~Colisão de prefixo `/ai`~~ **[REVISADO 07-03 + CORRIGIDO]** | Análise de precisão (path a path) mostrou que NÃO havia colisão método+path. O problema real: **`ia_extra.py` era ÓRFÃO** (não registrado no main.py) → 5 endpoints chamados pelo frontend em 404 na produção (`/ai/gerar-minuta`, `/ai/resumir-texto`, `/ai/traduzir-andamento`, `/ai/pesquisar`, `/ai/sugestao-honorarios`). **Corrigido: registrado no main.py** (verificado: zero sobreposição de paths com ai.py) | **Alta → resolvida** |
| B2 | ~~Colisões adicionais~~ **[REVISADO 07-03]** | `/analytics`, `/webhooks`, `/teses` (v4 usa prefixo `/teses-v4`) e jurimetria ×2: **sem colisão real** — paths distintos, ambos registrados. **`honorarios_oab.py` era ÓRFÃO** → `/honorarios-oab/estimar` (usado por EstimadorHonorarios.tsx) em 404. **Corrigido: registrado no main.py.** Fantasma no frontend: `GET /teses/busca-avancada` é chamado mas não existe no backend (tratar na Fase 4) | **Alta → resolvida** |
| B3 | Routers órfãos **[REVISADO 07-03]** | Lista real de órfãos é bem menor que a estimativa inicial (~20-30): além dos 2 corrigidos acima, só **`assistente.py`** segue órfão (frontend não o chama — morto, sem ação). Os demais suspeitos (ia_saude, ia_defensiva, ia_governanca, ia_especializada, jurimetria_extra etc.) **estão registrados** no main.py | Baixa |
| B4 | Fila assíncrona não persistente | Upload usa `BackgroundTasks` do FastAPI — perde tarefa se o processo reiniciar; sem Celery/Redis no requirements | Média |
| B5 | `Document.tipo` é String livre (não enum), 6 valores informais | `app/models/document.py` | Média |
| B6 | Auditoria de `Depends(get_current_user)` em 100% dos routers pendente | — | Média |

---

## 3. INVENTÁRIO BANCO DE DADOS

- **42+ modelos**; head Alembic **`056_processes_is_principal`** (cadeia única 001→056, migrações idempotentes).
- Núcleo: User (9 roles, TOTP), Client (status inclui `arquivado`), **Case (status inclui `arquivado`** + `deleted_at` soft delete + resultado/lições aprendidas), Document (5 níveis de confidencialidade + `ocr_text`), Deadline (alertas 7/3/1d), Fee/FeePayment, LegalDoc (**HITL obrigatório**: `ai_generated` + `human_reviewed` bloqueiam aprovação), Tese (taxa_sucesso, N:N com casos), JurisprudenciaInterna.
- Especializados 1-1 por ramo: Environmental/Empresarial/Civel/Penal/Trabalhista/Admin/BancarioCase.
- **Workflow BPM configurável JÁ EXISTE** (migração 052): `workflow_templates` (area_juridica, is_default) → `workflow_etapas` (ordem, `sla_dias_uteis`, `acao_automatica`) → `case_workflows` → `workflow_historico`.
- Checklists configuráveis: `checklist_templates` (por área, 8 templates seeded) → `case_checklists` → itens.
- Diário Oficial: `diario_oficial_keywords` (keyword, fonte, case_id) + `diario_oficial_alertas` (lido). DJEN: `djen_comunicacoes`.
- RAG: `knowledge_docs` (**isolamento client_id/case_id** — migração 055) → `knowledge_chunks` (pgvector **768d**, HNSW, multilingual-e5-base).
- Auditoria: `audit_logs` **imutável** (ação/entidade/registro/dados_antes/depois/user/ip — LGPD art. 37); `ai_logs` (prompt_sanitizado, pii_removida, fontes_rag, tokens, status_hitl, revisado_por). Soft delete (`deleted_at`) em todas as entidades núcleo + lixeira com restauração (`trash.py`).

### Tabelas AUSENTES (a criar no redesign)
| Tabela | Para | Seção do prompt |
|--------|------|-----------------|
| `module_help` (module_key, section, titulo, conteudo_md, ordem) | Ajuda contextual atualizável sem redeploy | §3 |
| `area_modulos_mapping` (area, module_key, habilitado, ordem, ferramentas_json) | Matriz área→módulos configurável | §8 |
| `document_types_master` (tipo_key, descricao, categoria, campos_extracao_json) | 14+ tipos de documento com campos específicos | §5 |
| `tabela_oab_honorarios` (item, area, valor_min, vigencia, fonte) | Referência OAB/MG versionada e atualizável (hoje só em seeds/RAG) | §7 |

---

## 4. GAP ANALYSIS — REQUISITOS DO REDESIGN (R1–R12)

| Req | Descrição | Status | O que falta (essencial) |
|-----|-----------|--------|--------------------------|
| R1 | Manual interativo por módulo | **JÁ EXISTE ~80%** (Ajuda.tsx com 28 tutoriais + busca; OnboardingTour 7 slides) | Botão "?" contextual por tela vinculado à rota; conteúdo em `module_help` (hoje hardcoded) |
| R2 | Arquivar/excluir caso | **PARCIAL** (status `arquivado` no enum; soft delete + lixeira + restauração + audit log; restrito admin/socio) | Modal com digitação de confirmação; **bloqueio condicional** (prazo ativo, honorário aberto, peça protocolada → só arquivar); motivo no audit log |
| R3 | Import/classificação de documentos | **PARCIAL** (upload PDF/DOCX/imagens + OCR + análise IA em `ImportarDocumento.tsx` + `documento_service`) | 14 tipos específicos (multas, NF-e XML, edital, denúncia, B.O., laudo…); sugestão de tipo por IA com confirmação humana; suporte XML; fila persistente |
| R4 | Extração com origem+confiança | **PARCIAL** (JSON estruturado completo: partes, CPF/CNPJ, datas, valores, área, brechas) | Trecho de origem por campo; score de confiança por campo; UI de revisão lado-a-lado antes de gravar |
| R5 | Motor IA (área+teses+estratégia+OAB) | **PARCIAL** (todos os blocos existem: classificação de área, `/teses` com busca semântica, `_sugerir_honorarios()` via RAG da tabela OAB, AILog+HITL) | Orquestração automática no intake (extração→teses→estratégia→valor OAB em um fluxo); tabela OAB gerenciável |
| R6 | Matriz área→módulos | **PARCIAL** (16 ramos no RamosHub + 63 endpoints em ramos.py) | Tudo hardcoded — criar `area_modulos_mapping` + UI de configuração |
| R7 | Export DOCX + impressão | **PARCIAL** (PDF via weasyprint OK; `@media print` existe; python-docx instalado) | Endpoint de export DOCX real com modelo institucional; views de impressão auditadas |
| R8 | Checklist de conversão caso→processo | **PARCIAL** (checklists por área existem; `conflito_service.py` com classificação SEM_CONFLITO/ALERTA/CONFLITO_GRAVE; `linked_judicial_case_id`) | Checklist específico de conversão com **bloqueio** (422 + itens pendentes); UI de resultado/pós-mortem |
| R9 | Workflow por área | **PARCIAL** (framework BPM completo com SLA e histórico) | Auto-aplicação de template por área do caso; scheduler de SLA (atrasado + alerta); visualização timeline/kanban |
| R10 | Diário Oficial/DJEN/DataJud | **PARCIAL** (keywords+alertas DO; captura DJEN por OAB; sync DataJud por CNJ) | Job agendado documentado, vinculação automática publicação→caso por nº CNJ, criação assistida de prazo, notificação push/e-mail no alerta |
| R11 | Saída de IA limpa | **JÁ EXISTE** (Markdown.tsx seguro + AIResponse em todas as 9 superfícies de IA) | Só corrigir F1 (MemoriaInstitucional.tsx) e regra eslint anti-`dangerouslySetInnerHTML` |
| R12 | Notificações | **PARCIAL** (in-app + push VAPID + e-mail SMTP + WhatsApp em `notification_service.py`; scheduler dispara prazos/honorários) | Gatilhos por evento (D.O., revisão, intimação); preferências por usuário |

**Conclusão da análise:** nenhum requisito parte do zero. O redesign é majoritariamente **fiação + consolidação + UI**, não construção nova — o que reduz drasticamente o risco de regressão.

---

## 5. LISTA CONSOLIDADA DE PROBLEMAS (por criticidade)

**Críticos:**
1. ✅ **RESOLVIDO (07-03)** — B1/B2: routers órfãos `ia_extra.py` e `honorarios_oab.py` registrados no main.py (6 endpoints do frontend saíram de 404). Não havia colisões reais de path.
2. F1 — XSS via `dangerouslySetInnerHTML` em MemoriaInstitucional.tsx (em correção na Fase 2).
3. ✅ **RESOLVIDO (07-03)** — Fase 3 visual commitada na branch `ui/fase-3-tokens` (b918932).

**Altos:**
4. B3 (revisado) — único órfão remanescente é `assistente.py` (morto, frontend não chama — sem ação). Fantasma no frontend: `GET /teses/busca-avancada` chamado sem endpoint correspondente (Fase 4).
5. R2 — exclusão de caso sem bloqueios condicionais nem confirmação forte.
6. B4 — pipeline de documentos sem fila persistente.

**Médios:** B5 (Document.tipo string livre), F3 (escala tipográfica), F4 (ajuda hardcoded), R6 (matriz hardcoded), R7 (DOCX ausente), B6 (auditoria de auth em 100% dos routers).

**Baixos:** F2 (componentes .bak/experimentais), F5 (navegação de IA fragmentada), F6 (sem catálogo de componentes).

---

## 6. PLANO DE FASES (sequencial, com checkpoint por fase)

1. **Fase 2 — Design system**: commitar Fase 3; escala tipográfica (display/heading/body/caption/mono); padronizar Table/Modal/Alert/EmptyState/LoadingState em UI.tsx; corrigir F1; `docs/design-system.md`.
2. **Fase 3 — Módulos funcionais**: correção B1/B2 (colisões) primeiro; ajuda contextual (`module_help` + botão "?" por rota); arquivar/excluir caso com bloqueios; tipos de documento + sugestão IA com confirmação; extração com origem/confiança + UI de revisão.
3. **Fase 4 — Motor IA e configurabilidade**: orquestração de intake (extração→teses→estratégia→OAB, tudo rascunho+AILog); `area_modulos_mapping`; checklist bloqueante de conversão; auto-workflow por área + SLA scheduler.
4. **Fase 5 — Export e Diário Oficial**: DOCX institucional + views de impressão; vinculação automática D.O./DJEN→caso + alertas via notification_service.
5. **Fase 6 — Auditoria final**: rotas testadas, responsividade 375/768/1280, relatório de entregáveis (Seção 14 do prompt).

*Routers órfãos (B3): tratados transversalmente — nenhum será deletado; os que forem consolidados serão registrados na lista de alterações do relatório final.*
