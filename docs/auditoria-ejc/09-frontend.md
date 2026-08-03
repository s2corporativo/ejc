# 09 — Frontend (Fase 9)

> **Estado:** os três P0 foram **corrigidos** neste mesmo PR (ver `00-resumo-executivo.md`). Os itens marcados como quebrados por causa do prefixo `/v1` ou de `GET /api/rag/docs` **já respondem**. O texto segue no tempo do diagnóstico; P1/P2/P3 continuam pendentes.


> `npm run lint` (tsc --noEmit) → **exit 0**. `npm test` (vitest) → **54 arquivos, 343 testes,
> todos passando**, 34,3 s. Nada foi alterado.

## 1. Rotas

`STAFF_ROUTES` tem **42 entradas**; `LEGACY_REDIRECTS` tem **35**. `App.tsx:139-155` consome o
registry — **não há rota de módulo solta**.

Grupos de papel (`moduleRegistry.tsx:39-54`): `gestores` = superadmin/admin/socio ·
`administradores` = superadmin/admin · `financeiro` = gestores + financeiro · `juridico` =
gestores + advogado/advogado_auxiliar/estagiario · `compliance` = gestores + advogado ·
`clientes` = gestores + advogado/secretaria. **TODOS** = qualquer papel exceto `cliente_externo`
(barrado por `StaffOnly`, `RouteGuards.tsx:30-37`).

| URL | Componente | Papéis |
|---|---|---|
| `/` | `Dashboard` → `DashboardModern` | TODOS |
| `/casos` · `/casos/:id` · `/casos/:id/jornada` | `Casos`, `CasoDetalhe`, `JornadaCaso` | TODOS |
| `/casos/novo` | `Casos` (wizard) | clientes |
| `/casos/:id/entrevista` | `EntrevistaInteligente` | compliance |
| `/clientes` · `/clientes/:clientId` | `Clientes`, `DossieCliente` | clientes / TODOS |
| `/cadastro-manual` · `/crm-leads` | `CadastroManual`, `CRMLeads` | clientes / TODOS |
| `/sala-juridica` · `/raio-x` | `SalaJuridica`, `RaioXProcesso` | juridico |
| `/areas-de-atuacao` · `/areas-de-atuacao/:slug` | `RamosHub`, `ramos/RamoBase` | juridico / TODOS |
| `/atividades` | `Central` | TODOS |
| `/legado/prazos|tarefas|intimacoes|suspensoes` | `Prazos`, `Tarefas`, `Intimacoes`, `Suspensoes` | TODOS |
| `/documentos` · `/pecas` · `/assinaturas` | `GestaoDocumental`, `Pecas`, `Assinaturas` | TODOS |
| `/workflow` · `/checklists` | `Workflow`, `Checklists` | TODOS |
| `/inteligencia` · `/prompts` | `InteligenciaWorkspace`, `Prompts` | juridico |
| `/datajud` · `/diario-oficial` · `/radar-regulatorio` · `/noticias` | — | TODOS |
| `/compliance/radar` | `RadarCompliance` | compliance |
| `/financeiro` | `FinanceiroWorkspace` | financeiro |
| `/produtividade` | `Produtividade` | **TODOS** ⚠️ (ver §6) |
| `/configuracoes` · `/ajuda` · `/ferramentas` | — | TODOS |
| `/ia-governanca` · `/diagnostico` · `/auditoria` · `/mapa-modulos` · `/lixeira` | — | gestores |
| `/usuarios` | `Usuarios` | administradores |

Rotas em `App.tsx` **fora** do registry — todas legítimas e comentadas: `/login`,
`/recuperar-senha`, `/redefinir-senha`, `/trocar-senha`, `/configurar-2fa` (pré-sessão);
`/portal` + 6 filhas (`App.tsx:106-123`, guarda `PortalOnly`); `/ia-governanca/provedores`
(`:159-166`); 3 redirects dinâmicos (`:178-189`); `*` → `NotFound`.

**Verificações negativas — nada encontrado:**

| Hipótese | Resultado |
|---|---|
| Páginas órfãs | **nenhuma** — dos 89 arquivos em `src/pages/`, 54 são roteados e 35 são subcomponentes de abas |
| Entrada do registry para componente inexistente | **nenhuma** — `tsc --noEmit` exit 0 prova que os 54 `lazy(() => import(...))` resolvem |
| Rotas duplicadas | **nenhuma** — 0 paths repetidos, 0 colisões entre os três conjuntos |

