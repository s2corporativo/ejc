# Baseline de Performance — Cadeia Entrada → Caso → Hoje

Status: **esqueleto aprovado — medições pendentes de execução em homolog** (sandbox sem PostgreSQL; medições rodam no CI/homolog com `RUN_DB_TESTS=1` + `SCHEMA_CHECK_DATABASE_URL` apontando ao dataset sintético da seção 7).

Data de emissão: 2026-10-02 · Base de código: main `70d45e8` · Alembic HEAD: `164_commission_rules` (verificar `python3 scripts/alembic_dag_check.py --versions-dir backend/alembic/versions` antes de qualquer nova revision).

---

## 0. Portão (gate) desta fase

**Nenhum índice, cache ou reescrita de query pode ser implementado antes que este baseline seja reproduzível** (mesmo dataset → mesmas contagens → mesma matriz preenchida em 2 rodadas com amplitude conhecida). Ganho de performance só vale se p95 cair acima do ruído inter-rodada (seção 6.4). Este documento é o contrato que impede "otimização por achismo".

## 1. Escopo

A cadeia **Entrada → Caso → Hoje** cobre o primeiro minuto operacional do usuário: login → Hoje (painel de decisão) → Central de Atividades → listas (casos/clients/prazos/documents/tarefas). Os roteadores analisados: `atividades.py`, `tasks.py`, `cases.py`, `clients.py`, `deadlines.py`, `documents.py`, `dashboard.py` (+ `agenda_eventos.py` e `ownership.py` como dependências de contrato). Páginas analisadas: `DashboardUltra.tsx`, `CentralAtividades.tsx`, `Casos.tsx`.

Fora de escopo nesta fase: materialized view de `vw_atividades` (decisão do plano: manter a view; só cursor/página), expurgo legacy_verticals, refactors arquiteturais.

## 2. Inventário dos endpoints (estado atual em `70d45e8`)

| Rota | Paginação | Ordenação | Tiebreaker | Visibilidade (resumo) | Custo dominante |
|---|---|---|---|---|---|
| `GET /api/atividades` | **NENHUMA** — devolve o feed inteiro | `data ASC NULLS LAST` | **NENHUM** (datas empatadas ⇒ ordem instável) | gestão = tudo; equipe: caseless `responsavel_id = uid` **OU** `EXISTS cases` da carteira (`atividades.py:30-39`) | View `vw_atividades` = UNION ALL de 5 tabelas (deadlines, tasks, suspensoes_tribunal, agenda_eventos, djen_comunicacoes) + LEFT JOIN cases; payload descontrolado |
| `GET /api/atividades/alertas-inteligentes` | `limit_per_type ≤ 10` | por tipo | — | service próprio | baixo |
| `GET /api/tasks/` | **NENHUMA** | `data_limite ASC NULLSLAST, created_at` | created_at só (colisão possível) | **`tasks.py:109-130` — predicado canônico, INTOCÁVEL**: gestão = tudo; equipe: `case_id IN carteira` OU caseless `(responsavel_id|criado_por) = uid` | scan completo do kanban a cada chamada |
| `GET /api/cases/` | offset `page/page_size≤500` | `created_at DESC` | **NENHUM** | `_filtro_visibilidade` (`cases.py:106-116`): socio+ tudo; demais `or_(resp,aux)` | `count(*)` subquery + OFFSET; `search` ILIKE 4 colunas |
| `GET /api/cases/stats` | — | — | — | mesma do listar | 4 agregações sobre o mesmo conjunto (fonte única BUG-06/10) |
| `GET /api/clients/` | offset `page/page_size≤500` | `created_at DESC` | **NENHUM** | `_filtro_visibilidade_cliente` aplicada ANTES da busca | `count(*)` + ILIKE nome/razão_social + hash cego CPF/CNPJ (`clients.py:423-441` — **PRESERVAR**) |
| `GET /api/deadlines/` | offset `page/page_size≤200` | `data_prazo ASC` | **NENHUM** | `_filtro_escopo_prazos` (`deadlines.py:62-76`): gestão = tudo; equipe: `case IN carteira` OU `responsavel = uid` | `count(*)` + OFFSET |
| `GET /api/documents/` | offset `page/page_size≤100` | `created_at DESC, id DESC` | `id DESC` ✓ (único correto) | `documents.py:534-574`: `<socio` limita `confidencialidade IN (normal,interno)`; cliente_externo só os próprios `normal`; não-gestão: case da carteira OU client da carteira OU upload próprio caseless | `count(*)` com ILIKE sobre **`ocr_text`** (pesado) |
| `GET /api/dashboard/` | — | — | — | `require_roles(["secretaria"])`; escopo financeiro: admin+ vê escritório, demais por uid (`dashboard.py:51` usa `ROLE_LEVEL["admin"]` ≠ `is_gestao` socio+ — **divergência de limiar registrada**) | 7 blocos SQL; cache TTL 30s em processo (`_DASHBOARD_TTL_S=30.0`) |
| `GET /api/agenda-eventos/` | offset `page_size≤500` (default 200) | (não mapeado — fora da cadeia crítica) | — | padrão do módulo | Central chama com `page_size: 500` |

