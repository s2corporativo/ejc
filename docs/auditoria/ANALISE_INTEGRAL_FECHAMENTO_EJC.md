# Análise integral do EJC — pendências, falhas, código morto e plano de fechamento

- **Base analisada:** `main` @ `bcbaa6b` (02/10/2026, após #1988)
- **Ambiente:** Linux, Python 3.11.15, Node 22.22.0, venv isolado
- **Método:** execução real dos portões (ruff, pytest, tsc, eslint, vitest, build,
  prettier), varredura estática por script (imports, marcas de histórico,
  configuração), `vulture`, `knip`, `pip-audit`, `npm audit` e leitura dirigida
  dos pontos suspeitos. Toda afirmação abaixo foi conferida no arquivo citado;
  achados de ferramenta que se mostraram falso-positivos estão listados na §9.

---

## 1. Resumo executivo

| Dimensão | Resultado | Leitura |
|---|---|---|
| Backend — `ruff check app` (config do repo) | **0 erros** | Limpo |
| Backend — `pytest` completo | **8.032 passed, 482 skipped, 0 failed** (250 s) | `main` verde |
| Frontend — `tsc --noEmit` | **0 erros** | Limpo |
| Frontend — `vitest run` | **160 arquivos / 872 testes, 0 falhas** | Verde |
| Frontend — `vite build` | **OK** (4,45 s) | Verde |
| Frontend — ESLint | 0 erros, **646 warnings** (625 `no-explicit-any`, 21 `exhaustive-deps`) | Dívida de tipagem |
| Frontend — Prettier | **21 arquivos fora do padrão** | Cosmético |
| Alembic | **head único** `170_djen_remove_unicidade_global` | Íntegro |
| `npm audit --omit=dev` | 0 vulnerabilidades | OK |
| `pip-audit` | **2 CVEs** (PyJWT 2.14.0, WeasyPrint 69.0) | Ver §3 |
| Tamanho | backend ~184 mil linhas (`app/`), frontend ~130 mil linhas, 907 endpoints, 163 routers, 742 arquivos de teste backend | Grande |

**Conclusão:** o EJC **não está quebrado** — compila, testa e constrói limpo.
O passivo real é **estrutural**: camadas de compatibilidade e *monkey patches*
que viraram permanentes, código morto residual, duas superfícies de API, flags
de rollout já concluídos, ~790 arquivos com marcas de histórico (PR/onda/data)
e documentação dispersa (370 arquivos `.md`). "Fechar" o EJC é eliminar esse
passivo **sem** reescrever o que funciona.

---

## 2. Pendências abertas no GitHub (estado em 02/10/2026)

### 2.1 PRs abertos (21)

| Situação | PRs |
|---|---|
| Prontos (não-draft) | #1991 parcelas 1-N · #1985 contrato de honorários ↔ Financeiro · #1984 logomarca DPT · #1950 ledger de rotas · #1947 seed sintético |
| Draft — segurança/LGPD | #1976 e **#1957 (duplicados: ambos tratam C1 `/sumulas/verificar-conflito`)** · #1977 jurimetria (I3) · #1979 Infosimples teto de custo (E2) · #1981 RAG ingestão de saída de IA (I1) |
| Draft — IA/Legal Brain | #1978 inventário AST (I2) · #1964/#1966/#1968 Legal Brain · **#1961 e #1970 (sobrepostos: AILog do Manus)** · #1951/#1952 aprendizado HITL · #1954 proveniência RAG |
| Draft — saneamento/docs | **#1955 saneamento estrutural** (remove `pnpm-lock.yaml`, `dashboard-canonical.css`, `.agent/`; move relatórios) · #1938 auditorias |

**Observações**

1. **#1950 está desatualizado no propósito**: o PR afirma "main vermelha", mas
   a suíte completa na `main` atual (`bcbaa6b`) passou com 0 falhas. Antes do
   merge, conferir se a mudança ainda é necessária ou já foi absorvida.
2. **Duplicidades a resolver pelo titular:** #1957 × #1976 (C1) e #1961 × #1970
   (Manus/AILog). Issues duplicadas correspondentes: #1956 × #1971 e #1960 × #1969.
3. **A `main` está congelada no Woodpecker.** `config/release_candidate.json`
   (`release: homologacao-final-20260930`, `freeze_main: true`) faz
   `scripts/check_release_freeze.py` reprovar todo PR cuja branch de origem não
   seja `fix/homologacao-final-20260930` — inclusive PR só de documentação. Ainda
   assim, PRs seguem sendo mesclados manualmente (ex.: #1988). Cabe ao titular
   encerrar a release (atualizar ou remover o congelamento) ou formalizar a
   exceção; enquanto isso, o check `ci/woodpecker/pr` fica vermelho em todos os PRs.
4. #1955 é **pré-requisito** de qualquer limpeza documental — esta análise não
   toca os arquivos dele (regra 10 do `CLAUDE.md`).

### 2.2 Issues abertas (15)

#1986 DJEN (perda por advogado, vínculo manual, evidência truncada) · #1975 I2 ·
#1974 Infosimples · #1973 RAG/AI-log · #1972 jurimetria · #1971/#1956 C1 ·
#1969/#1960 Manus · #1967/#1965/#1963 Legal Brain · #1953 saneamento ·
**#1943 súmulas oficiais antes do modo estrito de citações** ·
**#1941 Google Drive Knowledge sem autenticação própria/homologação**.

---

## 3. Falhas e riscos reais (corrigir)

Ordenados por severidade. "Confirmado" = verificado no código nesta análise.

### Alta

| # | Achado | Evidência | Recomendação |
|---|---|---|---|
| A1 | **Controles de segurança da IA instalados por *monkey patch* em runtime.** Fail-closed de provedores, escopo de precedentes `caso:<id>`, listagem escopada de `KnowledgeDoc` e HyDE estritamente local dependem de `instalar()` sobrescrever funções no boot. O próprio docstring declara "correções transitórias". | `app/services/ai_core_hardening_patch.py` (303 linhas), `app/services/datajud_cognitive_patch.py` (225), chamados por `app/services/event_subscribers.py:51,66`; o Celery só os recebe porque `event_subscribers` foi incluído em `app/core/celery_app.py:26-35` | Internalizar cada correção na função de origem (gateway, RAG, DataJud), com teste de regressão por item, e apagar os dois módulos. Enquanto existirem, qualquer novo processo/entrypoint que não importe `event_subscribers` roda **sem** as barreiras. |
| A2 | **12 de 42 jobs agendados têm monitoramento de resultado.** Sem *heartbeat*: `feriados`, `feriados_brasilapi` (alimentam cálculo de prazo), `honorarios`, `regua_cobranca*`, `purga_lgpd`, `purga_ia`, `retencao_ia` (obrigações LGPD), `procuracoes`, `contratos`, `ing_*` (ingestões RAG), `workflow_sla`, entre outros. | `app/services/scheduler.py` (42 IDs) × `app/services/heartbeat_service.py` (12 constantes `JOB_*`) | Estender o padrão `_bater_ponto` a todos os jobs com efeito jurídico, financeiro ou LGPD; priorizar feriados e purgas. |
| A3 | **CVE em WeasyPrint 69.0** (GHSA-jf6q-chmf-3h3v): `write_pdf()` ignora o `url_fetcher` restritivo em `xmp_metadata`/anexos. | `backend/requirements.txt` | Atualizar para 70.0. O EJC não usa `url_fetcher`/`xmp_metadata` (grep vazio), então a exposição atual é baixa, mas o PDF é gerado a partir de conteúdo de usuário. |

### Média

| # | Achado | Evidência | Recomendação |
|---|---|---|---|
| M1 | **CVE em PyJWT 2.14.0** (GHSA-42vr-xj54-vc7v), no fluxo `PyJWKClient`. | `requirements.txt` | Atualizar para 2.15.0. O EJC usa HS256 sem JWKS (`PyJWKClient` não aparece em `app/`): exposição improvável, correção trivial. |
| M2 | **Pipeline de rescan SHA-256 sem gatilho.** `rescan_tasks.agendar_rescan`, `document_rescan_service`, `document_remote_hash_service` e as tabelas da migration 142 existem, mas nenhuma rota, job ou script de `app/` os aciona; `rescan_tasks` nem está no `include` do Celery. | `app/tasks/rescan_tasks.py`; `app/core/celery_app.py:26` | Decidir: expor em rota admin + job, ou remover o código (as tabelas ficam até uma migration *contract*). |
| M3 | **Parâmetros de API externa nunca confirmados.** | `app/services/transparencia_service.py:218` e `app/routers/car.py:34` (`TODO(verificar-vps)`) | Validar contra a documentação oficial (Portal da Transparência / SICAR) e cobrir com teste de contrato; até lá a consulta pode retornar vazio silenciosamente. |
| M4 | **Webhook Evolution (WhatsApp) recebe mensagem e não integra.** | `app/routers/evolution_webhook.py:61` (`TODO: integrar com fluxo de CRM/casos`) | Integrar ou desligar a rota pública `/api/webhooks/` para esse provedor. |
| M5 | ~~Texto de PR exposto em resposta de API.~~ **Corrigido neste PR.** | `app/modules/dpt360/radar_service.py`: `dependencias_pendentes` citava um PR fechado sem merge; o gate de vigência já existe em `services/ai/reranker.py` | Lista vazia + teste de regressão `tests/test_dpt360_radar_sem_referencia_de_pr.py`. |
| M6 | **Duas superfícies de API para os mesmos 907 endpoints** (`/api` e `/api/v1`), mantidas por normalização no middleware. | `app/core/auth_middleware.py:42-63`; `frontend/src/lib/api.ts` (interceptor que apara prefixo) | Definir `/api/v1` como única e desativar `/api` após janela de telemetria; dobra a superfície de ataque e de testes. |
| M7 | **Configuração em dois mecanismos.** 278 *settings* em `config.py` (1.590 linhas, 86 flags, 45 desligadas por padrão) **e** 73 leituras diretas de `os.getenv/os.environ` em 30 arquivos; 47 variáveis do `.env.example` não passam pelo `Settings` (ex.: `GOOGLE_DRIVE_*`, `*_OPEN_DATA_ENABLED`). | script de comparação `config.py` × `.env.example` | Centralizar tudo no `Settings` (validação e documentação únicas). |

### Baixa

| # | Achado | Evidência |
|---|---|---|
| B1 | Argumento padrão mutável (`itens: list = []`) | `app/routers/checklists.py:79,100`; `app/routers/workflow.py:92` |
| B2 | Itens duplicados em conjunto (`"acórdão"`, `"janeiro"`) | `app/services/ai/ner_local.py:105,124` |
| B3 | Variáveis atribuídas e não usadas | `models/case.py:209`, `services/commission_service.py:311`, `services/datajud_service.py:806`, `services/ajuizamento/conectores/base.py:126` |
| B4 | Migrations com o mesmo prefixo `101_` (bifurcação já fundida em `104_merge_entrada_orquestrador`) | `alembic/versions/101_*.py` — não reescrever (aplicadas em produção); só registrar |
| B5 | Warnings de depreciação: `starlette.testclient` com `httpx`, `import multipart` | saída do pytest |
| B6 | `docker-compose.override.yml` versionado (o Compose o carrega sozinho em qualquer clone) e quase idêntico ao `.example` | raiz do repo |

---

## 4. Código morto, redundante e obsoleto

### 4.1 Morto (sem consumidor em produção — confirmado)

| Item | Tamanho | Evidência |
|---|---|---|
| 17 componentes no fim de `frontend/src/components/UI.tsx` (`IconButton`, `SearchInput`, `Panel`, `MetricCard`, `PageContainer`, `Tabs`, `Pagination`, `Breadcrumb`, `FilterBar`, `Stepper`, `Timeline`, `ActionMenu`, `Combobox`, `DatePicker`, `Calendar`, `FileUploader`, `DataGrid`) | **~1.135 linhas** (da linha 1443 ao fim) | nenhum `import` desses nomes vindo de `UI` fora do próprio arquivo |
| `SkeletonList`/`SkeletonCard` duplicados em `UI.tsx` e `components/base/Skeleton.tsx` | — | knip |
| Exports não usados: `Dashboards.tsx` (6), `taxonomia.ts` (5), `types/gerado.ts` (10 constantes), `ramosConfig.ts` (`RAMOS_LISTA*`), `areasWorkspace.ts` (3), `ramoWorkspace.ts` (3) e outros; 40 tipos exportados sem uso | — | knip |
| `frontend/src/styles/dashboard-canonical.css` | 17 linhas | sem import (removido em #1955) |
| `frontend/tests/e2e-homologacao.mjs`, `tests/homologacao-modulos.mjs`, `scripts/auditar-css.selftest.mjs` | — | sem script em `package.json` |
| Rescan SHA-256 (ver M2) | ~700 linhas | sem gatilho |
| Dependência `fpdf2` | — | o próprio `requirements.txt:85` diz "sem consumidores em app/ — remover" |
| Reexports de compatibilidade em `app/routers/financeiro_consolidado.py` (15 nomes) | — | `vulture`; só preserva o caminho de import antigo |
| `app/models/dataroom_teses_v4_compat.py` | — | models de routers já arquivados, mantidos só para o Alembic |

### 4.2 Só usado por testes (avaliar)

`app/core/veredito_ia.py`, `app/services/legal_graph.py`, `app/services/legal_brain/shadow.py`,
`app/utils/api_contract.py` (é ferramenta de teste — mover para `tests/`),
`app/integrations/inlabs_parser.py`, `app/eval/*` (CLIs de avaliação, usados por
`scripts/ci-local.sh` — manter, mas fora de `app/`).

### 4.3 Redundante (duas implementações do mesmo conceito)

| Conceito | Implementações | Observação |
|---|---|---|
| Inteligência do caso | `case_intel.py` (488) e `case_intelligence_service.py` (219) | nomes quase iguais, responsabilidades sobrepostas |
| Contexto do caso | `case_context.py` (235) e `legal_case_context.py` (61) + `modules/legacy_verticals/case_context_adapter.py` | adapter "enquanto durar a compatibilidade" |
| IA | `ai_service.py` (1.377) e `ai_gateway.py` (1.749) + `services/ai/` (provider_registry, provider_registry_runtime, provider_policy, model_router) | dois registros de provedor (`provider_registry` + `_runtime`) |
| Ingestão documental | `document_ingestion_service`, `document_ingestion_orchestrator` ("substituir gradualmente a orquestração do router GED"), `document_intake_service`, `documento_service`, `documental`, `document_intelligence/` — 20+ módulos `document_*` | migração iniciada e não concluída |
| Callback de análise documental | `routers/documents._analisar_doc_bg` sobrescrito no boot por `document_analysis_hook` | `event_subscribers.py:30-46` |
| Navegação frontend | `CANONICAL_CORE_NAV` e `CANONICAL_MENU_9_NAV` exportam o mesmo valor | `config/canonicalNavigation.ts` |
| Lockfiles | `package-lock.json` e `pnpm-lock.yaml` | removido em #1955 |
| CI | GitHub Actions (arquivado em `docs/arquivo/ci/`), Woodpecker (`.woodpecker.yml`), runner self-hosted, `scripts/ci-local.sh`, `ci-fallback*.sh` | cinco caminhos para o mesmo portão |
| Pastas de documentação | `docs/ai` × `docs/ia`; `docs/audit` × `docs/auditoria` × `docs/auditorias` | parte resolvida em #1955 |

### 4.4 Obsoleto (rollouts e transições concluídos)

- **Flags de rollout já ativas por padrão**: `VITE_EJC_MENU_9`, `VITE_EJC_W3_TABS`,
  `VITE_EJC_W4_TABS` e overrides por `localStorage` (`frontend/src/config/w3Tabs.ts`).
  Concluído o rollout, removem-se a flag e o caminho antigo.
- **Telemetria de "telas legadas"**: `app/services/route_usage.py:62-90` ainda
  descreve `/legado/prazos|tarefas|intimacoes|suspensoes` como telas existentes,
  mas os arquivos `pages/Prazos.tsx`, `Intimacoes.tsx`, `Tarefas.tsx`,
  `Suspensoes.tsx` já não existem — viraram redirects em `moduleRegistry.tsx`.
  Os endpoints continuam usados pela Central de Atividades (conferido), então a
  correção é atualizar o motivo do monitoramento ou encerrá-lo.
- **Redirects legados**: 50 entradas `from:` em `moduleRegistry.tsx`
  (`/agenda`, `/kanban`, `/legado/*`, `/assistente-ia`, `/ia`…). Após 60–90 dias
  sem acesso, removem-se.
- **Três rotas "duplicata depreciada"** (`/penal/ferramentas/prescricao-punitiva`,
  `/admin-esp/ferramentas/recurso-multa-transito`, `/trabalhista/ferramentas/horas-extras`)
  ainda chamadas pelo frontend — migrar o chamador para a rota canônica e remover.
- **Scripts de execução única** em `scripts/`: `fase3_edit.py` (removido neste PR), `apply_architecture_refactor_wave1.py`, `audit_2026-07-01/*.sql`
  (movido em #1955), `migrar_env_obsoletos.sh`.
- **`qa/`** com planos de PR específicos (`pr40_*.md`, `evidencias/pr494`).

---

## 5. Marcas de edição ao longo do tempo

Medição por regex em `backend/app`, `frontend/src`, `backend/tests`, `backend/alembic` (2.113 arquivos):

| Tipo de marca | Ocorrências | Onde |
|---|---|---|
| Referência a PR/issue (`PR #705`, `(#1491)`) | 584 | app 198 · testes 314 · front 42 · alembic 30 |
| Onda/fase/wave/bloco/lote/`W82`/`P1-6` | 576 | app 241 · testes 230 · front 86 · alembic 19 |
| Data em comentário (2025/2026) | 205 | app 129 · testes 46 · front 29 |
| "corrigido/antes/agora/legado/compat" | 65+ (estrito) | — |
| **Arquivos afetados** | **~790** | — |
| Testes com nome histórico (`_onda1`, `_1336`, `bloco6_`, `_w82`…) | **43 arquivos** | `backend/tests/` |

Maiores concentrações: `tests/test_rotas_registro_explicito.py` (59), `core/config.py` (55),
`routers/ai.py` (38), `routers/peca_geracao.py` (27), `services/ai_gateway.py` (27),
`routers/cases.py` (26), `config/moduleRegistry.tsx` (20).

Exemplos reais: `# gate e registrado por inteiro. Review do CodeRabbit no PR #705.`
(`peca_geracao.py:606`); `# Onda 2 — Fase C (2026-07): corrigidas e REMOVIDAS da matriz`
(`homologacao_ferramentas.py:54`); `# Idempotência (follow-up PR #283)` (`motor_peca_service.py:805`).

**Critério para a limpeza** (o que sai e o que fica):

- **Sai:** número de PR/issue, onda/fase/bloco, data, nome de revisor/ferramenta,
  narrativa "antes era X, agora é Y". Isso pertence ao `git log`/`git blame`.
- **Fica, reescrito no presente:** o *porquê* da regra (invariante, risco jurídico,
  base legal). Ex.: `# Idempotência (follow-up PR #283): submissão repetida...` →
  `# Idempotência: submissão repetida do mesmo prazo devolve os rascunhos existentes.`
- **Não se toca:** migrations já aplicadas (regra 5 do `CLAUDE.md`), identificadores
  de achado usados como chave em testes/ledgers sem antes migrar a chave, e
  referências normativas (artigo de lei, súmula), que não são marca de edição.
- **Testes:** renomear os 43 arquivos pelo comportamento verificado
  (`test_datajud_deadline_fail_closed_1336.py` → `test_datajud_prazo_fail_closed.py`),
  um PR por área, com `git mv` para preservar histórico.

**Por que não executar agora, em um único PR:** atinge ~790 arquivos e colide com
os 21 PRs abertos (regra 10 do `CLAUDE.md`), gerando conflito em quase todos. A
forma segura é por ondas de área, **depois** de mesclar ou fechar os PRs abertos
daquela área (§7, Fase 3).

---

## 6. Análise por módulo

Legenda: ✅ íntegro · ⚠️ dívida estrutural · ❗ falha/risco a corrigir.
Testes: todos os routers listados têm testes que os referenciam (conferido por
prefixo de rota e nome de módulo).

| Módulo (frontend → backend) | Estado | Pontos |
|---|---|---|
| Autenticação/2FA (`auth`, `users`, `auth_middleware`) | ✅ | bcrypt puro, JWT HS256; normalização de `//` e `/api/v1` no middleware; M1 (PyJWT) |
| Casos (`casos`, `caso-detalhe` → `cases.py` 2.111 linhas, 24 endpoints, 76 consultas SQL diretas) | ⚠️ | router grande com SQL inline; `CasoDetalhe` 280 kB no bundle |
| Clientes/CRM (`clientes`, `crm`, `cliente-detalhe` → `clients.py`) | ⚠️ | 53 consultas diretas no router; `DossieCliente.tsx` 1.795 linhas |
| Entrada única / intake (`entrada`, `caso-novo` → `entrada_universal`, `intake`) | ⚠️ | três serviços de entrada (`entrada_service`, `entrada_juridica_service`, `entrada_universal`) |
| Atividades/Prazos/Intimações (`atividades` → `deadlines`, `intimacoes`, `tasks`, `suspensoes`) | ⚠️ | `CentralAtividades.tsx` 2.287 linhas; telemetria "legado" desatualizada (§4.4); issue #1986 (DJEN) aberta |
| DJEN/DataJud (`datajud`, `diario-oficial`) | ❗ | barreira DataJud via patch (A1); #1986 aberto |
| Documentos/GED (`documentos` → `documents.py`) | ⚠️ | ingestão fragmentada (§4.3); callback sobrescrito no boot; rescan órfão (M2) |
| Peças/Ajuizamento (`pecas`, `ajuizamento` → `peca_geracao`, `legal_docs`, `motor_peca`) | ✅/⚠️ | gates HITL/citação presentes; `legal_docs.py` 1.577 linhas |
| Áreas de atuação (`ramos`, `ramo-detalhe`, `tributario` → `ramos*.py`) | ⚠️ | `ramosConfig.ts` 3.293 linhas; `RamoBase` 336 kB no bundle; 3 rotas duplicadas depreciadas |
| Inteligência/IA (`inteligencia`, `prompts`, `governanca-ia` → `ai.py`, `ai_gateway`, `ia_governanca`, `rag`) | ❗ | A1; duplicidade `ai_service`/`ai_gateway`; issues I1/I2/I3, #1943 (súmulas antes do modo estrito) |
| Legal Brain | ⚠️ | 4 PRs draft e 3 issues abertos; `shadow.py` só em testes |
| Financeiro/Honorários (`financeiro` → `financeiro/*`, `fees`, `nfse`) | ⚠️ | 3 PRs abertos tocando contratos/parcelas (#1985, #1991, #1988 mesclado); fachada de reexport; jobs `honorarios`/`regua_cobranca` sem heartbeat (A2) |
| Data Room / Teses (`banco-teses` → `data_room`, `teses`) | ⚠️ | models `_v4_compat` mantidos só para o Alembic |
| Sociedade/Contratos societários | ✅ | — |
| DPT360 / Radar (`dpt360`, `radar`) | ✅ | M5 corrigido neste PR |
| Integrações públicas (Transparência, CAR, Infosimples, Google Drive) | ❗ | M3; #1974 (Infosimples); #1941 (Drive sem auth própria) |
| WhatsApp/Evolution | ❗ | M4 |
| Configurações/Cofre/Usuários/Lixeira/Auditoria | ✅ | cofre com chave efêmera em dev (warning esperado) |
| Backup (`backup_admin`, `backup_*`) | ✅ | job monitorado |
| Portal do cliente (`portal-*`) | ✅ | rotas isoladas no registry |
| Diagnóstico/Mapa de módulos | ⚠️ | diagnóstico curado diverge do inventário (já documentado no `CLAUDE.md`) |
| Design system (`components/UI.tsx`) | ⚠️ | ~1.135 linhas mortas; 625 `any` no frontend |

---

## 7. Melhor forma de "fechar" o EJC como se tivesse começado hoje

**Princípio:** não reescrever. O sistema está verde em 8.904 testes; reescrever
jogaria fora a cobertura que é o maior ativo do repositório. Fechar é **remover
as camadas de transição**, deixando o código como se a versão final tivesse sido
escrita diretamente. Cada fase é uma sequência de PRs pequenos, com o portão da
tabela de verificação do `CLAUDE.md`.

### Fase 0 — Estancar (1–2 dias)
1. Decidir as duplicidades: #1957 × #1976, #1961 × #1970; fechar issues espelhadas.
2. Mesclar ou fechar os PRs de segurança (C1, I1, I3, E2) e #1955/#1950.
3. **Congelar features** até o fim da Fase 3 (cada PR novo reabre conflito com a limpeza).

### Fase 1 — Corrigir o que é risco (§3)
A2 (heartbeat em todos os jobs jurídicos/LGPD/financeiros) · A3/M1 (bump de
WeasyPrint e PyJWT) · M3/M4 · B1–B3. (M5 e `scripts/fase3_edit.py` já resolvidos neste PR. O bump de dependências, a remoção de `fpdf2` e a poda de `UI.tsx` aguardam o fechamento dos PRs ativos que tocam `backend/requirements.txt` — #1950, #1951, #1952, #1954, #1955 — e `frontend/src/components/UI.tsx` — #1984, #1985 —, por força da regra 10 do `CLAUDE.md`.)

### Fase 2 — Eliminar transições (o "como se fosse hoje" de verdade)
1. **A1:** internalizar os dois *patches* e o hook de documentos; apagar
   `ai_core_hardening_patch.py`, `datajud_cognitive_patch.py` e os `instalar()`.
2. Unificar: `ai_service` → `ai_gateway`; `case_intel` + `case_intelligence_service`;
   ingestão documental em um orquestrador; `provider_registry` + `_runtime`.
3. Remover fachadas de reexport (`financeiro_consolidado`), `legacy_verticals`
   após migrar os 3 chamadores, flags `MENU_9`/`W3`/`W4`, redirects sem acesso,
   rotas duplicadas depreciadas.
4. Remover código morto da §4.1 e `fpdf2`.
5. Uma superfície de API (`/api/v1`) e uma fonte de configuração (`Settings`).
6. Um CI: escolher Woodpecker **ou** `ci-local.sh` como portão oficial e arquivar o resto.

### Fase 3 — Apagar as marcas de edição (§5)
Por área, depois que os PRs daquela área estiverem fechados: comentários
reescritos no presente, testes renomeados por comportamento, sem tocar migrations
aplicadas. Um PR por área (IA, casos, financeiro, documentos, frontend…).

### Fase 4 — Baseline de banco e documentação
1. **Migrations:** 170 revisões. Opção segura: nova revisão *baseline* gerada do
   schema de produção para **bancos novos**, mantendo a cadeia antiga para o banco
   existente (que só recebe `stamp`). Exige backup, ensaio de restore e decisão
   explícita do titular — é a única etapa com risco irreversível.
2. **Documentação:** 370 `.md`. Manter `README`, `CLAUDE.md`, `AGENTS.md`,
   `docs/GOVERNANCA_IA.md`, catálogos e `RUNBOOK_*` vigentes; mover relatórios,
   pareceres, planos de onda e evidências de PR para `docs/arquivo/` (ou para fora
   do repositório). #1955 já faz parte disso.
3. Regenerar `MAPA_DE_MODULOS`/`ARQUITETURA_ATUAL` a partir do código.

### Critério de "fechado"
- Zero `instalar()` / *monkey patch* no boot.
- Zero referência a PR, onda ou data em código e testes (exceto migrations aplicadas).
- Uma superfície de API, um registro de provedores, uma fonte de configuração, um CI.
- Todos os jobs com heartbeat de resultado.
- `pip-audit` e `npm audit` limpos; ESLint sem `any` em código novo.
- Suíte completa verde no mesmo número de testes (ou maior) que hoje.

---

## 8. Pontos de decisão do titular

1. Duplicidades de PR (#1957/#1976; #1961/#1970) e o congelamento da `main`
   pela release `homologacao-final-20260930` (§2.1, item 3).
2. Congelamento de features durante as Fases 2–3.
3. Rescan SHA-256: ativar ou remover.
4. Desativação da superfície `/api` em favor de `/api/v1` (impacta integrações externas, ex.: n8n).
5. Baseline de migrations (Fase 4.1).
6. CI oficial único.

## 9. Falso-positivos descartados nesta análise

- `ramos_*.py` "sem registro em `main.py`": são incluídos por `routers/ramos.py`.
- `PREFIXOS_PUBLICOS` com `/api/rag/knowledge-base/`: protegido por API key com escopo `knowledge:write` e rate limit (`rag_public.py`).
- `public/sw.js`/`sw-register.js` "sem uso" (knip): carregados por `index.html:18`.
- Routers "sem teste" pela heurística de prefixo: todos têm testes ao conferir por nome de módulo/rota.
- Aviso de *pooling* do fastembed: `embedding_service.py` valida `POOLING_ESPERADO` e a versão está fixada (`fastembed==0.8.0`).
- B023 em `bank_statement.py:66`: a função interna é chamada na mesma iteração.
- Senhas/segredos literais em código: nenhum encontrado.
- Seeds `checklists_seed`, `clausulas_seed`, `oab_honorarios_seed`, `templates_seed` (listados inicialmente como mortos): são CLIs manuais (`python -m app.seeds.<nome>`) documentados em `docs/DEPLOY-VPS.md` — a carga da tabela OAB/MG é deliberadamente manual. Mantidos.