*(`/casos` e `/casos/novo` compartilham o componente `Casos`, mas `Casos.tsx:335` chama
`resolverModoNovoCaso(location.pathname, …)` — é **modo**, não duplicata.)*

**P3 — OBSOLETA:** `/legado/prazos`, `/legado/tarefas`, `/legado/intimacoes`, `/legado/suspensoes`
são 4 páginas completas, registradas e roteadas, mas **nenhum link no app inteiro aponta para
elas** — só alcançáveis digitando a URL. Superfície de manutenção sem usuário. Idem
`/legado/knowledge-hub`, redirect para URL que nunca foi pública.

---

## 🔴 2. P0 — as 27 chamadas `/v1/…` retornam 404

**A causa raiz está neste arquivo.** Diagnóstico completo em `08-backend.md` §3; aqui, o lado
frontend.

```ts
frontend/src/lib/api.ts:9    export const API_BASE_URL = "/api/v1";
frontend/src/lib/api.ts:21   if (url.startsWith("/api/v1/")) config.url = url.slice("/api/v1".length);
frontend/src/lib/api.ts:22   else if (url.startsWith("/api/"))  config.url = url.slice("/api".length);
frontend/src/lib/api.ts:23   else if (url.startsWith("/v1/"))   config.url = url.slice("/v1".length);
```

Prova executada com o **axios real instalado** + a lógica do middleware:

| URL chamada | enviada ao HTTP | após middleware | registrada no backend | |
|---|---|---|---|---|
| `/v1/despesas` | `/api/v1/despesas` | `/api/despesas` | `/api/v1/despesas` | **404** |
| `/v1/clients/ABC/pending-items` | `/api/v1/clients/…` | `/api/clients/…` | `/api/v1/clients/…` | **404** |
| `/clients/ABC/dossie` | `/api/v1/clients/…` | `/api/clients/…/dossie` | `/api/clients/…/dossie` | OK |
| `/v1/v1/despesas` | `/api/v1/v1/despesas` | `/api/v1/despesas` | `/api/v1/despesas` | OK |

> **A poda de `/v1/` na linha 23 é a causa raiz — não a compensação.** O `CLAUDE.md` registra o
> caso como "Resolvido em 2026-08-02: o bundle está certo"; **essa conclusão está incorreta**.

Páginas atingidas (27 call sites): `Despesas.tsx` (6), `OfficeContracts.tsx` (5, **página
inteira**), `DossieCliente.tsx` (5), `Sociedade.tsx` (3), `DespesasRecorrentes.tsx` (2),
`Kanban.tsx` (2), `DataJudBusca.tsx` (2, **página inteira**), `FinanceiroDashboard.tsx` (1),
`RadarRegulatorio.tsx` (1).

Como as páginas tratam erro, o usuário **não vê crash** — vê "falha ao carregar" ou lista vazia.
**Nenhum teste cobre a URL final do interceptor**: `lib/api.test.ts` exercita só o interceptor de
*resposta*.

### 2.1 Outras lacunas do interceptor

- **P1 — passe único.** `if/else-if` sem laço: `"/api/v1/v1/despesas"` cai só no primeiro ramo,
  vira `"/v1/despesas"`, e o resultado final é `"/api/v1/v1/despesas"` de novo. Um `while`
  fecharia.
- **P1 — URL relativa sem barra inicial.** `api.get("despesas")` não casa nenhum `startsWith`; o
  `combineURLs` do axios monta `/api/v1/v1/despesas`. Sem ocorrência hoje — armadilha aberta.
- **P3 —** `"/api"` e `"/v1"` sem barra final não são aparados. Sem ocorrência hoje.

### 2.2 axios cru (fora do cliente `api`) — todos corretos

`refreshAccessToken` → `POST /api/auth/refresh` (`api.ts:44`, com o porquê documentado em
`:39-43`); `logout` → `POST /api/auth/logout` (`:424`); `ErrorBoundary.tsx:39` →
`fetch("/api/observabilidade/frontend-error")`; `lib/stream.ts:19-35` (`authFetch`, SSE) usado por
`PecaGeneratorModal.tsx:595`, `BancarioForense.tsx:564`, `AnaliseExtratos.tsx:152`,
`AgenteIA.tsx:147`. **Todos usam o path real. FUNCIONAL.**

**P3 —** comentário obsoleto em `Despesas.tsx:117` ("baseURL /api").

---

## 3. Dados reais × mock — nada fabricado

**Este é o ponto mais forte do frontend.**

