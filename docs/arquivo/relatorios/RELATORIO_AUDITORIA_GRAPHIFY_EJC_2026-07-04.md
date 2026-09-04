# RELATÓRIO DE AUDITORIA GRAPHIFY — EJC (2026-07-04)

**Método:** grafo de dependências e chamadas (5 fases: extração determinística → grafo com métricas → análise estrutural → caça a bugs guiada por risco → reorganização).
**Stack:** mista — backend FastAPI (314 módulos) + frontend React/TS (128 módulos) + camada de integração HTTP (259 arestas front→back).

## Resumo executivo

1. Grafo consolidado: **442 nós, 1.767 arestas, 0 ciclos de import** (backend e frontend acíclicos — arquitetura sã na base).
2. **22 achados confirmados** com evidência arquivo:linha — 2 críticos (IDOR destrutivo no Drive; CPF/CNPJ exposto a qualquer autenticado), 13 altos, 5 médios, 2 baixos.
3. Padrão-raiz de 8 dos bugs: **docstrings anunciam `/api/v1/...` mas os prefixes reais não têm `/v1`** — o frontend foi escrito seguindo as docstrings e recebia 404 silencioso (`catch {}`).
4. Router `module_help` era chamado pelo frontend e **nunca foi montado** em `main.py` (404 em produção).
5. Jurimetria acumulava estatísticas **sistematicamente erradas** (vocabulário de `resultado` divergente entre router e serviço).
6. **Todas as correções foram aplicadas nesta branch** (ver §6) — backend: 112 testes passando; frontend: tsc limpo.
7. Cobertura de testes: **nenhum relatório existe no repo** (sem `.coverage`/`htmlcov`/`coverage/`) — o fator cobertura do índice de risco foi neutralizado (1.0) e está declarado como N/D em todos os nós.
8. Entregáveis: este relatório, `auditoria-grafo/grafo-dados.json` (reuso/comparação futura) e `auditoria-grafo/grafo-interativo.html` (D3 force-directed, tema escuro, busca, filtros, export PNG/SVG — validado em Chromium headless).

---

## 1. Fase 1 — Extração (ferramentas determinísticas)

| Fonte | Ferramenta | Resultado |
|---|---|---|
| Imports backend | AST Python (`ast`), imports top-level + lazy | 313 módulos, 1.143 arestas |
| Complexidade | `radon cc` (API) | Σcc e max_cc por módulo |
| Código morto backend | `vulture --min-confidence 90` | 7 itens (§3.5) |
| Grafo frontend | `madge --json --extensions ts,tsx` | 128 módulos; `--circular`: **0 ciclos** |
| Exports mortos frontend | `ts-prune` | 36 exports não usados |
| Rotas backend | AST (`APIRouter(prefix)` + decorators) | 578 rotas |
| Chamadas HTTP frontend | regex `api|axios.(get|post|…)` sobre fonte | 271 chamadas → 259 casadas, 12 investigadas |
| Histórico | `git log --name-only` (um passe) | `last_modified` + `commit_count` por nó |
| Cobertura | — | **indisponível** (sem relatório no repo; não simulada) |

Incidente de extração: `app/services/peca_service.py` tinha **BOM U+FEFF** no byte 0 (falha de parse no AST; benigno em runtime, corrigido).

## 2. Fase 2 — Grafo e métricas

Índice de risco composto: `cc × ln(fan_in+1) / log10(dias_desde_última_modificação+10)` (fator cobertura = 1.0, N/D).
Bandas de severidade por percentil do próprio repo: crítico ≥ p95 (73.2), alto ≥ p85 (27.2), médio ≥ p60 (6.0).

**Top 10 risco:** `routers/cases` (387) · `services/ai_service` (229) · `routers/clients` (194) · `routers/ai` (167) · `routers/documents` (152) · `services/ai_gateway` (151) · `routers/teses` (145) · `routers/legal_docs` (138) · `routers/ia_governanca` (129) · `routers/rag` (117).

**Pontos de estrangulamento (betweenness):** `ai_service` > `ai_gateway` > `routers/cases` > `case_context` > `front.App`. Falha em `ai_gateway` (fan-in 26) derruba toda a superfície de IA.

