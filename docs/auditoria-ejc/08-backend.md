# 08 — Backend (Fase 8)

> Método: graphify para localizar → leitura do arquivo real → AST sobre `app/routers/` → **app
> FastAPI montado de verdade** (`from app.main import app`, **830 rotas**) → requisições via
> `TestClient` com JWT forjado. Os três achados P0 foram **provados em runtime**, não inferidos.
> Suíte completa executada: **4 463 passed, 166 skipped** em 67 s.

## 1. Inventário de rotas

| Métrica | Valor |
|---|---|
| Arquivos em `app/routers/` | 163 (**162 módulos** + `__init__.py`) |
| Módulos registrados em `main.py` | 157 (161 chamadas `include_router`) |
| Registrados por side-effect em `routers/__init__.py` | 5 |
| **Routers órfãos (código morto)** | **0** |
| **Rotas montadas no app real** | **830** |

> **Correção ao `CLAUDE.md`:** são **162** routers, não 163 — o número inclui o `__init__.py`.
> E **nenhum** está órfão.

Os 161 `include_router` cobrem 157 módulos de `app/routers`, 3 de `app/integrations`
(`main.py:483-485`) e `ia_saude.router_status` (segundo router do mesmo módulo, `main.py:375`).

**P2 — 5 routers registrados fora do `main.py`** (`routers/__init__.py:24-30`): `entrada_universal`,
`entrada_universal_vinculo`, `defesas_revisoes`, `defesas_revisoes_pacote_seguro`,
`defesas_revisoes_avancado`. Não são órfãos, mas são **invisíveis para quem lê só o `main.py`**.
A Onda 3 migrou **cinco outros** grupos de side-effect para registro explícito
(`main.py:427-443`, travado por `tests/test_rotas_registro_explicito.py`) e deixou estes de fora —
mesmo padrão, meia correção.

## 2. Superfície dupla `/api` e `/api/v1`

**Um único middleware, sem duplicação de routers.** `core/api_version_middleware.py:34-42`
reescreve `scope["path"]` de `/api/v1…` para `/api…` **antes do roteamento**; `:8` isenta
`/api/health`, `/api/docs`, `/api/openapi.json`; `:44-63` adiciona `content-location` +
`x-ejc-api-version: 1` (canônico) ou `deprecation: true` + `link: rel="successor-version"`
(legado). Registrado em `main.py:287`. A autenticação normaliza por conta própria
(`auth_middleware.py:38-50`), para não depender da ordem dos middlewares.

Confirmado em runtime: `/api/cases` e `/api/v1/cases` respondem ambas.

**Classificação: FUNCIONAL / P3.** Ressalva real: qualquer regra por path (rate limit de borda,
WAF, log, cache no Nginx) precisa cobrir **os dois** prefixos.

---

## 🔴 3. P0-1 — 27 chamadas do frontend caem em 404

**Oito routers declaram `prefix="/v1/…"` no próprio `APIRouter`** e depois são montados sob
`prefix="/api"`:

| Router | Prefixo declarado |
|---|---|
| `despesas.py:24` | `/v1/despesas` |
| `office_contracts.py:20` | `/v1/office-contracts` |
| `partner_withdrawals.py:10` | `/v1/partner-withdrawals` |
| `kanban.py:21` | `/v1` |
| `datajud.py:17` | `/v1/datajud` |
| `regulatorio.py:19` | `/v1/regulatorio` |
| `pending_items.py:11` | `/v1/clients` |
| `whatsapp.py:34` | `/v1/whatsapp` |

O path registrado vira `/api` + `/v1/despesas` = **`/api/v1/despesas`**. Mas o middleware come o
`/api/v1` de **qualquer** requisição antes do roteamento:

| Requisição | Após o middleware | Resultado |
|---|---|---|
| `/api/despesas` | `/api/despesas` | 404 |
| `/api/v1/despesas` | `/api/despesas` | **404** |
| `/api/v1/v1/despesas` | `/api/v1/despesas` | **casa a rota** |

**Provado em runtime** (500 = rota casou e o DB indisponível estourou; 404 = nenhuma rota):

```
404  /api/despesas                     500  /api/v1/v1/despesas
404  /api/v1/despesas                  500  /api/v1/v1/office-contracts
404  /api/v1/office-contracts          500  /api/v1/v1/partner-withdrawals
404  /api/v1/partner-withdrawals       500  /api/v1/v1/kanban-columns
404  /api/v1/kanban-columns            500  /api/v1/v1/regulatorio/digest-semanal
```

