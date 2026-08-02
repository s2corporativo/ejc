# 02 — Relatório Graphify (Fase 2)

> Auditoria integral do EJC — commit `aa65974`, branch `claude/auditoria-ejc-graphify-aoa2hi`, 2026-08-02.
> **O grafo é índice auxiliar, não fonte da verdade.** Toda afirmação abaixo que veio do grafo foi
> confirmada (ou refutada) no arquivo real. As refutações estão registradas — elas são o resultado
> mais útil desta fase.

## 1. Estado da ferramenta

| Item | Situação |
|---|---|
| Binário | `graphify 0.9.28`, em `/usr/local/bin/graphify` — **instalado** |
| Comando executado | `graphify update .` (incremental, AST-only, sem custo de API) |
| Grafo antes | `graph.json` de 27/07, 24,3 MB — **6 dias defasado** |
| Grafo depois | 27,3 MB, `built_at_commit = aa65974…` — **sincronizado com o commit auditado** |
| Cobertura | 1 638 arquivos no manifesto; 19 575 nós; 47 896 relações |
| Versionamento | `graphify-out/` está no `.gitignore` (linha 61) e **não é versionado** (`git ls-files` vazio) |

**Divergência documental encontrada.** O `CLAUDE.md` descreve o grafo como "versionado" ("o grafo
versionado estava 6 dias e 147 commits atrás"). Ele **não é versionado** — é ignorado pelo git e
reconstruído localmente pelo hook `SessionStart`. A frase induz a crer que o grafo chega pronto no
clone; não chega. → correção sugerida no plano (P3).

**Arquivos que o extrator não conseguiu ler** (reportados pelo próprio graphify): 11 arquivos
produziram zero nós, entre eles `.claude/settings.json`, `auditoria-grafo/grafo-dados.json`,
`jurisprudencia.json`, `teses_vitoriosas.json`, `gold_set.template.json`. São JSON — o extrator é
AST de código. Sem impacto para esta auditoria, mas explica ausências.

### Segurança da indexação
Verificado antes de rodar: `graphify-out/` está no `.gitignore`; o comando roda **AST-only, sem
chamada a API externa** (a própria saída sugere `GEMINI_API_KEY` como *opcional* para extração
semântica — **não foi configurada, nada saiu da máquina**). Nenhum segredo, documento jurídico ou
dado pessoal foi enviado a serviço externo. `.env` não existe no repositório (só `.env.example`).

---

## 2. Achado metodológico central — o grafo erra por colisão de nome

O graphify resolve símbolos por AST, mas **funde símbolos homônimos de arquivos diferentes num só
nó**. Isso produz hubs fantasma.

**Caso demonstrativo — `maritaca_provider.py`.** O grafo o apontava como o 6º maior hub do
repositório, com **136 dependentes**. Isso implicaria que um provider de IA é importado por meio
backend — violação direta da regra "toda IA passa pelo `ai_gateway`".

Confirmação no arquivo (`grep -rn maritaca_provider --include=*.py backend/`):

| Fonte | Dependentes de `maritaca_provider` |
|---|---|
| Grafo | 137 arquivos |
| **Código real** | **4 arquivos** — `ai_gateway.py` (linhas 633, 637, 882-883), `credential_testers.py:195` (só um comentário), `tests/test_maritaca_provider.py`, e ele mesmo |

Causa: o método privado `_post()` existe em 78 arquivos. O grafo colapsou todos no `_post()` do
`maritaca_provider`, e cada `references` para qualquer `_post` virou aresta para o provider.

### Quantificação do erro

| Métrica | Valor |
|---|---|
| Símbolos de código distintos | 10 589 |
| Símbolos **ambíguos** (mesmo nome em >1 arquivo) | 573 (5,4 %) |
| Arestas código→código | 42 768 |
| **Arestas cujo alvo tem nome ambíguo** | **10 336 — 24,2 %** |

**Um quarto das arestas do grafo não é confiável sem verificação no arquivo.** Os nomes mais
ambíguos: `.__init__()` (127 arquivos), `upgrade()`/`downgrade()` (121 cada — todas as migrations),
`.execute()` (78), `_FakeDB` (72), `.commit()` (69).

### Segunda limitação — imports tardios são invisíveis

O grafo é AST de nível de módulo: **`import` dentro de função não é capturado**.

| Métrica | Valor |
|---|---|
| Imports internos indentados (dentro de função) em `backend/app` | **743** |
| Arquivos que usam o padrão | **169** (de 539 = 31 %) |

Consequência prática: `services/due_diligence_empresarial.py` aparece como **órfão** no grafo, mas é
importado em `routers/sociedades_cliente.py:165`, dentro de uma função. **Qualquer afirmação de
"código órfão" tirada do grafo é falso positivo em potencial para um terço do backend.**

> **Regra operacional derivada:** o graphify serve para *localizar* e para *ordenar prioridade de
> leitura*. Ele **não** serve para afirmar que algo não existe, não é usado, ou é o hub principal.

---

## 3. Hubs reais (após descartar arestas ambíguas)

Recalculado no nível de arquivo, excluindo as 10 336 arestas de alvo ambíguo e as relações
`contains`/`rationale_for` (que não são dependência).

### Backend — `backend/app`

| # | Arquivo | Dependentes | Papel | Impacto de alteração |
|---|---|---|---|---|
| 1 | `core/database.py` | 247 | `AsyncSession`, `get_db()` | **sistêmico** |
| 2 | `models/user.py` | 232 | identidade + RBAC | **sistêmico** |
| 3 | `core/security.py` | 207 | JWT, `ROLE_LEVEL`, `require_roles` | **sistêmico** |
| 4 | `core/config.py` | 184 | settings/env | **sistêmico** |
| 5 | `services/__init__.py` | 122 | fachada de services | transversal |
| 6 | `core/ownership.py` | **99** | gate ABAC de caso | **sistêmico (segurança)** |
| 7 | `models/case.py` | 98 | entidade central do domínio | **sistêmico** |
| 8 | `models/audit_log.py` | 90 | trilha de auditoria | transversal |
| 9 | `core/rate_limit.py` | 88 | limitação de taxa | transversal |
| 10 | `services/ai_gateway.py` | 62 | **único ponto de saída de IA** | **sistêmico (IA)** |
| 11 | `models/ai_log.py` | 59 | telemetria de IA | modular |
| 12 | `models/client.py` | 52 | cliente | transversal |
| 13 | `services/sanitizer.py` | 41 | barreira de PII | **sistêmico (LGPD)** |
| 14 | `services/pii_crypto.py` | 25 | Fernet + HMAC cego | **sistêmico (LGPD)** |
| 15 | `services/citation_gate.py` | 11 | gate antialucinação | modular (crítico) |

### Frontend — `frontend/src`

| # | Arquivo | Dependentes | Impacto |
|---|---|---|---|
| 1 | `lib/api.ts` | **137** | **sistêmico** — todo tráfego HTTP |
| 2 | `components/UI.tsx` | 118 | transversal (design system) |
| 3 | `components/Toast.tsx` | 86 | transversal |
| 4 | `lib/list.ts` | 43 | modular |
| 5 | `stores/auth.ts` | 33 | **sistêmico** (sessão) |
| 6 | `config/moduleRegistry.tsx` | 15 | **sistêmico** (rotas + RBAC de navegação) |

`moduleRegistry.tsx` tem in-degree baixa mas impacto alto: é *dado*, consumido por poucos
arquivos, e governa todas as rotas. **Centralidade de grafo não mede criticidade** — é a segunda
razão para não decidir por grafo sozinho.

### Acoplamento de saída (out-degree) — `backend/app`

| Arquivo | Dependências | Leitura |
|---|---|---|
| `main.py` | 176 | esperado: registra 166 objetos `APIRouter` |
| `models/__init__.py` | 62 | agregador |
| `routers/cases.py` | 42 | **router mais acoplado** — candidato a extração de service |
| `services/scheduler.py` | 36 | APScheduler toca muitos domínios |
| `routers/legal_docs.py` | 28 | produção jurídica |

---

## 4. Comunidades

942 comunidades detectadas; maior = 274 nós; mediana = 12; 34 comunidades de nó único.

As 10 maiores confirmam o domínio funcional real do sistema:

| Nós | Comunidade | Domínio |
|---|---|---|
| 274 | `Case` | núcleo do caso (backend) |
| 257 | `api` | cliente HTTP (frontend) |
| 215 | `User` | identidade/RBAC |
| 212 | `verificar_acesso_caso` | **gate de ownership** |
| 183 | `UI.tsx` | design system |
| 175 | `RamoBase.tsx` | ramos do direito (frontend) |
| 157 | `moduleRegistry.tsx` | roteamento |
| 142 | `Client` | cliente |
| **141** | **`_post`** | **artefato de colisão — não é módulo** |
| 121 | `is_gestao` | RBAC de gestão |

A comunidade `_post` (141 nós) é a materialização do defeito da seção 2: um "módulo" que não
existe no produto.

**Leitura de produto:** as comunidades reais se organizam em torno de `Case`, `User`, `Client` e
`ownership` — ou seja, o núcleo do sistema é coerente. A dispersão está na periferia (942
comunidades para 1 638 arquivos, mediana 12), o que é compatível com o diagnóstico de excesso de
módulos do `docs/auditoria/parecer-arquitetural.md`.

---

## 5. As 20 consultas obrigatórias — respostas

Respostas curtas; a evidência está nos documentos indicados.

| # | Pergunta | Resposta (confirmada em arquivo) |
|---|---|---|
| 1 | Principais módulos? | `Case`, `User`, `Client`, ownership, IA/RAG, produção de peças, financeiro, portal — ver `11-modulos.md` |
| 2 | Hubs? | seção 3 acima |
| 3 | Mais dependentes? | `core/database.py` (247), `models/user.py` (232), `core/security.py` (207) |
| 4 | Serviços muito acoplados? | `routers/cases.py` (42 deps), `services/scheduler.py` (36), `routers/legal_docs.py` (28) |
| 5 | Módulos isolados? | 8 candidatos no grafo; **todos falsos positivos** por import tardio (seção 2) |
| 6 | Componentes sem consumidor? | ver §6 — 64 routers sem consumidor localizável no frontend |
| 7 | Rotas não chamadas pelo frontend? | **393 de 820 (48 %, limite superior)** — §6 |
| 8 | Chamadas sem endpoint? | **25 — todas causadas pelo prefixo `/v1`** — §6 |
| 9 | Tabelas sem consumidor? | ver `07-banco-de-dados.md` |
| 10-11 | Models × migrations | ver `07-banco-de-dados.md` |
| 12 | Agentes compartilhando prompt? | sim — 4 pares; ver `04-agentes.md` |
| 13 | Skills por agente? | ver `05-skills.md` |
| 14 | Skills sem consumidor? | 10 de 19 (Claude Code); ver `05-skills.md` |
| 15 | Prompts duplicados? | `PROMPT_ANALISE_CASO` serve 4 chaves; ver `04-agentes.md` |
| 16 | Serviços de IA equivalentes? | 4 superfícies paralelas de "skill"; ver `05-skills.md` |
| 17 | Dependências circulares? | `core/ownership.py` existe **para evitá-las** (documentado no cabeçalho do arquivo) |
| 18 | Maior raio de impacto? | `core/database.py`, `core/security.py`, `lib/api.ts`, `main.py` — §3 e `03-mapa-dependencias.md` |
| 19 | Comunidades funcionais? | §4 |
| 20 | Onde o fluxo quebra? | ver `10-fluxo-juridico.md` |

---

## 6. Confronto frontend × backend (validação do grafo contra execução)

Este cruzamento **não** foi feito pelo grafo — foi feito por extração direta dos decoradores
`@router.*` e das chamadas `api.*`, justamente porque o grafo não modela rota HTTP. Serve também
como validação independente do grafo.

**Método e suas limitações (declaradas):** parser estático sobre `main.py` +
`routers/__init__.py` (registro aninhado) + os 162 arquivos de router; normalização de parâmetros
de path (`{id}` e `${id}` → `*`); reprodução do interceptor de `lib/api.ts` e do
`APIVersionCompatibilityMiddleware`. O extrator **subconta** chamadas encadeadas
(`api\n  .get(...)`) e não resolve URL montada em variável.

| Métrica | Valor |
|---|---|
| Arquivos de router | 162 |
| Objetos `APIRouter` registrados | 166 |
| **Endpoints registrados** | **820** |
| Chamadas `api.*` no frontend | 449 |
| Chamadas que casam com rota real | 422 |
| **Chamadas sem rota correspondente** | **27** — das quais **25 pelo bug `/v1`** e 2 são artefato do extrator (segmento dinâmico) |
| Endpoints sem consumidor localizável | 393 (48 %) — **limite superior** |
| Routers sem nenhum consumidor localizado | 64 de 162 |

**Correções que precisei fazer na minha própria análise** (registradas por honestidade metodológica):

1. Primeira passagem acusou **230** chamadas quebradas — era bug do meu normalizador (ordem de
   `${...}` vs `{...}`). Número real: 27.
2. Primeira passagem acusou **11 routers não registrados** — falso: o regex não via
   `include_router(` com comentário na mesma linha, nem import com alias. Real: **0**.
3. Depois acusou **5 routers não registrados** (`defesas_revisoes*`, `entrada_universal*`) —
   também falso: são registrados **aninhados** em `routers/__init__.py:24-30`, sob
   `novos_modulos`. Real: **0 routers órfãos**.
4. Acusou o router `ramos` (82 endpoints) como 100 % sem consumidor — falso: `ramosConfig.ts`
   declara **72 endpoints como dado**, consumidos por `RamoBase.tsx:201,1017,1063`
   (`api.get(cfg.endpoint)`). Por isso o número de endpoints sem consumidor é **limite superior**,
   não medida.

Os 64 routers sem consumidor localizado incluem casos legítimos de servidor (`evolution_webhook`,
`backup_admin`, `api_keys`, `audit`, `observabilidade`) e casos que merecem decisão de produto
(`cerebro`, `diplomacia_v3`, `intelligence_v3`, `victory_vault_router`, `curadoria_renomada`).
A lista completa está em `03-mapa-dependencias.md`.

---

## 7. Matriz de impacto

| Componente | Depende de | Consumido por | Centralidade | Impacto | Risco |
|---|---|---|---|---|---|
| `core/database.py` | config | 247 arquivos | máxima | **sistêmico** | alto — sessão async em todo o backend |
| `core/security.py` | models/user | 207 | máxima | **sistêmico** | **alto — auth/RBAC** |
| `models/user.py` | — | 232 | máxima | **sistêmico** | alto |
| `core/config.py` | — | 184 | máxima | **sistêmico** | alto — boot falha se inconsistente |
| `core/ownership.py` | security, models | 99 | alta | **sistêmico** | **alto — barreira de IDOR** |
| `models/case.py` | — | 98 | alta | **sistêmico** | alto |
| `services/ai_gateway.py` | providers, sanitizer | 62 | alta | **sistêmico** | **alto — LGPD/custo/kill-switch** |
| `services/sanitizer.py` | — | 41 | média | transversal | **alto — barreira de PII** |
| `services/pii_crypto.py` | config | 25 | média | transversal | **alto — chave de criptografia** |
| `frontend/lib/api.ts` | axios, auth | 137 | máxima | **sistêmico** | **alto — o bug `/v1` vive aqui** |
| `frontend/config/moduleRegistry.tsx` | páginas | 15 | baixa (grafo) | **sistêmico (real)** | médio |
| `core/api_version_middleware.py` | — | 1 | mínima (grafo) | **sistêmico (real)** | **alto — reescreve todo path** |
| `main.py` | 176 | — | — | **sistêmico** | médio |
| `routers/cases.py` | 42 | — | alta | transversal | médio |

As duas últimas linhas são o argumento contra confiar em centralidade: `api_version_middleware.py`
tem **um** dependente no grafo e é a causa raiz do defeito P0 desta auditoria.

---

## 8. Artefatos

Preservados **fora do versionamento** (já cobertos pelo `.gitignore`), como manda a boa prática:
`graphify-out/graph.json` (27 MB), `manifest.json`, `GRAPH_REPORT.md` (210 KB), `graph.html`
(969 KB), `cache/`. **Nada disso foi commitado** — são regeneráveis por `graphify update .` e
o `graph.html` embute caminhos internos do repositório.

## 9. Conclusão da fase

O graphify **pagou o próprio custo** nesta auditoria: apontou `core/ownership.py`, `ai_gateway.py`
e `lib/api.ts` como pontos de concentração, e as comunidades confirmaram o núcleo funcional. Mas
**nenhum dos quatro achados P0/P1 desta auditoria veio do grafo** — vieram de leitura dirigida de
arquivo e de cruzamento de contrato. O grafo escolheu *onde olhar*; não disse *o que era verdade*.

Recomendação: manter o hook `SessionStart`, manter `graphify-out/` fora do git, e **acrescentar ao
`CLAUDE.md` a taxa de erro medida (24 % das arestas com alvo ambíguo; 743 imports tardios
invisíveis)** — hoje o arquivo alerta qualitativamente, mas sem número o alerta é fácil de ignorar.