## 3. Fase 3 — Análise estrutural

### 3.1 Ciclos
**Nenhum** (backend e frontend). Sem risco de import circular/`undefined` em runtime.

### 3.2 God modules (acoplamento ≥ p92 do próprio repo)
Backend: `core/database` (157), `models/user` (122), `core/security` (121), `main` (119 fan-out), `models/case` (47), `routers/cases` (40, fan-out 31 — o único "god" com lógica pesada), `ai_gateway` (33). Os quatro primeiros são *hubs de infraestrutura* — fan-in alto esperado; o alvo de refator é `routers/cases` (1.118 loc, cc=175).
Frontend: `lib/api` (81), `App` (74 fan-out), `components/UI` (71 fan-in, 1.018 loc), `pages/CasoDetalhe` (4.196 loc, 27 imports).

### 3.3 Violações de camada (3)
- `services/scheduler → routers/dashboard` (domain→api) — job importa lógica de router em vez de serviço.
- `core/rate_limit → services/security_service` (infra→domain).
- `scripts/seed_renomados → services/rag_juridico` (aceitável para seed; registrado).

### 3.4 Routers não montados (fan-in=0 em `main.py`)
- `routers/module_help.py` (149 loc) — **chamado pelo front** (`HelpButton.tsx:82,103`) → 404. **Corrigido: montado.**
- `routers/area_modulos.py` (197 loc) e `routers/assistente.py` (113 loc) — nenhuma chamada no front: **código morto** (candidatos a remoção em etapa própria).

### 3.5 Código morto / órfãos
- Backend (vulture ≥90%): imports não usados em `indice_risco.py:10`, `intelligence_v3.py:9`, `jurisprudencia_externa.py:19`; variáveis mortas em `elite_tools.py:9,17`, `google_drive.py:60`, `minerador_sucesso.py:32`.
- Backend órfãos (fan-in=0, amostra): `services/motor_estrategico`, `elite_tools`, `crawler_precedentes`, `gatilhos_estruturais`, `geracao_documental`, `relatorio_visual_law`, `honorarios_oab`, `embeddings_api`, `system_prompts/*` (parcial).
- Frontend órfãos (madge fan-in=0): `DashboardModernLuxury`, `PortalClientePlatinum`, `MarketIntelligencePanel`, `WhatsAppChatbot`, `EscritaAssistida`, `FocusToday` (~830 loc). *Hipótese a validar antes de remover: import dinâmico/uso futuro — a sessão de confirmação individual foi interrompida.*
- `ramosConfig.ts`: exports `RAMOS_LISTA` e `RAMOS_LISTA_FINAL` sem uso externo (ts-prune) — verificar qual é o vivo antes de qualquer remoção.

## 4. Fase 4 — Achados (evidência rastreável)

### CRÍTICOS

**C1 — IDOR + exclusão destrutiva sem ownership (Google Drive)** — `backend/app/routers/documents.py:659-676`
`gd.delete_file(file_id)` executava antes de qualquer checagem; o filtro `uploaded_by` só protegia a linha do banco. Qualquer autenticado (inclusive `cliente_externo`) destruía arquivo alheio no Drive, com `except: pass` engolindo falhas. **Corrigido:** gate `_gate_drive_doc` antes do delete + audit log + warning logado.

**C2 — CPF/CNPJ de todos os clientes expostos a qualquer autenticado** — `backend/app/routers/clients.py:296-324, 389-400`
`GET /clients/` e `GET /clients/{id}` sem gate de role — cliente do portal listava a carteira inteira com PII em claro (violação LGPD + IDOR horizontal). **Corrigido:** dependência `_req_clientes_leitura` bloqueia `cliente_externo`.

### ALTOS