Isto reproduz **exatamente** a evidência da auditoria externa (`/api/v1/v1/despesas` = 200,
`/api/v1/despesas` = 404) e **fecha o item `[INVESTIGAR]`** com causa raiz.

### 3.1 O frontend não compensa mais — a compensação virou a causa

O `CLAUDE.md` diz que "o frontend compensa chamando `/v1/x`". **Deixou de valer.**

```
frontend/src/lib/api.ts:9    baseURL: "/api/v1"
frontend/src/lib/api.ts:23   else if (url.startsWith("/v1/")) config.url = url.slice("/v1".length);
```

`api.get("/v1/despesas")` → interceptor apara → `/despesas` → baseURL → o navegador envia
`/api/v1/despesas` → middleware → `/api/despesas` → **404**.

**27 call sites em 9 páginas** ficam sem rota — módulos inteiros mortos na UI:

| Página | Chamadas | Módulo morto |
|---|---|---|
| `Despesas.tsx:118,143,190,192,203,222` | 6 | Financeiro — despesas |
| `OfficeContracts.tsx:99,102,163,165,183` | 5 | **Contratos do Escritório (página inteira)** |
| `DossieCliente.tsx:220,246,262,280,1001` | 5 | Pendências do cliente |
| `Sociedade.tsx:125,202,228` | 3 | Retiradas de sócios |
| `DespesasRecorrentes.tsx:51,76` | 2 | Financeiro — recorrentes |
| `Kanban.tsx:69,110` | 2 | Kanban de casos |
| `DataJudBusca.tsx:54,71` | 2 | **DataJud (página inteira)** |
| `FinanceiroDashboard.tsx:149` | 1 | Exportação CSV |
| `RadarRegulatorio.tsx:33` | 1 | Digest semanal |

Como as páginas têm tratamento de erro, **o usuário não vê crash** — vê "falha ao carregar" ou
lista vazia. Por isso o defeito sobreviveu sem ser notado.

**Classificação: QUEBRADA / P0.** Correção mínima: remover o `/v1/` do `prefix=` desses 8 routers
(o `/api/v1` público continua entregue pelo middleware). **É mudança de contrato público → exige
autorização do titular (§10 da governança).**

**Convergência de método:** este achado foi obtido por **quatro** caminhos independentes — trace do
middleware, diff de contrato estático, *probe* com o axios real, e requisição no app montado.

---

## 🔴 4. P0-2 — o verificador de contrato está cego para exatamente este bug

`backend/app/utils/api_contract.py:83-93` (`_final_url`) concatena `AXIOS_BASE_URL + raw`
**sem reproduzir a poda de prefixo** de `api.ts:21-23`. Verificado por mim: a função faz

```python
if prefix_is_axios:
    if not norm.startswith("/"): return None
    norm = AXIOS_BASE_URL + norm        # <- nenhuma poda de /v1, /api, /api/v1
```

Para `raw = "/v1/despesas"` ele calcula `/api/v1/v1/despesas`, que `_internal_api_url` (`:96-106`)
converte em `/api/v1/despesas` — **e casa com a rota registrada**.

**O checker valida a URL que o navegador deixou de enviar.** `tests/test_api_contract.py` passa
(39 testes verdes) enquanto a tela dá 404.

**Classificação: QUEBRADA (falso verde) / P0.** É o guarda-corpo desta classe exata de defeito, e
está cego para ela. **Corrigir o checker antes de corrigir os routers** — senão a regressão volta.

---

## 🔴 5. P0-3 — `GET /api/rag/docs` retorna 500 sempre

`app/services/ai_core_hardening_patch.py:188-193` troca o callable da rota por atribuição direta:

```python
for route in rag.router.routes:
    if getattr(route, "name", "") == "listar_docs":
        route.endpoint = _listar_docs_escopado
        route.dependant.call = _listar_docs_escopado
```

Mas `main.py:424` (`include_router`) roda **depois** e reconstrói o `dependant` a partir da
assinatura do novo endpoint. E a assinatura (`ai_core_hardening_patch.py:111-117`), **verificada
por mim**, é:

```python
async def _listar_docs_escopado(page=1, page_size=20, categoria=None, db=None, cu=None):
```

