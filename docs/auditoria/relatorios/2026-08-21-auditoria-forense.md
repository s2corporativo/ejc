# Auditoria forense do EJC — 2026-08-21

**Base auditada:** `main` @ `5de5fa6` · **Issue:** #1233
**Método:** execução real (suítes, migrations, banco Postgres 16 + pgvector, build) e
análise estática cruzada. Nada aqui foi declarado sem comando executado.

> Regra aplicada em todo este documento: **"não auditado" nunca é "funcionando"**.
> A seção *Fora do alcance* lista o que não pôde ser verificado nesta sessão.

---

## 1. Resumo executivo

Três defeitos confirmados e corrigidos — todos na **infraestrutura de verificação** e no
**gate de autenticação**, não nas regras de negócio. O achado de maior impacto é que a
suíte backend inteira era inexecutável fora do CI: um `pytest.skip()` mal formado
interrompia a coleta e **zero** dos 5.853 testes rodava em qualquer ambiente sem Postgres.

O sistema em si mostrou-se, nas áreas efetivamente auditadas, mais sólido do que os
relatórios históricos da raiz do repositório sugerem. Várias "armadilhas confirmadas"
descritas em `CLAUDE.md` **já não se reproduzem** na `main` atual (§7).

| # | Achado | Gravidade | Status |
|---|--------|-----------|--------|
| 1 | Suíte backend não coleta fora do CI (`pytest.skip` de módulo) | ALTO | CORRIGIDO · TESTADO |
| 2 | 2 testes de DR falham por config ausente em vez de pular | MÉDIO | CORRIGIDO · TESTADO |
| 3 | Fail-open latente em `_api_path_interno` (`//api/...`) | SEGURANÇA (latente) | CORRIGIDO · TESTADO |
| 4 | Gates de governança desligados — não rodam em PR nenhum (§7-A) | ALTO (processo) | ENCONTRADO · **decisão do titular** |

---

## 2. Prova de execução

### Achado 1 — suíte backend inexecutável fora do CI

- **Problema:** `pytest tests` abortava na coleta com
  `Interrupted: 1 error during collection`; nenhum teste executava.
- **Causa raiz:** `tests/test_document_rescan_integracao_dblevel.py:23` chamava
  `pytest.skip()` em nível de módulo sem `allow_module_level=True`. Isso é erro de
  coleta, não skip. O CI nunca expôs a falha porque lá `RUN_DB_TESTS` está definida e
  a linha jamais é alcançada. Varredura AST de toda a suíte: **é o único arquivo** com
  esse padrão; os demais `*_dblevel.py` usam `pytestmark = pytest.mark.skipif(...)`.
- **Arquivos:** `backend/tests/test_document_rescan_integracao_dblevel.py`
- **Correção:** alinhado ao padrão dos vizinhos (`pytestmark`), imports movidos ao topo.
- **Teste:** `pytest tests -q` sem Postgres.
- **Resultado:** antes `1 error, 0 testes`; depois **5853 passed, 273 skipped, 0 failed**.
- **Status:** VALIDADO.

### Achado 2 — testes de DR falhando por configuração ausente

- **Problema:** com `RUN_DB_TESTS=1` (modo local documentado), 2 testes falhavam com
  `KeyError: 'SCHEMA_CHECK_DATABASE_URL'`.
- **Causa raiz:** o `skipif` guardava só `RUN_DB_TESTS`, mas os testes consomem uma
  segunda variável via `os.environ[...]`. Erro de ambiente ficava indistinguível de
  quebra real de schema — justamente nos testes que provam reconstrução do banco e
  reversibilidade de migration.
- **Arquivos:** `backend/tests/test_schema_dr_parity.py`,
  `backend/tests/test_preliminares_fundacao_schema_140.py`
- **Correção:** o guard passa a exigir as duas variáveis. **No CI nada muda** —
  `ci.yml:46` define ambas, e os testes continuam rodando lá.