Observações estruturais:
- Nenhum helper de paginação existe em `app/core/` — o cursor da Tarefa 2 é módulo novo (`app/core/pagination_cursor.py`).
- `vw_atividades` (migration `100_vw_atividades_enriquecida.py`) é fonte única da Central: cada linha da Central custa um scan da UNION ALL de 5 tabelas. **A view é mantida** (decisão do plano; materialized view fora de escopo).
- `djen_comunicacoes` não tem filtro `deleted_at` na view (tabela sem soft delete) — intimações usam `advogado_id` como `responsavel_id`.
- Rate limits existentes a preservar: `cases-listar 120`, `clients-listar 120`, `doc-listar 120`, `deadlines-listar 120`, etc.

## 3. Contratos de visibilidade (congelados — nenhuma alteração é permitida)

Estes predicados são o contrato de segurança da cadeia. A paginação cursor (Tarefas 2/3/5) deve **reautenticar por página** com exatamente estes predicados:

1. **Tarefas** — `tasks.py:109-130`: tarefa COM caso segue a carteira do caso (`Case.advogado_responsavel_id`/`advogado_auxiliar_id`, `deleted_at IS NULL`); tarefa SEM caso é pessoal (responsável OU criador). Casos órfãos só para gestão. **Não mexer.**
2. **Atividades** — `atividades.py:30-39`: `responsavel_id` nunca funciona como bypass da carteira de um caso (caseless exige `responsavel = uid`; com caso exige `EXISTS cases` da carteira).
3. **Casos** — `cases.py:106-116`: socio+ vê tudo; demais só a própria carteira. Gate de corpo `requer_equipe_juridica`.
4. **Clientes** — `clients.py:418-441`: segregação de titularidade aplicada ANTES da busca (o filtro por documento também fica restrito). Busca por documento = igualdade exata via hash cego HMAC (`cpf_hash`/`cnpj_hash`); ILIKE parcial por documento é impossível por natureza (LGPD C6). **Não converter para comparação em texto puro.**
5. **Prazos** — `deadlines.py:62-76`: prazo avulso é pessoal (`responsavel = uid`); com caso segue carteira.
6. **Documentos** — `documents.py:534-574`: piso de confidencialidade para `<socio`; cliente_externo com `client_id` vê só `normal` do próprio cliente; não-gestão = case da carteira ∪ client da carteira ∪ upload próprio sem vínculos. **OCR full-text não entra em cursor nem em log.**
7. **Ownership canônico** — `ownership.py`: `is_gestao` = socio+ (7+); `pode_ver_todos` = admin+ (8+); `verificar_acesso_caso` = 404 se inexistente/soft-deleted, gestão passa, carteira passa, **órfão só gestão**.
8. **cliente_externo** — barrado pelo AuthMiddleware fora de portal/auth/signatures/notifications; a Tarefa 3 não pode expor novos dados a esse perfil nem por nova rota.