**`db` e `cu` não têm `Depends()`.** FastAPI trata parâmetro sem anotação e com default como
**query param**. Introspecção do app montado:

```
QUERY_PARAMS = ['page','page_size','categoria','db','cu']   ← db e cu viraram query params
SUBDEPS      = []                                           ← get_db e get_current_user sumiram
```

Requisição real com JWT válido:
`500 GET /api/rag/docs → AttributeError("'NoneType' object has no attribute 'execute'")`

Três consequências, **nenhuma dependente do banco** (o erro é `NoneType`, então **acontece igual em
produção**):

1. A rota retorna **500 sempre**.
2. O escopo de visibilidade que o patch existe para instalar (`:130-145`) **nunca executa** — e a
   implementação original de `rag.listar_docs` foi substituída. **O hardening é nominal.**
3. Foi a única rota do app com esse sintoma (varredura das 830 procurando query params
   `db`/`cu`/`user`/`session`/`request`).

**A suíte inteira (4 463 testes) passa sem tocar nesta rota.**
**Classificação: QUEBRADA / P0.**

---

## 6. Autenticação e RBAC por rota

### 6.1 Allowlist pública — `core/auth_middleware.py:22-35`

`/api/auth/login|refresh|logout|recuperar-senha|redefinir-senha` · `/api/health` · `/api/docs` ·
`/api/openapi.json` · `/api/webhooks/` · `/api/calendar/` · `/api/data-rooms/acesso/` ·
`/api/rag/knowledge-base/`

Mecânica **correta e defensiva**: `_api_path_interno` (`:38-50`) aplica `posixpath.normpath`
**antes** da comparação. Confirmado em runtime: `GET /api/health/../cases` → **401**;
`GET /api/v1/../cases` → **401**. Gates encadeados: troca de senha obrigatória (`:143-152`), 2FA
(`:169-189`), confinamento de `cliente_externo` (`:191-204`).

**P2 —** `_is_publica` (`:60-65`) retorna `True` para **qualquer path que não comece com `/api/`**.
Hoje só alcança `/docs/oauth2-redirect` (e só fora de produção). É **default aberto**: rota futura
montada fora de `/api` nasce pública, contra a regra crítica nº 5 do `CLAUDE.md`.

**P2 —** o gate de `cliente_externo` lê `payload["role"]` do **JWT**, não do banco. Rebaixamento de
papel só vale após expirar o access token.

### 6.2 Cobertura de RBAC — medida no app montado, não por regex

| Categoria | Rotas |
|---|---|
| `require_roles`/`require_admin` na cadeia de DI | **198** |
| Só `get_current_user` (papel/ownership inline, quando existe) | **612** |
| Sem nenhuma dependency de autenticação | **20** (allowlist deliberada + o defeito §5) |

Refinando as 612 por AST com expansão de helpers locais: **~145 fazem checagem de papel inline** e
**~122 fazem checagem de ownership**. O padrão inline é sólido nos módulos examinados
(`gestao_societaria.py:96,120,138`; `exito_rateio.py:32,101`; `fees.py:62-67`;
`data_room.py:347-352`).

> **A cobertura de RBAC é melhor do que a auditoria externa sugeria.**

### 6.3 Endpoints sensíveis sem checagem de papel

Todos exigem JWT (o middleware garante) e barram `cliente_externo`. Mas **qualquer perfil interno
— inclusive `secretaria` (2) e `estagiario` (3) — passa**:

| Endpoint | Evidência | O que faz | Classe / P |
|---|---|---|---|
| `POST /api/victory_vault/teses` | `victory_vault_router.py:8,11` | grava tese no cofre institucional; sem RBAC, sem rate limit, sem audit log, sem service | **INSEGURA / P1** |
| `POST /api/victory_vault/modelos` | `victory_vault_router.py:8,19` | idem, modelos de documento | **INSEGURA / P1** |
| `POST /api/document-templates/generate` | `peca_geracao_router.py:28-30` | gera documento jurídico sem vínculo a caso e **sem gate de advogado** — enquanto o caminho gêmeo exige (`kit_documental.py:58`, `cases.py:698-704`) | **INSEGURA / P1** |
| `POST /api/prompts-biblioteca/` | `prompts.py:42` | cria prompt sem RBAC | **INSEGURA / P2** |
| `POST /api/prompts-biblioteca/{id}/executar` | `prompts.py:59-65` | dispara o orchestrator **sem rate limit** — custo de provedor sem teto | **INSEGURA / P2** |