**A1..A8 — Contratos HTTP quebrados (404 em produção)** — padrão-raiz: docstring `/api/v1/...` ≠ prefix real. Confirmados nas duas pontas:
| Front (arquivo:linha) | Chamava | Rota real |
|---|---|---|
| `AnaliseExtratos.tsx:78,91,104` | `/v1/bank-analysis/*` (3) | `/bank-analysis/*` (`bank_analysis.py:37,160,177`) |
| `CasoDetalhe.tsx:146` | `/extratos/casos/{id}` | `/extratos/detalhado/{id}` (`extratos.py:18`); 404 engolido por `catch {}` |
| `FinanceiroDashboard.tsx:88,103` | `/v1/financeiro/consolidado`, `/v1/relatorio/mensal` | sem `/v1` (`financeiro_consolidado.py:21`, `relatorio.py:21`) |
| `Honorarios.tsx:86,99` | `/v1/honorarios-exito/{id}/rateio` | sem `/v1` (`exito_rateio.py:79,90`) — fluxo de rateio inteiro quebrado |
| `Sociedade.tsx:209` | `PATCH .../{id}/reject` | **não existia** (só approve/pay em `partner_withdrawals.py:85,109`) |
**Corrigidos:** paths do front alinhados; endpoint `reject` criado no backend; `module_help` montado (A9, `HelpButton.tsx:82` → 404).

**A10 — IDOR em `POST /cases/{id}/gerar-documentos`** — `cases.py:492-507`: único endpoint de caso sem `_filtro_visibilidade`. **Corrigido.**

**A11 — IDOR em `traduzir_andamento`** — `cases.py:736` + `movimento_ia.py:40`: `mov_id` de caso alheio era processado e persistido. **Corrigido:** vínculo `CaseMovimento.case_id == case_id` (404 caso contrário).

**A12 — Jurimetria corrompida** — `case_intel.py:179,198` vs `cases.py:643`: router emite `exito|derrota|…`; serviço esperava `exito_total`/`improcedente` → vitórias e derrotas nunca contabilizadas (`taxa_sucesso=None`). **Corrigido:** vocabulário unificado + `pattern` no schema (422 para valor livre) + aliases históricos.

**A13 — Race condition na numeração `DPT-AAAA-NNNN`** — `cases.py:40-50`: SELECT-max→INSERT sem lock (duplicata em criação concorrente) e ordenação lexicográfica quebra no caso 10000. **Corrigido:** `pg_advisory_xact_lock` + `CAST(substring(...) AS INTEGER)`.

**A14 — `ia_analise_cliente` sem gate/sanitização/log** — `clients.py:402-429`: `cliente_externo` podia disparar IA sobre qualquer cliente, com PII sem `sanitizar_pii` e sem AILog. **Corrigido:** `_req_clientes` + `deleted_at` + sanitização.

**A15 — PATCH de cliente dessincronizava índice cego LGPD** — `clients.py:444`: `cpf`/`cnpj` alterados sem regravar `*_enc`/`*_hash` → checagem de conflito (EOAB 34-35) com falso negativo. **Corrigido:** revalidação de dígito + regravação de enc/hash (e `ClientUpdate` ganhou os campos).

### MÉDIOS

**M1 — Notificações duplicadas em falha parcial** — `scheduler.py:161-193, 476-527`: e-mail/WhatsApp enviados no loop com commit único no fim → falha na linha N reenviava tudo no dia seguinte. **Corrigido:** commit por item + try/except por destinatário.

**M2 — `NameError` latente em `_verificar_sincronia_datajud`** — `scheduler.py:742`: `datetime` não importado (mascarado pelo `except Exception`). **Corrigido** (+ `timezone.utc`).

**M3 — Commit prematuro da sessão do request** — `ai_gateway.py:312-324`: `_registrar_ai_log` commitava a sessão do handler (fan-in 26 — persistência parcial em rollback posterior). **Corrigido:** sessão própria (`AsyncSessionLocal`).

**M4 — BOM U+FEFF** — `peca_service.py:1`. **Corrigido.**

**M5 — Higiene observada (não corrigida nesta rodada; baixo risco):** `documents.py:448` (`remover`) não checa o gate de confidencialidade que o download exige; `cases.py:1057` usa `Body(default={})` sem schema; `scheduler.py:729` monta `pg_dump` com `shell=True` interpolando `DATABASE_URL_SYNC` (função não agendada).

### BAIXOS

**B1 — Job duplicado** — `scheduler.py:875,887`: `_purgar_logs_ia` agendado 2×. **Corrigido** (mantido `purga_ia`).
**B2 — Routers mortos** — `area_modulos.py`, `assistente.py` (nenhum consumidor). Mantidos; remoção sugerida no plano (§5).