## 4. Estado atual do frontend (fan-out e amostras)

### 4.1 CentralAtividades (`load()` em 957–1068; resumo em 1452–1478)
- `Promise.allSettled` de 3 chamadas: `/atividades` com `apenas_pendentes: false` (**feed inteiro, sem corte**), `/agenda-eventos/` com `page_size: 500`, `/deadlines/` com `status: ""` p1 `PRAZOS_PAGE_SIZE=200`.
- **N+1 explícito**: para cobrir `confirmado`/`ciencia_confirmada`, busca as páginas restantes de `/deadlines/` **em paralelo** até `PRAZOS_MAX_PAGINAS=10` ⇒ teto teórico de **2.000 prazos + feed completo de atividades** por render da Central.
- Enriquecimento por merge de id (agendaMap/prazoMap); sem os extras a Central mantém "Dar ciência" e perde "Confirmar" — **a Tarefa 3 não pode perder os botões Confirmar/Dar ciência/Reagendar/Concluir**.
- Resumo (1452–1478): `stats` conta o conjunto visível com `contextCaseId` mas **sem os filtros de tipo/urgência/situação** — proteção anti-auto-zerar dos cards (são botões de filtro). O novo `/atividades/resumo` deve preservar exatamente esta semântica.

### 4.2 DashboardUltra (`carregar()` em 218–267; decisões em 378–479; scores em 138–195)
- 7 chamadas paralelas: `/dashboard/`, `/atividades` (`apenas_pendentes: true`, **sem corte**), `/cases/` p1 s20, `/documents/` p1 s1 (só para o `total` de 7 dias), `/tasks/` `minhas: true` (**sem corte**), `/saneamento/integridade` (admin), `/legal-docs/` p1 s30.
- `decisoesHoje` = top-3 por prioridade sobre **amostras do navegador**: peças (30), casos (p1 = 20), tarefas (`minhas`, completo), atividades (feed pendente completo). Com carteira > 20 casos ou > 30 peças, os badges e decisões divergem do real — a Tarefa 4 corrige com agregação autorizada no backend.
- Fórmulas a espelhar server-side (paridade de decisão, Tarefa 4):
  - `scoreCaso`: encerrado/arquivado −100; aberto +40; prioridade urgente +30 / alta +20; risco crítico +35 / alto +25; `proxima_acao_prazo`: vencido +100 / hoje +90 / ≤3d +70 / ≤7d +45 / ≤30d +15; por atividade do caso: urgencia vencido +120 / critico +95 / atencao +55, e dias <0 +120 / 0 +85 / ≤3 +60 / ≤7 +35.
  - `scoreTarefaHoje`: prioridade urgente +50 / alta +30; sem data +10; vencida +80; hoje +60; concluída −5.
  - Prioridades das decisões: peça em_revisao 120 / corrigida 112; prazo vencido 118 / hoje 110 / futuro `94−dias`; tarefa = `scoreTarefaHoje`; risco crítico 88 / alto 76; desempate por inserção; dedup por `to|titulo`.

### 4.3 Casos (`load()` em 185–207)
- `/cases/` `page_size: 50` (page default 1), filtros search/area/status/advogado_id/arquivo, debounce 350 ms, guarda de corrida por `seq`. Clientes do filtro: `/clients/` `page_size: 100`; advogados: `/users/`. Paginação offset com `total` real do backend (o cursor não pode fingir `total` com valores de página — Tarefa 5 mantém offset como default).

## 5. Hipóteses de gargalo (a provar/refutar na matriz da seção 6)