| Hipótese | Resultado |
|---|---|
| `Math.random` | **1** ocorrência — `stores/cadastroManual.ts:123`, ID local de rascunho. Legítima |
| `mock` / `fake` / `lorem` / "dados de exemplo" | **0** em código de produção |
| `console.log` · `alert()` · `prompt()` | **0** |
| `TODO` / `FIXME` reais | **0** (os hits são a palavra "TODOS") |
| Arrays literais em páginas | 36 auditados — **todos** são configuração de domínio (abas, tipos de peça, tabela de prescrição em `Casos.tsx:120` **com base legal citada**), não métricas |
| Cards de métrica | **todos** derivados de dados carregados — `DashboardModern.tsx:394-428`, `portal/PortalFinanceiro.tsx:58-80`, `PortalDashboard.tsx:76-95` |

`components/RadarLegislativo.tsx:4` traz comentário histórico ("antes exibia dados mockados") —
hoje consome `/intelligence-v3/radar/legislativo` de verdade (`:28`).

**P3 — DESCONECTADA, mas inalcançável:** `DossieCliente.tsx:1439-1453` tem a aba "IA do Cliente
(Análise 360º)" com selo "Em breve". `ia_cliente` foi removido de `validTabs` (`:846-854`), então
`abaAtiva` **nunca** assume esse valor, nem por deep-link. É código morto preservado; o usuário
não chega nele.

## 4. Botões e ações mortas — nenhuma

`onClick={() => {}}`, `href="#"`, `onSubmit={() => {}}` → **0 ocorrências**. Varredura multilinha
de todos os `<button>`: **um único** sem handler — `components/Layout.tsx:683-691` — e é
intencional (`disabled`, `title={ROTULO_IA_NAO_ATIVADA}`, `cursor-not-allowed`, ramo `else` de
`iaDisponivel`). Todos os `<form>` têm `onSubmit`. **FUNCIONAL.**

## 5. Loading, vazio e erro

| Página | Loading | Vazio | Erro | Classificação |
|---|---|---|---|---|
| `Casos.tsx` | `SkeletonTable`:987 | `EmptyState`:991 | `EmptyState` + "Tentar novamente":976 | **FUNCIONAL** |
| `Clientes.tsx` | `SkeletonTable`:177 | `EmptyState` | `EmptyState`:166 + `toast.error`:85 | **FUNCIONAL** |
| `CentralAtividades.tsx` | :917,958 | `EmptyState`:696 | `setError(true)`:918,979 | **FUNCIONAL** |
| `Documentos.tsx` | `Spinner`:847 | `EmptyState`:837 | `setErro(true)`:219 | **FUNCIONAL** |
| `Pecas.tsx` | `Spinner`:718,1332 | `EmptyState`:25 | `toast.error(errDetail())`:188 | **FUNCIONAL** |
| **`DashboardModern.tsx`** | :188 | `EmptyState`:39,601 | **ausente** — `Promise.allSettled`:202-227 descarta rejeições em silêncio | **PARCIAL** |
| Portal · Casos/Documentos/Financeiro | `Spinner` | `EmptyState` | `ErrorState` **com retry** | **FUNCIONAL** (o melhor do app) |
| **`portal/PortalDashboard.tsx`** | :49 | texto:185 | **ausente** — `allSettled`:52-70 | **PARCIAL** |
| `portal/PortalCasoDetalhe.tsx` | `Spinner`:118 | :66 | `ErrorState`+retry:110, **mas** `MensagensCliente` faz `.catch(() => {})`:17 | FUNCIONAL C/ RESSALVAS |
| **`Produtividade.tsx`** | :116 | "sem dados" | `.catch(() => setData(null))`:124 — **403 vira estado vazio** | **PARCIAL** |

> ### 🟠 P2 — falha silenciosa como classe: 41 ocorrências
>
> `.catch(() => {})` / `} catch {}` em código de produção. As mais relevantes:
> `CasoDetalhe.tsx:300,529,557,646,650`; `CasoDetalhe/TabResumo.tsx:147,383,465`,
> `TabPartes.tsx:35,45`, `TabScore.tsx:23,33`, `TabRisco.tsx:52`, `TabProcessos.tsx:50`,
> `TabMemoria.tsx:39`; `Documentos.tsx:228,234`; `Jurimetria.tsx:114,133`; `Layout.tsx:144`;
> `stores/caseContext.ts:89`; `contexts/useCasoFiltro.ts:44`.
>
> Em todas, backend indisponível produz uma aba **visualmente idêntica a "não há dados"** — o
> advogado não distingue *"o caso não tem partes"* de *"a chamada falhou"*. Num sistema jurídico,
> essa ambiguidade é material: leva a concluir que não há prazo, parte ou prova quando há.
>
> *(Duas exceções corretas por desenho: `api.ts:424` (logout) e `RecuperarSenha.tsx:10`, que
> engole erro de propósito para não vazar existência de e-mail.)*