## 5. Fase 5 — Plano de reorganização incremental (cada passo mantém o sistema funcional)

**Etapa 0 (feita nesta branch):** correções de segurança/contratos acima — pré-requisito de qualquer refactor.

**Etapa 1 — Contrato de API como fonte única (1-2 dias).** Gerar client TS a partir do OpenAPI do FastAPI (`openapi-typescript`) e substituir paths hardcoded gradualmente (página a página). Elimina a classe inteira de bug A1-A9. *Rollback:* client gerado convive com axios manual; reverter é trocar import.

**Etapa 2 — Quebra de `routers/cases.py` (1.118 loc, cc=175) (2-3 dias).** Extrair por responsabilidade: `cases_crud.py` (CRUD+visibilidade), `cases_documentos.py` (gerar-documentos/uploads), `cases_movimentos.py` (andamentos/traduzir), `cases_encerramento.py` (encerrar+jurimetria). Agregador `cases/__init__.py` reexporta o router — `main.py` não muda. *Rollback:* commit único por sub-router; reverter arquivo a arquivo. *Regressão obrigatória:* suite pytest atual (112) + smoke de rotas (`test_app_monta_com_rotas`).

**Etapa 3 — Eliminar violação domain→api (0,5 dia).** Mover a lógica usada por `scheduler` de `routers/dashboard` para um `services/dashboard_service.py`; router e scheduler passam a consumir o serviço. *Rollback:* trivial (re-import).

**Etapa 4 — Poda de código morto (1 dia, uma remoção por commit).** Ordem: imports/vars do vulture → `area_modulos.py`/`assistente.py` → órfãos frontend (após confirmar ausência de import dinâmico com `grep -r "lazy\|import("` por nome) → decidir `RAMOS_LISTA` vs `RAMOS_LISTA_FINAL`. *Rollback:* revert do commit específico.

**Etapa 5 — Cobertura visível (contínuo).** Ativar `pytest --cov` no CI e publicar o XML no repo; recalcular o índice de risco com o fator cobertura real (o JSON exportado aceita `coverage_pct` por nó).

**Etapa 6 — `CasoDetalhe.tsx` (4.196 loc) (3-4 dias).** Extrair abas para componentes por domínio (`caso/AbaResumo.tsx`, `AbaMovimentos.tsx`, …) mantendo o estado no pai; uma aba por PR. *Regressão:* navegação entre abas + fluxos de intimação/teses recém-criados.

## 6. Correções aplicadas nesta branch (verificação)

- Backend: 10 arquivos corrigidos; `python -m py_compile` limpo; **`pytest`: 112 passed, 8 skipped**.
- Frontend: rotas 404 corrigidas + redesign (design system); `tsc --noEmit` exit 0 (ver PR).
- Nenhuma migration necessária (sem mudança de schema).

## 7. Checklist de validação pós-refatoração

- [ ] `pytest backend/tests -q` verde (inclui `test_app_monta_com_rotas` e cadeia Alembic).
- [ ] `tsc --noEmit` exit 0.
- [ ] Smoke manual: login → Casos → CasoDetalhe (abas) → Documentos (upload/download/delete com usuário sem ownership deve dar 403) → Honorários (rateio) → Financeiro (consolidado/relatório) → Sociedade (approve/reject) → Análise de extratos (upload/excel/documento) → botão de ajuda (module-help).
- [ ] `GET /clients` com token de `cliente_externo` deve retornar 403.
- [ ] Encerrar caso com `resultado="qualquer"` deve retornar 422; com `exito` deve incrementar jurimetria.
- [ ] Criar 2 casos em paralelo → números internos distintos.
- [ ] Jobs: forçar exceção em um destinatário da régua → demais seguem, sem reenvio no dia seguinte.
- [ ] `graphify update .` + re-extração do grafo (`auditoria-grafo/grafo-dados.json`) para comparar evolução de acoplamento/risco.

---
*Evidências completas por achado (trechos literais) nos registros da auditoria; grafo navegável em `auditoria-grafo/grafo-interativo.html` (abra no navegador — busca, filtros por camada/risco, painel de métricas por nó, export PNG/SVG).*