Descartados como falsos positivos após leitura: `credential_vault.py:59`, `module_help.py:20-21`,
`clients.py:35,41`, `sociedades_cliente.py:51,57`, `lgpd_registros.py:75,81`, `legal_chat.py:51`,
`honorarios_oab.py:141`, `teses_v4.py:96`, `rag.py:598`, `ai_core.py`, `cases.py:700`,
`fees.py:73`, `exito_rateio.py:107`, `dashboard.py:219`.

## 7. Qualidade

### 7.1 Rotas duplicadas — nenhuma

Sobre as 830 rotas: **0 colisões exatas** e **0 sombreamentos** (rota dinâmica antes de estática
equivalente). `module_help.py:82` (`/{module_key:path}`) é declarado **depois** das estáticas — na
ordem certa.

**Sobreposição semântica** — 23 prefixos servidos por 2+ routers. Os relevantes:

| Prefixo | Routers | Classe / P |
|---|---|---|
| `/ai` | `ai.py`, `ai_core.py`, `ai_skills.py`, `ai_tools.py`, `ia_extra.py` | **DUPLICADA / P2** — 5 fachadas de IA |
| `/teses` vs `/teses-v4` | `teses.py`, `teses_v4.py` | **OBSOLETA / P3** — já `deprecated=True` e delegando; pronto para remoção |
| `/data-rooms` vs `/data-room-v4` | idem | **OBSOLETA / P3** |
| `/bank-analysis` vs `/analise-bancaria` | dois vocabulários (PT/EN), **sem `deprecated`** | **DUPLICADA / P2** |
| `/cases` (15 routers) vs `/casos` (7) | dois idiomas para a mesma entidade | **FUNCIONAL C/ RESSALVAS / P2** |

### 7.2 Regra de negócio no router

| Arquivo | Linhas | Endpoints | imports de service |
|---|---|---|---|
| **`routers/ramos.py`** | **4 519** | **82** | 4 |
| `routers/workflow.py` | 522 | — | **0** (23 queries direto) |
| `routers/atendimentos.py` | 1 060 | — | 1 (22 queries) |
| `routers/data_room.py` | 726 | — | 1 (21 queries) |