- **Teste:** executados nos dois caminhos.
- **Resultado:** sem a variável → `2 skipped` com motivo explícito; com a variável →
  `11 passed`. Confirmado que o defeito era o guard, não o schema.
- **Status:** VALIDADO.

### Achado 3 — fail-open latente no gate de autenticação

- **Problema:** `_is_publica("//api/casos")` retornava `True` — classificando como
  **rota pública** (sem JWT) um path que aponta para recurso protegido.
- **Causa raiz:** `posixpath.normpath` preserva exatamente duas barras iniciais (regra
  POSIX). `//api/casos` não é normalizado, falha o `startswith("/api/")`, e
  `_is_publica` cai no ramo "não é `/api/` → liberado".
- **Explorabilidade — verificada, não presumida:** chamada ASGI direta com
  `path="//api/casos"` devolve **404** (o roteador do Starlette não casa o path), e o
  nginx colapsa barras antes do proxy. **Não é explorável hoje.** É corrigido mesmo
  assim porque a autenticação estava fail-open e dependia inteiramente de duas defesas
  externas a ela: qualquer normalização a jusante (novo middleware, `root_path`, troca
  de servidor) converteria isso em bypass real.
- **Arquivos:** `backend/app/core/auth_middleware.py`,
  `backend/tests/test_auth_middleware_public_paths.py`
- **Correção:** colapso de barras iniciais antes da normalização (fail-closed).
- **Teste:** regressão nova + 50 testes de middleware existentes.
- **Resultado:** `//api/casos`, `///api/casos`, `//api/v1/casos` → `False`;
  `//api/auth/login` segue pública; `/static/app.js` segue liberado. **50 passed.**
- **Status:** VALIDADO.

---

## 3. Verificação executada (comandos e resultados)

| Verificação | Comando | Resultado |
|---|---|---|
| Suíte backend (sem banco) | `pytest tests -q` | 5853 passed · 273 skipped · **0 failed** |
| Suíte backend (banco real) | `RUN_DB_TESTS=1 … pytest tests -q` | 6120 passed · 5 skipped · **2 failed** (Achado 2) |
| Suíte backend (banco real, pós-correção) | idem + `SCHEMA_CHECK_DATABASE_URL` | **6124 passed · 3 skipped · 0 failed** |
| Migrations do zero | `alembic upgrade head` | **138 migrations**, base vazia → `146_case_sigilo_reforcado` |
| Lint backend | `ruff check app` | All checks passed |
| Typecheck frontend | `tsc --noEmit` | 0 erros |
| Testes frontend | `vitest run` | 106 arquivos · **567 passed** |
| Build produção | `vite build` | ✓ built |

Ambiente reconstruído do zero nesta sessão: Postgres 16 + `vector`/`pg_trgm`/`pgcrypto`.

---

## 4. Grafo de migrations

Análise AST das 138 migrations (parser ingênuo de regex produz falso positivo em
`down_revision` de tupla multi-linha — refeito com `ast.literal_eval`):

- **Head único:** `146_case_sigilo_reforcado` ✔
- Nenhum `down_revision` órfão ✔ · Nenhum filho com prefixo ≤ pai ✔
- Prefixo `101` duplicado: histórico, dois ramos convergidos por
  `104_merge_entrada_orquestrador` ✔
- `alembic upgrade head` reconstrói banco vazio ✔ · `139 → downgrade 138` preserva
  tabelas legadas ✔ *(estes dois só puderam ser provados após o Achado 2)*

---

## 5. Autorização e isolamento (auditado, sem achado)

- **IDOR por caso:** 50 arquivos expõem `{case_id}`/`{caso_id}`; 106 usam
  `verificar_acesso_caso`. Os 5 que não importam o gate canônico foram lidos um a um —
  todos têm gate próprio equivalente (`_obter_caso_visivel`, `_filtro_visibilidade`,
  `pode_ver_todos`) ou são apenas redirects. **Sem lacuna.**