| # | Hipótese | Onde | Como prova/refuta |
|---|---|---|---|
| A | Feed `/atividades` sem corte domina a primeira pintura da Central e do Hoje (payload + serialização + scan UNION ALL) | `atividades.py:45-54`; Central 972; DashboardUltra 226 | p50/p95 + KB do feed; contagem de linhas por ator |
| B | N+1 de deadlines (até 10×200) multiplica queries e payload por render da Central | Central 993-1020 | nº de chamadas HTTP por tela; KB agregado |
| C | `count(*)` + OFFSET degradam em página profunda nas 4 listas | cases/clients/deadlines/documents | EXPLAIN p/ page 1 vs page 100 do mesmo filtro |
| D | ILIKE `%…%` em `titulo`/`ocr_text` (documents) e 4 colunas (cases) não usa índice btree; custo por busca | documents 601-612; cases 148-154 | EXPLAIN BUFFERS com termo presente/ausente |
| E | Ordenações sem tiebreaker geram páginas instáveis/deleção-duplicada sob paginação | cases/clients (created_at), deadlines (data_prazo), atividades (data) | dataset com valores empatados; varrer 3 páginas consecutivas |
| F | KPI do Hoje conta amostras do navegador ⇒ divergência de decisão com carteira grande | DashboardUltra 321-338, 378-479 | dataset >50 casos/>30 peças; comparar badge vs banco |
| G | `/tasks/` sem corte devolve kanban inteiro (inclui concluídas antigas) | tasks.py:102-140 | linhas devolvidas vs visíveis; p95 |
| H | 7 chamadas paralelas do Hoje saturam pool de conexão em horário de pico | DashboardUltra 223-236 | contagem de queries por tela; p95 agregado |

## 6. Matriz de medição e método

### 6.1 Formato da tabela (uma linha por rota × ator × filtro)
`rota | ator | filtros | linhas visíveis | cold/warm | execuções | p50/p95 (ms) | payload (KB) | queries/tela | buffers | plano (resumo) | erro`

### 6.2 Células a preencher (primeira onda)
| Rota | Atores | Filtros/params |
|---|---|---|
| `GET /api/atividades` | advogado_A, advogado_B, socio, secretaria, cliente_externo | `apenas_pendentes=true` e `false` |
| `GET /api/tasks/` | advogado_A, socio | default; `minhas=true`; `case_id` do caso A1 |
| `GET /api/cases/` | advogado_A, socio | p1 e p100; `search` com e sem hit; `arquivo=todos` |
| `GET /api/clients/` | advogado_A, socio | p1 e p100; `search` nome; `search` CPF completo |
| `GET /api/deadlines/` | advogado_A, socio | `status=pendente` (default) e `status=""`; p1 e p50 |
| `GET /api/documents/` | advogado_A, socio, cliente_externo | p1 e p100; `search` título; `search` termo só no OCR |
| `GET /api/dashboard/` | socio, advogado_A, secretaria | — (cache quente/frio) |
| Tela Central (agregado) | advogado_A | carga inicial completa |
| Tela Hoje (agregado) | advogado_A, socio | carga inicial completa |

### 6.3 Procedimento
1. Dataset sintético carregado (seção 7) num PostgreSQL **isolado** de homolog; migrations no HEAD.
2. Por célula: 5 execuções cold (pool reciclado/`DISCARD ALL`) + 30 warm; registrar p50/p95, KB serializado, nº de queries SQL (log do driver) e erro.
3. Para as queries dominantes de cada célula: `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` — **somente SELECT**; registrar desvio estimado vs real, método de sort, temp IO.
4. Repetir a matriz inteira **2×** para medir ruído.