## 6. Permissões no cliente — divergências com o backend

`canRoleAccessPath` (`moduleRegistry.tsx:1054-1061`) **não é** a guarda de rota: só filtra o
catálogo de `/ferramentas` (`Ferramentas.tsx:91`), as opções de home em `Configuracoes.tsx:138` e
o destino pós-login em `LoginModern.tsx:130`. A guarda real é `<RoleOnly>`
(`App.tsx:147-152` → `RouteGuards.tsx:48-60`).

**Enforcement no backend confirmado** para `/auditoria` (`routers/audit.py:28`), `/lixeira`
(`trash.py:44,66`), `/mapa-modulos` (`system_modules.py:42`), `/diagnostico`
(`diagnostico.py:30`), `/usuarios` (`users.py:26`), `/clientes` (`clients.py:32-45`),
`/financeiro` (`fees.py:37-44`), `/ia-governanca` (`ia_governanca.py:35`), jurimetria
(`jurimetria.py:37`), ia-saúde (`ia_saude.py:50`).

> ### 🟠 P1 — `/prompts` protegido só no frontend
>
> O registry restringe a rota a `ROLES.juridico` (exclui `financeiro` e `secretaria`). O backend
> `routers/prompts_juridicos.py:113-118` exige apenas `ROLE_LEVEL >= estagiario` — e, verificado
> por mim em `core/security.py:27-37`, **`financeiro` = 4 > `estagiario` = 3**.
>
> Logo um usuário `financeiro` que chame `GET /api/prompts-juridicos` direto recebe a lista
> **completa** (a checagem é um *filtro* de `publico`, não um 403). `secretaria` = 2 é barrada
> corretamente. Impacto material baixo (biblioteca interna de prompts, sem PII), mas é divergência
> real de matriz de permissão. **[NÃO CONFIRMADO empiricamente]** — análise estática.

**P2 — `/produtividade`, divergência invertida.** A entrada no registry **não tem `roles`**
(qualquer staff acessa a tela), mas `routers/produtividade.py:16-21` exige **sócio+**, com
comentário explícito ("dado gerencial sensível"). Para advogado/estagiário/financeiro/secretaria:
toast "Sem permissão" + tela "sem dados". **Não é IDOR** — o backend é o mais restritivo. É
defeito de UX/consistência: a rota deveria carregar `roles: ROLES.gestores`.

**P3 —** `canRoleAccessPath` faz match por **igualdade exata** de path (`:1058`). Para caminho
dinâmico (`/casos/abc-123`) devolve `false`. Inofensivo hoje; quem reutilizar a função para gatear
links de detalhe terá bloqueio silencioso.

## 7. Achados priorizados

| # | Achado | Classe | P |
|---|---|---|---|
| 1 | 27 chamadas `/v1/…` em 404 — 8 módulos de negócio mortos na UI | QUEBRADA | **P0** |
| 2 | `api.ts:23` — a poda de `/v1/` é a causa raiz | QUEBRADA | **P0** |
| 3 | Interceptor de passe único não normaliza `/api/v1/v1/…` | FUNCIONAL C/ RESSALVAS | P1 |
| 4 | Interceptor não cobre URL relativa sem barra inicial | FUNCIONAL C/ RESSALVAS | P1 |
| 5 | `/prompts` protegido só no frontend | FUNCIONAL C/ RESSALVAS | P1 |
| 6 | `/produtividade` sem `roles` no registry vs sócio+ no backend | PARCIAL | P2 |
| 7 | 41 `.catch(() => {})` — falha indistinguível de "sem dados" | PARCIAL | P2 |
| 8 | `DashboardModern` e `PortalDashboard`: `allSettled` sem sinalizar widget que falhou | PARCIAL | P2 |
| 9 | `PortalCasoDetalhe.tsx:17` — mensagens falham em silêncio | FUNCIONAL C/ RESSALVAS | P2 |
| 10 | 4 rotas `/legado/*` sem nenhum link | OBSOLETA | P3 |
| 11 | Aba `ia_cliente` "Em breve" — código morto inalcançável | DESCONECTADA | P3 |
| 12 | `canRoleAccessPath` falha em path dinâmico | FUNCIONAL C/ RESSALVAS | P3 |
| — | rotas órfãs · componentes inexistentes · duplicatas · mocks · botões mortos · forms sem submit | **nada encontrado** | — |
