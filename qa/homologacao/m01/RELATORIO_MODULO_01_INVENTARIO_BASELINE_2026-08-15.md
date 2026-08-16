# EJC — Módulo 01: Inventário e Baseline Técnico

**Data da execução:** 15/08/2026 (22:32 UTC)
**Repositório:** s2corporativo/ejc
**Status do módulo:** HOMOLOGADO (baseline registrada; sem correção destrutiva necessária)

---

## 1. Baseline do repositório

| Item | Valor verificado |
|---|---|
| Branch | `main` (working tree limpo, sem alterações locais) |
| Commit HEAD | `89daf7b221e0e7da938726b39164e9ea9203f46d` |
| Data do HEAD | 2026-08-15 22:29 UTC |
| Mensagem do HEAD | fix(dpt360): dashboard reutiliza índice de empresas/áreas no radar (DER-01 #1084) (#1156) |
| Total de commits | 2.352 |
| Tags | nenhuma tag versionada |
| Issues abertas | 15 (incl. #1150 Auditoria IA integral, #1147 Auditoria pós-Manus, #1126/#1131 CI fallback, #1077 phantom save societária) |
| PRs abertos | 4 (todos DRAFT/open recentes de auditoria) |

## 2. Estrutura física confirmada

| Camada | Localização | Volume |
|---|---|---|
| Backend | `backend/app/` | main.py (594 linhas) |
| Routers | `backend/app/routers/` | **155 módulos** de rota ativos |
| Routers mortos | `backend/app/routers/_dead_code/` | 7 módulos |
| Models | `backend/app/models/` | 68 módulos de model |
| Services | `backend/app/services/` | 168 módulos de serviço (+ subpacotes `ai/`, `ambiental/`, `calc/`, `conhecimento_ingest/`, `ingestors/`, `juris_import/`, `nfse/`, `observability/`, `providers/`, `system_prompts/`) |
| Core | `backend/app/core/` | 26 módulos (auth_middleware, rate_limit, ownership, client_ownership, log_sanitizer, celery_app, celery dispatcher, ai_brain, veredito_ia etc.) |
| Integrations | `backend/app/integrations/` | DataJud, DJEN, BrasilAPI, IBGE, TCU, CNJ-SGT, IDE-Sisema, Infosimples, Querido Diário, PGFN, CKAN |
| Tasks (Celery) | `backend/app/tasks/` | dispatcher, rag_tasks, rescan_tasks, processo_eletronico_tasks, raio_x_tasks, vault_sync |
| Frontend | `frontend/src/` | **103 páginas** + 104 arquivos de teste frontend |
| Stores | `frontend/src/stores/` | auth, cadastroManual, caseContext, moduleLifecycle, preferences, theme (6) |
| Migrations | `backend/alembic/versions/` | **136 versões** (001 a ~144) |
| Tests backend | `backend/tests/` | **487 arquivos** (+ `_dead_code`, fixtures, snapshots) |
| Tests frontend | `frontend/` | 104 arquivos `.test.*` |
| Docker | `docker-compose.yml` | 8 serviços: db (PostgreSQL 16/pgvector), redis, backend, worker, frontend (nginx 1.27-alpine), langfuse-db, langfuse, ollama (+ ollama-init) |
| Config | `.env.example` | 783 linhas de variáveis |
| CI | `.github/workflows/` | 17 workflows (ci.yml com PostgreSQL efêmero porta 55432 isolada de produção, release-gate, frontend-ci, governança, backup-monitor, probe-apis etc.) |
| QA/Homologação | `qa/homologacao/`, `qa/e2e/`, `qa/evidencias/` | matriz homologação H01–H15, certificador de release |
| Docs | `docs/` | 50+ documentos (ARQUITETURA_ATUAL, MAPA_DE_MODULOS, MATRIZ_DE_ROTAS, CATALOGO_APIS_EJC, RUNBOOKS, ADRs, RELATÓRIOS de auditorias anteriores) |

## 3. Cruzamento frontend ↔ API ↔ service ↔ model ↔ migration ↔ testes

### 3.1 Registro de rotas backend
- `main.py` contém **155 `include_router`** correspondendo 1:1 aos 155 módulos de router ativos.
- 5 módulos de router existem mas **não são importados diretamente no main.py** porque são anexados ao router `novos_modulos` dentro de `backend/app/routers/__init__.py` (mecanismo declarativo intencional e documentado nos comentários do próprio `__init__.py`): `defesas_revisoes`, `defesas_revisoes_avancado`, `defesas_revisoes_pacote_seguro`, `entrada_universal`, `entrada_universal_vinculo`. **Não são órfãos reais.**
- Alias `api_keys_router` (import `from app.routers import api_keys as api_keys_router`) — verificado correto, linha 150.
- **Prefixos duplicados (potenciais colisões de rota):** `/system-modules` (module_settings + system_modules), `/entrada-universal` (entrada_universal + entrada_universal_vinculo), `/ia-governanca` (ia_provider_metrics + ia_governanca), `/clients` (clients + pending_items), `/ia` (ia_adversarial, ia_saude, ia_citacoes, ia_agente), `/cases` (cases + kit_documental), `/analytics` (produtividade + analytics), `/portal` (portal + portal_documentos), `/ai` (ai + ai_tools). Na maioria dos casos o FastAPI mescla rotas do mesmo prefixo em routers distintos sem conflito de caminho, mas o padrão indica **fragmentação modular alta** que merece consolidação futura.

### 3.2 Rotas de mesmo caminho em routers diferentes (verificação grosseira, ignorando prefixo)
Diversos caminhos coincidem entre routers (`/`, `/analisar`, `/buscar`, `/calcular`, `/status` etc.), todos com **prefixos distintos**, portanto sem colisão real em produção. Dois casos merecem atenção futura: `/socios/{socio_id}` presente tanto em `gestao_societaria` (patch) quanto `sociedades_cliente` (patch/delete) — mesmo contexto semântico em routers separados; `/templates/{template_id}` em `workflow` e `checklists`.

### 3.3 Frontend ↔ API
- O frontend consome **57 caminhos de API distintos** identificados em `frontend/src` (grep de padrões `/api/...`).
- Roteamento canônico consolidado em `frontend/src/config/canonicalRoutes.ts` com redirectores legados documentados (`/prazos`, `/tarefas`, `/intimacoes`, `/suspensoes`, `/knowledge-hub`, `/ramos` — todos redirecionados por decisão documentada).
- Frontend possui **103 páginas** cobrindo: clientes, casos, atividades/prazos, documentos/GED, peças, inteligência/IA, RAG, DataJud, honorários, financeiro, NFSe, timesheet, kanban, assinaturas, procurações, intimacoes, agenda, portal, sala jurídica, DPT360, e verticais (ambiental, tributário, trabalhista, bancário, previdenciário, consumidor, fiscal).

### 3.4 Modelos e migrations
- 68 modelos em `app/models/`; 136 migrations Alembic; migrations recentes na main (fev–ago/2026) incluem: padronização `alembic_version` varchar(128) (#1151), SHA-256 GED (#1144/#1142), publicação explícita portal (#1141), prazos forenses (#1146).
- Teste `test_alembic_single_head.py` presente em CI — single head verificado nos gates.

## 4. Inconsistências de baseline encontradas (critério: impedir continuidade segura)

| # | Achado | Severidade | Ação tomada |
|---|---|---|---|
| 1 | 9 prefixos de router duplicados (fragmentação modular) | Baixa — sem colisão de caminho em produção | Apenas registrado; não impede continuidade |
| 2 | `/socios/{socio_id}` em dois routers distintos | Baixa | Registrado |
| 3 | `defesas_revisoes`/`entrada_universal` não importados em main.py (anexados via `__init__.py`) | Informativo | Verificado que é mecanismo intencional; não é órfão |
| 4 | Issues abertas relevantes: phantom save societária (#1077, corrigida no HEAD por #1155), ASS-00 portal assinaturas (#1075), NFS-e (#1072), CI fallback (#1026/#1031), backup criptografia (#1020) | — | Cruzadas com a baseline; serão tratadas nos módulos funcionais correspondentes |
| 5 | Nenhuma tag de versão; release controlada via workflows de gate | Informativo | — |

**Correções destrutivas: nenhuma executada.** O prompt 01 autoriza corrigir apenas inconsistências que impeçam a continuidade segura; nenhuma foi identificada nesse nível.

## 5. Prova de execução do inventário

Script automático de baseline registrado no repositório:
`scripts/inventory/m01_baseline_check.py` (executado com sucesso; saída completa em `qa/homologacao/m01/baseline_check_output.txt`).

Execuções verificáveis:
- `git log -1` → HEAD confirmado.
- `grep -c include_router main.py` → 155 registros.
- Contagens de routers (155), models (68), services (168), pages (103), migrations (136), testes backend (487), testes frontend (104), serviços Docker (8), workflows CI (17).

## 6. Status do Módulo 01

**HOMOLOGADO** — Baseline real mapeada e registrada. Inventário cruzado concluído. Sem bloqueio externo. Sem correção destrutiva executada. O repositório está pronto para o Módulo 02 (Infraestrutura, Docker e Health), que requer ambiente local com PostgreSQL 16 + pgvector.

**Evidências:** `qa/homologacao/m01/RELATORIO_MODULO_01_INVENTARIO_BASELINE_2026-08-15.md` (este arquivo), `qa/homologacao/m01/baseline_check_output.txt`, `scripts/inventory/m01_baseline_check.py`.