- **Portal do cliente:** os 7 endpoints chamam `_exigir_cliente(cu)` e filtram por
  `client_id`. Rotas laterais liberadas ao `cliente_externo` (`/signatures`,
  `/notifications`, `/users/me`) auditadas: `signatures` isola por `client_id` e
  reconfere confidencialidade no momento de servir o conteúdo (defesa em profundidade).
- **Rate limit × superfície dupla:** a chave é `nome lógico + usuário/IP`, **não o
  path** — `/api/x` e `/api/v1/x` compartilham cota. Não há bypass de brute-force.
  Degradação do Redis cai para contador em memória, nunca ilimitado.
- **Isolamento do RAG:** `_FILTRO_ESCOPO_RAG` é **fail-closed** por cliente (categorias
  restritas exigem `scope_cli`). O isolamento por caso é fail-open por decisão
  explícita e documentada (doc sem `case_id` permanece visível **dentro** do escopo do
  cliente) — dentro da fronteira do cliente, não a atravessa.

---

## 6. Contrato frontend ↔ backend

Cruzamento independente: **613** chamadas `api.*` estáticas do frontend contra as
**876** rotas do app montado, replicando a poda de prefixo do interceptor e o
middleware de versão.

**Resultado: nenhuma chamada sem rota correspondente.** Os 7 candidatos iniciais foram
verificados um a um — `redirect_slashes` (307) ou interpolação com domínio fechado
(`"arquivar" | "descartar"`). Nenhum botão morto por rota inexistente.

O repositório já possui guarda equivalente (`tests/test_api_contract.py` +
`app/utils/api_contract.py`); esta auditoria a confirma por caminho independente.

---

## 7. Armadilhas históricas reverificadas — já não se reproduzem

`CLAUDE.md` lista armadilhas confirmadas em produção. Reverificadas contra a `main`:

| Armadilha documentada | Estado hoje |
|---|---|
| `/api/v1/v1/despesas` 200 e `/api/v1/despesas` 404 | **Resolvida.** `despesas`, `office-contracts`, `partner-withdrawals`, `kanban-columns` e `regulatorio/digest-semanal` têm rota canônica em `/api/`; nenhum router montado dentro de `/api/v1`. |
| `qa/e2e/run_fictitious_smoke.py` roda contra produção | **Resolvida.** Guard em `run_fictitious_smoke.py:1025` exige staging/homolog/localhost ou autorização explícita. |
| Numeração de migrations envelhecida | Head atual confirmado por execução: `146_case_sigilo_reforcado`. |

Os `RELATORIO_*.md` da raiz devem ser lidos como histórico, não como estado atual.

---

## 7-A. Achado 4 — os gates de governança não rodam nos PRs (ALTO, processo)