### 6.4 Critério de ganho (válido para as Tarefas 2–6)
- p95 da célula alvo deve cair **> 20%** E a queda deve superar **2× a amplitude entre rodadas** da mesma célula. Caso contrário, a mudança é revertida (vale para índices da Tarefa 6 e para manter o cursor da Tarefa 2).
- Testes DB (`*_dblevel.py`) com `RUN_DB_TESTS=1`: **SKIP não é PASS**. Sem Postgres no ambiente, o gate da tarefa não foi cumprido.

## 7. Dataset sintético de homolog (plano + executor)

### 7.1 Princípios
- Banco **isolado** (`ejc_homolog_perf` ou schema dedicado), **nunca** produção nem o banco do CI de funcionais. O executor `scripts/perf/seed_homolog.py` recusa qualquer `DATABASE_URL` que não contenha o marcador `homolog_perf` (guarda anti-produção em dupla checagem: nome do banco E variável `SEED_HOMOLOG_PERF=1` afirmada).
- Migrations aplicadas até o HEAD antes do seed (`alembic upgrade head` é responsabilidade do ambiente, não do seed).
- Seed **idempotente por marcador**: se `users.email` do ator âncora existir, o seed termina com as contagens atuais (reexecutável sem duplicar).
- Nada de PII real: CPFs sintáticos válidos gerados de tabela fixa; `ocr_text` com lorem jurídico; nomes fictícios.

### 7.2 Atores (RBAC matrix viva do dataset)
| Ator | Papel | Vínculo |
|---|---|---|
| `perf-superadmin` | superadmin | — |
| `perf-socio` | socio | vê tudo |
| `perf-advogado-a` | advogado | dono da carteira A |
| `perf-advogado-b` | advogado | dono da carteira B |
| `perf-auxiliar-a` | advogado_auxiliar | auxiliar do caso A1 (e só dele) |
| `perf-estagiario` | estagiario | **sem vínculo** com nenhum caso |
| `perf-secretaria` | secretaria | intake, sem carteira |
| `perf-cliente-x` | cliente_externo | `client_id` do cliente X |

### 7.3 Volumes mínimos (dimensões que disparam as hipóteses)
| Tabela | Volume | Distribuição |
|---|---|---|
| clients | 200 | 60 ligados à carteira A, 60 à B, 80 neutros; cliente X com `cpf` conhecido |
| cases | 60 | 25 carteira A, 25 carteira B, 10 **órfãos** (só gestão); A1 = caso do auxiliar; ≥30 abertos com `proxima_acao_prazo` espalhada |
| deadlines | 1.500 + **12.000** concluídos antigos | 20 com `data_prazo` **idêntica** (tie test); mistura pendente/vencido/concluído; avulsos com `responsavel` |
| tasks | 800 | 30 **caseless** (resp/criador alternando), 20 com `data_limite` **idêntica**, resto por caso A/B |
| agenda_eventos | 2.000 | 500 futuros pendentes |
| djen_comunicacoes | 1.200 | 400 não processadas |
| documents | 3.000 | ≥10 `restrito/confidencial` **no caso A** (prova de piso <socio e de invisibilidade p/ B); `ocr_text` com termo canário |
| fees | 300 | pendente/atrasado/pago nos casos A/B |
| legal_docs | 40 | 15 `em_revisao`/`corrigida` (fila HITL > 30 p/ provar a amostra) |

### 7.4 Aserções pós-carga (bloqueiam o uso do dataset se falharem)
1. Contagem por ator conferida por SQL dedicado (ex.: prazos visíveis a advogado_A = pendentes carteira A + avulsos dele; visíveis a B ≠ A).
2. Documento restrito do caso A **invisível** para advogado_B e para o cliente X.
3. Caso órfão invisível para estagiário/advogados (só gestão).
4. Prazos empatados devolvem ordem determinística ao menos com `id` no desempate do cursor.
5. Registro obrigatório no log de seed: **schema (HEAD alembic) · commit do executor · contagens por tabela** — cola da linha "linhas visíveis" da matriz.

## 8. Orçamentos (budgets) por alvo — aprovação prévia dos números