**`ramos.py` é o achado central — PARCIAL / P1.** Seis verticais jurídicas + calculadoras num
arquivo de 4,5 mil linhas. **Regra jurídica com vigência datada** (`TETOS_DEPOSITO_RECURSAL`,
`:63-96`; `_teto_deposito_para()`, `:97-105`; uso em `:1262` — art. 899 §§1º-4º da CLT) mora no
router, não em service testável. Colide com a **regra 5 do `CLAUDE.md`** ("toda regra jurídica
precisa de fonte oficial, vigência e teste"). O próprio arquivo reconhece a dívida em `:57-59`
("ATUALIZAÇÃO ANUAL OBRIGATÓRIA").

### 7.3 Dez maiores services (56 988 linhas em ~150 módulos)

```
1894  scheduler.py              878  motor_peca_service.py     728  documento_service.py
1365  peca_service.py           829  google_drive_service.py   690  backup_service.py
1307  ai_gateway.py             744  legal_case_orchestrator.py
1169  legal_chat_service.py     739  diagnostico_service.py
1110  ai_service.py
```

**P2 — `scheduler.py` (1 894 linhas)** é o mais preocupante: ponto único de falha operacional, e o
`CLAUDE.md` já registra que pressupõe `--workers 1`.

### 7.4 Acesso direto ao banco em routers

**95 dos 820 endpoints (11,6 %)** executam **SQL cru** via `db.execute(text(...))`, em **38
routers** — concentrados em `novos_modulos.py` (12), `partner_withdrawals.py` (10),
`extratos.py` (9), `despesas.py` (9). Além disso, **555 ocorrências de `select(...)`** em routers.

**Não há injeção** — as queries lidas usam parâmetros vinculados. O custo é de manutenção: a camada
"routers finos → services" descrita no `CLAUDE.md` é **aspiração, não realidade, em ~1/3 dos
routers**. **FUNCIONAL COM RESSALVAS / P2.**

### 7.5 Transações multi-tabela — as hipóteses da auditoria anterior

**Confirmadamente ATÔMICOS:**
- `POST /cases/{id}/converter-judicial` — `conversao_caso.py:299` (INSERT `processes`), `:312`
  (UPDATE `cases`), `:317` (INSERT `case_movimentos`), `:322` (audit) → **um `db.commit()` em `:327`**.
- Sala Jurídica → Caso — `legal_chat_service.py:893-937` tudo em `flush`, com **um commit no
  router** (`legal_chat.py:352`), lock pessimista `with_for_update()` (`:829-835`) e limpeza de
  arquivos físicos em falha (`:938-940`).

**"Conversão perde `descricao_fatos`" — [NÃO CONFIRMADO no código].**
`legal_chat_service.py:906` grava `descricao_fatos=payload.descricao` explicitamente. O campo é
`Optional` no schema (`schemas/legal_chat.py:107`) — uma perda observada em produção viria do
**frontend não enviá-lo**.

**"Exclusão de caso não cascateia para as peças" — [NÃO CONFIRMADO como defeito vivo].**
`cases.py:613-691`: o DELETE é **soft** (`:684`) e **recusa 422 se houver prazo pendente, honorário
em aberto ou peça protocolada** (`:646-681`). As satélites não recebem `deleted_at`, mas a
visibilidade é herdada na leitura (`legal_docs.py:310-321`, `deadlines.py:43`, `fees.py:52,163`).
**O cenário de peça órfã visível está fechado no commit auditado.**

**Não atômico, com ressalva — P2:** `entrada_universal.py:186` (`processar`) faz **6 commits**
(`:216,246,265,299,303,306`) — um por item do lote. Falha no meio deixa lote parcialmente
processado; mitigado por `batch.status="erro"`.
*(`nfse.py:558` e `auth.py:179` também têm múltiplos commits, mas são **deliberados e corretos** —
reserva de referência antes de chamada externa e contadores de lockout que precisam sobreviver ao 401.)*

## 8. Achados consolidados

| # | Achado | Classe | P |
|---|---|---|---|
| 1 | 27 chamadas em 404 pelo prefixo `/v1` em 8 routers | QUEBRADA | **P0** |
| 2 | `api_contract.py` não modela o interceptor → falso verde sobre o achado 1 | QUEBRADA | **P0** |
| 3 | `GET /rag/docs` 500 sempre; hardening de escopo nunca executa | QUEBRADA | **P0** |
| 4 | `victory_vault` grava no cofre só com JWT | INSEGURA | **P1** |
| 5 | `document-templates/generate` sem gate de advogado | INSEGURA | **P1** |
| 6 | `ramos.py` — 4 519 linhas, regra jurídica com vigência no router | PARCIAL | **P1** |
| 7 | `prompts-biblioteca` cria e executa IA sem RBAC nem rate limit | INSEGURA | P2 |
| 8 | 5 routers registrados por side-effect | FUNCIONAL C/ RESSALVAS | P2 |
| 9 | `_is_publica` libera tudo fora de `/api/` | INSEGURA | P2 |
| 10 | 95 endpoints com SQL cru + 555 `select()` em routers | FUNCIONAL C/ RESSALVAS | P2 |
| 11 | 5 fachadas em `/ai`; `bank_analysis` vs `analise_bancaria` | DUPLICADA | P2 |
| 12 | `cliente_externo` avaliado pelo claim do JWT | FUNCIONAL C/ RESSALVAS | P2 |
| 13 | `entrada_universal.processar` — 6 commits | PARCIAL | P2 |
| 14 | `teses_v4`, `data_room_v4` prontos para remoção | OBSOLETA | P3 |
| 15 | `scheduler.py` 1 894 linhas, `--workers 1` | FUNCIONAL C/ RESSALVAS | P2 |

## 9. Observação metodológica

> **A suíte inteira passa — 4 463 testes — com três defeitos P0 vivos, dois deles verificáveis com
> uma única requisição HTTP.** Não há teste que faça request real contra `/api/rag/docs` nem contra
> os paths `/v1`.
>
> **O gap não é de cobertura de unidade — é de teste de superfície.** Nada exercita *"a URL que o
> navegador realmente envia bate numa rota que realmente responde"*. Essa é a lacuna estrutural
> mais cara desta auditoria, e explica por que os três P0 sobreviveram ao CI.