Descoberto ao conferir por que o PR desta auditoria (#1234) fechou verde sem que a
governança avaliasse o corpo. **Não corrigido aqui** — é CI/CD (governança §10 exige
autorização explícita), a mudança é de configuração no GitHub e não de código, e
reabilitar a trava agora reprovaria em massa os PRs abertos de terceiros. Registrado
como Issue nova; a decisão é do titular.

`CLAUDE.md` afirma que `ci.yml`, `ejc-release-gate.yml`, `governanca.yml`,
`continuity-ui-gates.yml`, `architecture-inventory.yml`, `backup-gdrive-activation.yml`
e `rag-production-activation.yml` "disparam em `pull_request`". No PR #1234
(`head_sha` `58b50cb`) rodaram **dois**:

| Workflow | `on: pull_request` no arquivo | Estado no GitHub | Rodou |
|---|---|---|---|
| `ci.yml` | sim | active | **sim** |
| `ejc-release-gate.yml` | sim | active | **sim** |
| `governanca.yml` | sim | **`disabled_manually`** | não |
| `continuity-ui-gates.yml` | sim | **`disabled_manually`** | não |
| `architecture-inventory.yml` | sim | **`disabled_manually`** | não |
| `backup-gdrive-activation.yml` | sim | active | não — filtro `paths` correto, o diff não toca os arquivos |
| `rag-production-activation.yml` | sim | active | não — idem |
| `auto-integracao.yml` | `on: workflow_run` | **`disabled_manually`** | não |

Os dois últimos `active` estão **corretos**: têm `paths` legítimos. O problema são os
três desabilitados manualmente.

**Correção de uma inferência errada desta auditoria.** A primeira versão deste relatório
datava cada desabilitação pelo campo `updated_at` do workflow ("19/08", "12/08"). Isso
está **errado** e as datas foram removidas da tabela: `updated_at` acompanha a última
alteração do *arquivo*, não o momento em que o workflow foi desligado. A prova é o
próprio `governanca.yml` — commit `bb04246a` em `2026-08-19T20:17:45-03:00`,
`updated_at` do workflow em `2026-08-19T20:17:47-03:00`, dois segundos depois. O estado
`disabled_manually` é fato verificado; a data em que foi aplicado, não.

**O que a evidência sustenta.** Dezenas de workflows compartilham `updated_at` na janela
`2026-08-12T22:20:41` – `22:21:25` — cerca de 45 segundos. São, quase todos, workflows
temporários e de diagnóstico (`_temp-*`, `diagnose-pr194`, `diagnose-pr207-db`,
`apply-*-once`, `format-*-temp`). A leitura mais provável é uma **faxina em massa** que
desligou o entulho — e apanhou junto três gates legítimos: `architecture-inventory.yml`,
`continuity-ui-gates.yml` e `auto-integracao.yml`. Dano colateral, não decisão.

**O agravante.** Em 19/08 o `governanca.yml` foi **ampliado** (commit `bb04246a`, +59/-20):
passou a exigir as seções `Diagnóstico`, `Impacto jurídico` e `Impacto LGPD` e a
Definition of Done. Investiu-se em endurecer um gate que já estava desligado — sintoma
de que ninguém percebeu o estado real.

**O `governanca-v2.yml` é um beco sem saída.** Consta `active` na API (id `335876178`),
mas o arquivo não existe na `main`: foi criado pelo commit `55494d4f` (17/08,
"fix(ci): criar governança v2 habilitada com mesmo contexto bloqueante (#998)"), que vive
**só** em `origin/fix/bootstrap-ruleset-recovery-998-v2` — branch nunca mesclada. Era um
contorno para a recuperação de ruleset da #998. Além disso, o `governanca.yml` de 19/08
**removeu do próprio cabeçalho** a menção à "governança v2", indicando que a lógica foi
consolidada de volta no v1. O caminho "recuperar o v2" está, portanto, obsoleto.

**Consequência.** Nenhuma das travas que `CLAUDE.md` descreve como obrigatórias está
sendo aplicada em PR nenhum: Issue vinculada (`#<numero>` no corpo), Definition of Done
marcada, e a confirmação de revisão de segurança exigida quando o diff toca superfície
sensível — que é exatamente o caso deste PR (`app/core/auth_middleware.py`). O merge
automático da regra 8 (`auto-integracao.yml`) também está desligado.

**Por que passou despercebido.** `CLAUDE.md` manda "conferir com
`grep -A4 '^on:' .github/workflows/*.yml` antes de afirmar que algo não roda". Os oito
arquivos têm o gatilho certo — **o grep confirma todos**. O estado
`disabled_manually` vive na API/UI do GitHub, não no arquivo: o método de verificação
recomendado pelo repositório é justamente o que não detecta este defeito. Só a
listagem de workflows (`GET /actions/workflows`) ou a ausência do check no PR revela.

É a mesma classe já catalogada em `CLAUDE.md` — *"monitoramento afere execução, não
resultado"* —, agora aplicada ao próprio CI: o gate existe, está versionado, parece
configurado, e não roda.

---

## 8. Auditado sem achado

Módulo de **prazos** (`deadline_calculator.py`, `calendario_tribunal.py`): contagem em
dias úteis exclui o dia de início (CPC art. 224); recesso do art. 220 correto
(20/12–20/01 inclusive); feriados móveis por computus de Gauss corretos (carnaval
−48/−47, sexta-feira santa −2, Corpus Christi +60); todo registro exige `fonte` e
`vigencia` com fail-fast na importação.

**Gravação não transacional** (classe de defeito recorrente citada em `CLAUDE.md`):
varredura AST encontrou apenas 7 funções com ≥3 `commit()` — os casos em `auth.py` são
caminhos de erro (registro de tentativa falha), não escrita de registros relacionados.

**Exceções silenciadas:** 996 handlers; 58 com `except: pass`. Amostragem nos caminhos
críticos (`rate_limit.py`) mostrou silenciamento legítimo e comentado (`aclose()` em
reconexão). Não é um filão de defeitos.

---

## 9. Riscos residuais e fora do alcance

**Não auditado nesta sessão** — não tratar como funcionando:

- **VPS, Docker em produção, deploy, backup/restore, runners, DNS/SSL.** Sem acesso ao
  ambiente de produção (e a governança §9 proíbe esse acesso a partir daqui).
- **Navegação real página por página** (itens 51–52 da missão: link por link, palavra
  por palavra). Exige a stack de pé com dados; feito o equivalente estático — contrato
  de rotas (§6) e os 4 testes de integridade de rota do frontend.
- **RAG com corpus real** (recall, reranking, isolamento sob dados de verdade).
  Auditada a *forma* dos filtros (§5), não o comportamento sob corpus.
- **Jurimetria, financeiro centavo a centavo, Visual Law, Ollama/Claude em runtime.**
- **Acessibilidade e responsividade.**

**Risco residual conhecido:** os 273 testes que pulam sem Postgres continuam
dependendo de banco; agora ao menos os outros 5.853 rodam localmente, o que encurta o
laço de feedback fora do CI.

---

## 10. Recomendações

**Prioridade A** — reabilitar `governanca.yml` (Issue #1235). É a versão consolidada e
mais recente do gate — não o `governanca-v2.yml`, órfão de branch não mesclada, que deve
ser desregistrado. Reavaliar no mesmo passo `continuity-ui-gates.yml` e
`architecture-inventory.yml`; `auto-integracao.yml` (merge automático) é decisão à parte.
Esperar reprovação inicial nos PRs abertos cujos corpos não têm as seções — o dependabot
já tem isenção embutida no workflow.

**Prioridade A** — `test_alembic_single_head.py` fixa o head à mão, o que faz dois PRs
com migration conflitarem ali por construção (já registrado em
`MIGRATION_RESERVATIONS.md`). `test_migration_numbering_guard.py` já cobre head único
sem identificador fixo; avaliar aposentar o teste de head fixo.

**Prioridade B** — `warning` de `act(...)` e um `setState` durante render em
`CadastroManual` no vitest: não quebram teste, mas indicam atualização de estado fora
do ciclo do React.

**Prioridade B** — `eslint` acusa **3 erros** de `no-unused-expressions` em
`src/components/DossieEstrategicoCaso.tsx` (linhas 201, 266, 280): o idiom
`gerarRef.current && clearTimeout(gerarRef.current)`. **Funciona** — o `clearTimeout` é
executado —, é apontamento de estilo, não defeito. Não corrigido aqui por estar fora do
escopo da Issue #1233. Os outros 679 achados do eslint são `no-explicit-any` (avisos).
Note que `npm run lint` é `tsc --noEmit`; o eslint não é bloqueante no CI.

**Prioridade C** — consolidar os ~45 `RELATORIO_*.md` da raiz. Descrevem estados já
superados e competem com `CLAUDE.md` como fonte da verdade.