| Alvo | Métrica | Orçamento | Base da comparação |
|---|---|---|---|
| Central: primeira tela | p95 (agregado HTTP) | ≤ 800 ms | matriz 6.2 (baseline) |
| Central: primeira tela | payload agregado | ≤ 120 KB | idem |
| Central: chamadas por carga | nº HTTP | 2 (feed + resumo) [+1 dashboard] | hoje: 3 + até 9 extras |
| `GET /api/dashboard/hoje` (T4) | p95 / payload / queries | ≤ 400 ms / ≤ 30 KB / ≤ 6 | novo |
| Hoje: contagens | exatidão | 100% com carteira >50 casos e >30 peças | dataset 7.3 |
| `GET /api/tasks/?pagination=cursor` (T2) | p95 (página 50) | ≤ 300 ms | baseline da mesma célula |
| Listas cursor (T5) | p95 p1 | ≤ 500 ms | baseline p1 offset |
| Listas cursor (T5) | deep page 100 | sem regressão >10% vs baseline | EXPLAIN + p95 |

## 9. Pendências de confirmação semântica (bloqueiam T3/T4 — decidir antes do código)

1. **Data operacional única do Hoje**: `dashboard.py` usa `date.today()`; `deadlines.py`/`core.clock` usam `hoje_operacional()`. Proposta: `hoje_operacional()` como fonte única do `/dashboard/hoje` — **aguardando aprovação do titular**.
2. **Escopo do resumo da Central**: manter "conta todo o caso (contextCaseId) ignorando filtros de UI" — proposto igual ao atual; confirmar.
3. **Definição de `ativos`**: `STATUS_ABERTOS` via `core/status_caso.py` (fonte única do `GET /cases/stats`) — o `/dashboard/hoje` usará a MESMA fonte; sem nova definição.
4. **Badges por carteira inteira**: contagens do Hoje consideram todo o conjunto permitido pela visibilidade (não amostra de 20/30/50) — requisito do plano, sem decisão pendente.

## 10. Gates por tarefa e rollout/rollback

| Tarefa | Gate de saída |
|---|---|
| T1 (este doc) | baseline reproduzível: dataset asserido + matriz preenchida 2× |
| T2 cursor tasks | `pagination=cursor` opt-in; shape/rota legacy intactos; visibilidade 109-130 preservada; testes unitários + `test_tasks_pagination_dblevel.py` (SKIP≠PASS); manter só se 6.4 ok |
| T3 atividades/resumo | flag `pagination=cursor`; botões Confirmar/Dar ciência/Reagendar/Concluir intactos; cliente_externo sem dado novo; resumo não auto-zera; rollback = flag off |
| T4 dashboard/hoje | `/api/dashboard/` **inalterado**; contagens exatas >50/>30; sem cross-user (matriz 7.2); `hoje_operacional` decidido em 9.1 |
| T5 cursor nas 4 listas | offset default intacto; filtro mudou ⇒ cursor rejeitado/renovado; `total` real não falsificado; sem índice novo antes da T6 |
| T6 índices | só com EXPLAIN provando ganho > 6.4; revision nova de HEAD real (`164_commission_rules`); DDL e lock avaliados (CONCURRENTLY quando aplicável); down() verificável |
| T7 gate final | p95 −20% mínimo nas rotas críticas; zero falha de autenticação/negócio/integridade; rollout em ondas **backend → Central → Hoje → listas**; rollback: primeiro flag do cliente, depois flag do servidor, por último revert |

## 11. Registro de execução (a preencher por rodada)

| Rodada | Data | Ambiente | Dataset (commit/contagens) | Matriz preenchida | Ruído (amplitude p95) | Observações |
|---|---|---|---|---|---|---|
| 1 | _pendente_ | homolog | _pendente_ | ☐ | _pendente_ | |
| 2 | _pendente_ | homolog | _pendente_ | ☐ | _pendente_ | |

