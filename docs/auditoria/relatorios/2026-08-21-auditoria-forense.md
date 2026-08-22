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

## 8-A. Segunda rodada — auditoria funcional com a stack de pé (22/08)

A primeira rodada auditou o repositório; esta auditou o **sistema em execução**.
Backend local, Postgres 16 + pgvector, 138 migrations do zero, banco descartável
`ejc_app`, dados fictícios. Cobre os itens §8–§29 e §64 do prompt mestre, que
nenhuma análise estática alcança.

**Método.** Cada passo confere os DOIS lados: a resposta HTTP e a persistência
real no Postgres. HTTP 201 não foi aceito como prova — é exatamente a premissa
do §2 do prompt ("um endpoint responder não significa que funciona").

**39 verificações · 35 conformes · 3 achados · 1 falso positivo meu.**

### Achados

| # | Achado | Gravidade | Status |
|---|--------|-----------|--------|
| 5 | `POST /fees/` aceita honorário sem valor e sem percentual (HTTP 201, `valor=NULL`) | ALTO | **CORRIGIDO · TESTADO** |
| 6 | Upload de documento não gera SHA-256 — sem prova de integridade | MÉDIO | ENCONTRADO (Issue #1237) |
| 7 | Campo desconhecido no corpo é descartado em silêncio (default do Pydantic) | BAIXO | ENCONTRADO — decisão de contrato |

**Achado 5, medido.** Corpo com apenas `descricao`, `client_id` e `tipo=exito`
→ **201**, e no banco `valor=NULL, percentual_exito=NULL, status=pendente`. Pior:
`valor_total` (nome inexistente; o certo é `valor`) também devolvia 201 gravando
`NULL` — erro de digitação virava honorário fantasma. No banco de auditoria:
`com valor: 0 | SEM valor: 2`. Corrigido com `model_validator` exigindo ao menos
um dos dois; validado contra a API real (**422** onde antes era 201, payload
correto segue 201 com `7500.50` gravado).

**Achado 6.** `app/routers/documents.py` não menciona `sha256` nem `hashlib`;
`documents` não tem coluna de hash; o SHA-256 vive em `document_intake_items`,
que o upload direto não alimenta.

> **Correção deste achado, feita em 22/08 (ver §8-H).** A redação original dizia
> que corrigir "exige coluna nova (migration, exceção §6-A)". Está errado, e a
> diferença é grande: a máquina inteira já existe e está testada — só não é
> chamada por ninguém.

### Auditado e conforme

**Autenticação (§30) — 10/10.** Credencial errada, usuário inexistente, token
forjado, ausência de token: 401 em todos. Primeiro acesso com
`must_change_password` bloqueia rota protegida (403), a troca conclui, o login
novo funciona e **a credencial antiga deixa de valer**.

**Isolamento entre usuários (§31) — 5/5, empírico.** Segundo advogado criado pela
API, sem vínculo com o caso: `GET /cases/{id}` alheio → 404; caso não aparece na
listagem dele; `GET /documents/{id}/download` → 403; `PATCH /documents/{id}` →
403; `GET /users/` → 403. **Nenhum IDOR** — agora verificado com dois usuários
reais, não por leitura de código.

**LGPD/PII (§33) — 3/3.** CPF gravado como `cpf_enc` Fernet (`gAAAAA…`),
`cpf_hash` preenchido para busca cega, e o CPF em claro não aparece em nenhuma
outra coluna textual da linha.

**Deduplicação (§58).** CPF repetido → **409**, detectado pelo índice cego sem
decifrar.

**Prazos (§8.3), o módulo de maior risco jurídico.** 15 dias úteis a partir de
hoje, TRT3: API gravou `data_prazo=2026-09-14`; o motor
`deadline_calculator.prazo_dias_uteis` calcula `2026-09-14`. **Confere.**

**Percurso do advogado (§77) — 22/22.** Cliente → caso → prazo → tarefa, com
verificação no banco a cada passo. `descricao_fatos` **sobrevive** à gravação
(a auditoria externa suspeitava de perda nesse campo — não se reproduz), o
vínculo cliente↔caso persiste, `numero_interno` é gerado (`DPT-2026-0001`), o
caso aparece na listagem. Documento nasce `confidencial` — sem publicação por
omissão no portal.

### Falso positivo descartado

Registrei "caso criado não aparece na listagem". Era **erro meu**: o envelope é
`{"data": [...]}` e o verificador procurava `items`. Corrigido; o passo é
conforme. Fica como lembrete de que o verificador também erra — e de que um
"achado" sem conferência vira ruído.

### O que esta rodada NÃO cobriu

RAG sob corpus real, jurimetria, Visual Law, geração de peças por IA, portal do
cliente com login externo, responsividade, acessibilidade e performance. E o
percurso foi exercitado **pela API**: prova o backend e a persistência, não a
interface renderizada.

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

## 8-B. Rodada 3 — prazos e financeiro sob dados (22/08/2026)

Backend local com Postgres real, banco descartável, dados fictícios. 27 verificações
executadas conferindo os dois lados: resposta HTTP e estado no banco.

### Achado 6 — pagamento de honorário sem qualquer restrição de valor (CORRIGIDO)

`FeePaymentCreate.valor` era `Decimal` puro. O arquivo já definia
`ValorNaoNegativo = condecimal(ge=0)` para `fees.valor` desde a auditoria de
2026-06-30 (M5) — o pagamento apenas não fora alcançado por essa regra.

Sequência reproduzida, todas as respostas HTTP 201:

| passo | soma real de `fee_payments` | `fees.status` |
|---|---|---|
| honorário de R$ 1.000,00 | 0,00 | `pendente` |
| pagamento **+1.000,00** | 1.000,00 | `pago` (correto) |
| pagamento **−1.000,00** | **0,00** | **`pago`** (mentira) |

`registrar_pagamento` só promove o honorário a `pago` quando a soma alcança o valor
contratado, e nunca reavalia para baixo. Um lançamento negativo devolve a dívida a zero
e deixa o honorário exibido como quitado: receita integralmente em aberto, invisível na
cobrança e somando 100% de recebimento no relatório do cliente.

Mesmo endpoint, segundo caminho silencioso: o campo é `forma`; um corpo com
`forma_pagamento` tinha o campo descartado pelo Pydantic e gravava o pagamento com
`forma = NULL`, com HTTP 201 — a mesma classe do Achado 5.

**Correção:** validadores próprios exigindo valor > 0 e recusando campo
desconhecido, mais `model_config = ConfigDict(extra="forbid")` como contrato
declarado no OpenAPI. O frontend (`pages/Honorarios.tsx`) já
envia exatamente `{valor, data_pagamento, forma}`, então nada em uso é recusado.
Verificado contra a API: pagamento negativo 201 → **422**; `forma_pagamento` 201 → **422**;
pagamento legítimo segue 201. Regressão em `tests/test_fee_pagamento_valor_valido.py`.

### Em aberto — pagamento acima do saldo devedor (decisão do titular)

`POST /fees/{id}/pagamentos` aceita pagar R$ 36.000,00 num honorário de R$ 12.000,00,
sem aviso. **Não corrigido de propósito:** juros, multa e correção monetária tornam o
pagamento acima do principal legítimo, e bloqueá-lo fecharia caso real de cobrança.
O que falta é distinguir excedente de erro de digitação — decisão de regra de negócio,
não de implementação.

### Verificado conforme (nenhum defeito)

- **Motor de prazo.** `POST /deadlines/calcular` devolve `2026-09-14`, idêntico ao
  `prazo_dias_uteis` do próprio sistema — uma fonte de verdade só.
- **Ciclo de vida do prazo.** Confirmação de rascunho (`confirmado`), ciência com data
  **e autor**, cumprimento via `PATCH status=concluido`, saída da lista de pendentes e
  3 registros em `audit_logs`. Tudo persistido.
- **Prazo vencido.** O job `_marcar_prazos_vencidos` (07:10) escreve `status='vencido'`
  e alerta o responsável, com guarda de idempotência no próprio `WHERE`. Executado
  contra o banco: o prazo migra de `pendente` e passa a aparecer sob `?status=vencido`.
- **Prazo avulso.** `deadlines.case_id` é nullable por desenho (prazo administrativo);
  o avulso aparece normalmente na agenda geral, não some.
- **Exclusão de caso.** Não há a cascata destrutiva que a auditoria externa temia: o
  `DELETE` exige motivo (mín. 5 caracteres), **recusa** caso com pendências indicando o
  arquivamento e listando cada pendência, e quando aceita faz soft delete restaurável
  com o motivo gravado na trilha.
- **Precisão monetária.** R$ 4.500,00 e R$ 12.000,00 persistidos sem desvio.

### Falsos positivos desta rodada (registrados para não voltarem)

Quatro apontamentos iniciais eram artefatos do ambiente ou do meu payload, não defeitos:
`?status=vencido` vazio (o job estava desligado por `ENABLE_SCHEDULER=false`);
`/confirmar` não mudar o status (ele confirma o rascunho da IA, não o cumprimento);
prazo sem `case_id` (nullable por desenho); `DELETE /cases/{id}` em 422 (falta do
`motivo` obrigatório). `POST /deadlines/calcular` usa `data_inicio`/`dias`, enquanto
`POST /deadlines/` usa `data_intimacao`/`dias_prazo` — divergência de nomenclatura
entre dois endpoints do mesmo módulo, sem efeito funcional.

## 8-C. Rodada 4 — Portal do Cliente, confidencialidade e isolamento no RAG (22/08/2026)

Duas superfícies em que um vazamento é silencioso e grave: o cliente externo (que
enxerga o sistema de fora) e o RAG (que injeta texto recuperado em prompts). Prioridade 6
do prompt (isolamento de clientes) e 9 (RAG). **Nenhum defeito encontrado.**

### Portal do Cliente — 20/20 conformes

Montados dois clientes completos (A e B), cada um com caso, honorário e documento
próprios; login externo real criado para A pelo caminho canônico
`POST /clients/{id}/criar-acesso`; todas as verificações feitas com o token de A.

| Verificação | Resultado |
|---|---|
| `/portal/meus-casos` | só o caso de A; o de B não aparece |
| `GET /portal/casos/{caso_de_B}` | **404** — não vaza nem a existência |
| `/portal/documentos` | documento de B ausente |
| `/portal/financeiro` | honorário de B ausente |
| Anotação interna (`movimento tipo=nota`) | **não** aparece na resposta do portal |
| Campos estratégicos (`tese`, `pontos_fortes`, `pontos_fracos`, `chance_exito`) | ausentes |
| `/cases/`, `/clients/`, `/fees/`, `/deadlines/`, `/users/`, `/documents/upload`, `/ia-governanca/provedores` | **403** em todas |
| `PATCH /portal/casos/{id}` | **405** — portal é read-only |
| Criação da credencial externa | evento próprio `PORTAL_ACESSO_CRIADO` em `audit_logs` |

### Confidencialidade de documento — barreira dupla

A rodada anterior deu este ponto por conforme **sem prová-lo**: o upload usara
`confidencialidade="sigiloso"`, valor inexistente no enum, então o documento nunca foi
criado e a asserção passou por vacuidade. Refeito com os cinco níveis reais:

| nível | upload | gravado | publicar no portal | visível ao cliente |
|---|---|---|---|---|
| `normal` | 201 | `normal` | 200 | sim (esperado) |
| `interno` | 201 | `interno` | **422** | não |
| `restrito` | 201 | `restrito` | **422** | não |
| `confidencial` | 201 | `confidencial` | **422** | não |
| `segredo_justica` | 201 | `segredo_justica` | **422** | não |

Duas barreiras independentes: a publicação é recusada na origem **e** a listagem do
portal filtra por `confidencialidade = normal AND publicado_portal = true`. A coluna é
`NOT NULL DEFAULT 'confidencial'` — documento nasce fechado.

### Isolamento no RAG — sem vazamento cruzado

Semeados em `knowledge_docs`/`knowledge_chunks`, com **embeddings reais** (1024d,
`intfloat/multilingual-e5-large`) e um marcador único: peça interna do cliente A,
intimação do caso A1 de A, súmula pública, e uma peça de A **sem aprovação de curadoria**
como controle do gate.

| escopo da consulta | resultados | conteúdo restrito de A | doc não aprovado |
|---|---|---|---|
| sem escopo de cliente | 3 | ausente — fail-closed | ausente |
| cliente **B** | 3 | **ausente — sem vazamento cruzado** | ausente |
| cliente A | 5 | presente (o dono recupera) | ausente |
| cliente A, **outro caso** | 4 | só `peca_interna`; a intimação do caso A1 fica de fora | ausente |

A linha do cliente A é o que torna o teste não-vacuoso: o marcador *é* recuperável
quando deve ser, logo a ausência nas outras linhas é isolamento, não busca vazia.
O isolamento por caso (`_FILTRO_CASO_RAG`) funciona: `comunicacao_processual` do caso A1
não entra no contexto do caso A2 do mesmo cliente.

O gate de governança (`RAG_EXIGIR_APROVADO=true`) manteve o documento sem
`rag_status='aprovado'` fora de **todos** os escopos, inclusive o do próprio dono.

### Duas tentativas inválidas antes desta, registradas

A primeira execução deu 0 resultados em todos os escopos — inclusive o do dono. Se eu
tivesse lido só as três primeiras linhas, teria declarado "isolamento perfeito" sobre uma
busca que não retornava nada. Causas, ambas comportamento correto do sistema:
`EMBEDDINGS_ENABLED` é opt-in e estava desligado; e, com embeddings ligados, o gate
`RAG_EXIGIR_APROVADO` barrava o seed sem curadoria. **Busca vazia não é isolamento** — só
vale como prova o teste que recupera quando deve recuperar.

### 8-B.1 — a mensagem que o advogado lê (revisão da própria correção)

A correção do Achado 6 tornou o 422 **alcançável** num caminho onde antes tudo
respondia 201. Isso obriga a olhar o outro lado do §2 do prompt: o que aparece na
interface. `pages/Honorarios.tsx:133` faz `toast.error(e.response?.data?.detail || …)`, e
o `detail` de um erro do Pydantic é um **array de objetos**, não uma string.

Verificado: `components/Toast.tsx` já normaliza isso — achata o array, extrai `msg` de
cada item e junta com `·`. Não há `[object Object]`. Mas o texto exibido saía do próprio
Pydantic:

```
"Input should be greater than 0"
"Extra inputs are not permitted"
```

Inglês, num sistema cujo padrão declarado é o português; e a segunda não diz **qual**
campo está errado — justamente o dado de que o usuário precisa. A convenção do
repositório é outra: `schemas/case.py` escreve `raise ValueError("valor_contratual não
pode ser negativo")`.

Trocado `condecimal(gt=0)` por validadores próprios. O que a interface exibe agora:

| ação do advogado | toast |
|---|---|
| pagamento de −100 ou 0 | *valor do pagamento deve ser maior que zero (R$ 0,00 não é pagamento; estorno tem lançamento próprio)* |
| campo `forma_pagamento` | *campo(s) não reconhecido(s) em pagamento: forma_pagamento. Use apenas: data_pagamento, forma, valor.* |
| pagamento legítimo | 201, sem toast de erro |

`extra="forbid"` permanece como contrato declarado (aparece no OpenAPI) e como defesa em
profundidade; a mensagem legível vem do validador. Coberto por
`test_mensagens_de_erro_saem_em_portugues_e_nomeiam_o_problema`, que falha se a recusa
voltar a sair em inglês ou deixar de nomear o campo.

## 8-D. Rodada 5 — a interface renderizada (§77) — 22/08/2026

Primeira passagem no NAVEGADOR (Chromium sobre o Vite em :5173 → backend :8000).
Tudo até aqui provava backend e persistência; esta rodada olha o que o advogado vê.

### Estado das telas

Login pela tela, oito rotas percorridas, **zero erro de console**, nenhum marcador de
tela quebrada, nenhum `[object Object]`, nenhuma tela vazia:

| rota | caracteres renderizados | erros de console |
|---|---|---|
| `/` `/clientes` `/casos` `/prazos` `/tarefas` `/documentos` `/honorarios` `/agenda` | 1.123 – 3.793 | 0 em todas |

O ciclo completo do §2 fecha: ação de escrita pela interface → 422 do backend →
mensagem legível na tela. `components/Toast.tsx` achata o array de erro do Pydantic e
exibe *"valor do pagamento deve ser maior que zero…"*.

Verificado também que o dashboard **degrada graciosamente**: `DashboardUltra.tsx` usa
`Promise.allSettled` com um mapa `failed` por fonte, então o feed externo de notícias
(ConJur/JOTA) cair não derruba a tela. A falha de rede que registrei no primeiro
percurso era artefato meu — navegação abortando uma requisição lenta em voo.

### Achado 7 — o painel dizia "0 vencido(s)" com três prazos estourados (CORRIGIDO)

Só a tela expõe este: as duas leituras estavam na mesma página, uma ao lado da outra.

**Mecanismo — dois comportamentos corretos que se anulavam.** O job
`scheduler._marcar_prazos_vencidos` roda às 07:10 e move o prazo estourado de
`status='pendente'` para `status='vencido'`, alertando o responsável; existe exatamente
para dar visibilidade ao que venceu. Só que **três** consumidores contavam vencidos
filtrando por `status='pendente'`. Depois que o job rodava, a linha saía do filtro e o
número ia a zero. Entre a meia-noite e as 07:10 o painel estava certo; depois, zerava em
silêncio — o job que existe para expor o prazo vencido era o que o escondia do painel.
`ENABLE_SCHEDULER` é `True` por padrão, então isto vale para a instalação em produção.

O repositório já contava certo em **quatro** outros lugares — `routers/relatorio.py`
("Prazos vencidos sem conclusão"), `services/case_health.py`, `routers/indice_risco.py`
e `modules/dpt360/dashboard_service.py`. Os três divergentes eram a minoria, e eram
justamente os que o advogado lê ao abrir o sistema.

| local | critério antes | agora |
|---|---|---|
| `routers/dashboard.py` | `WHERE status='pendente'` | `status NOT IN ('concluido','cancelado')` |
| `services/dashboard_service.py` | `status='pendente' AND data_prazo < CURRENT_DATE` | idem acima |
| `components/DeadlineRiskStrip.tsx` | `GET /deadlines/?status=pendente` | busca `pendente` **e** `vencido` |

O `status` do backend é igualdade exata, então o radar do frontend nunca recebia a linha
vencida: contava zero por construção. As duas faixas juntas são o conjunto de prazos em
aberto; concluído e cancelado seguem de fora.

**Antes e depois, contra o mesmo banco (3 prazos com `data_prazo = 2026-05-29`):**

```
verdade no banco                     3
GET /api/dashboard/  antes    vencidos: 0
GET /api/dashboard/  depois   vencidos: 3
tela, antes     "0 vencido(s)"   e   "3 prazos vencidos"   (lado a lado)
tela, depois    "1 vencido(s)" no cenário de teste do componente
```

Regressões: `tests/test_dashboard_prazos_vencidos_dblevel.py` (5 casos contra Postgres
real, um deles provando que o critério antigo devolve 0 no mesmo cenário) e
`src/components/DeadlineRiskStrip.test.tsx` (3 casos). O teste do componente foi
conferido contra a versão com defeito: **falha 2 de 3**, e passa 3 de 3 com a correção.

### Por que este não apareceu nas quatro rodadas anteriores

As rodadas 1–4 exercitaram a API. `GET /deadlines/?status=vencido` respondia
corretamente, e eu tinha registrado o job como "verificado conforme" na rodada 3 — ele
está mesmo correto. O defeito só existia na junção: um contador que perguntava a coisa
errada a uma API que respondia certo. Nenhuma chamada isolada de API o revelaria; foi
preciso abrir a tela e ver dois números incompatíveis no mesmo lugar. É a demonstração
concreta do §2 do prompt — endpoint responder não significa que funciona.

## 8-E. Rodada 6 — proteções de IA não negociáveis (22/08/2026)

Verificação das travas que o CLAUDE.md marca como intocáveis (regras 4 e 13): gate
antialucinação de citações, HITL e sanitização de PII antes de provedor externo.

### Gate de citações — conforme, e melhor do que o esperado

Alimentado com citações fabricadas, o gate reprova com diagnóstico específico:

```
política vigente      bloquear   (CITACOES_POLITICA, default fail-secure)
bloqueia_aprovacao    true
  Súmula 9999 STJ     "fora da faixa plausível de STJ (1 a 676) — provavelmente não existe"
  Processo 0000001-…  "dígito verificador do número CNJ inválido (módulo 97,
                       Res. CNJ 65/2008) — o número como escrito não pode existir"
```

`response_validator` degrada fail-closed: se a verificação falhar, vira alerta e
`revisao_obrigatoria = True`, em vez de liberar. `AI_REQUIRE_HITL` é `True` por padrão.

Lacuna menor, sem falso positivo de aprovação: `artigo 42.789 do Código Civil`
(inexistente) não foi extraído do texto — o gate reprovou pelas outras duas citações,
mas essa não chegou a ser avaliada. Registrado, não corrigido.

### Achado 8 — cartão de crédito escapava da barreira de PII (CORRIGIDO)

`_sanitizar_messages_externo` é a última barreira antes de Anthropic/Groq e promete, na
própria docstring, mascarar "CPF/CNPJ/processo/RG/e-mail/telefone/CEP/**cartão**/PIX".
O cartão não estava coberto na prática:

```
entrada    "Cliente ..., cartao 4111 1111 1111 1111, ..."
saída      "Cliente ..., cartao 41[TELEFONE] 1111, ..."   <- 6 dígitos em claro
residual   []                                             <- a 2ª barreira dizia "limpo"
```

Duas causas somadas:

1. Os padrões são aplicados **em ordem**, e TELEFONE (índice 5) vem antes de CARTAO
   (índice 7). Sem guarda à esquerda, o padrão de telefone casava `11 1111 1111` no
   MEIO do cartão, quebrava a sequência e impedia o padrão de cartão de casar. Sobravam
   `41` e `1111` em claro — e rotulados como telefone.
2. `validar_sem_pii`, a **segunda** barreira, checava os índices 0-6, 9 e 10 — sem
   CARTAO (7) nem CHAVE_PIX (8). Cartão ou chave PIX residual passava como
   "nenhuma PII residual". A verificação que existe para pegar o que escapou da
   primeira barreira era cega justamente para o que escapava.

**Correção sem reordenar a lista** — o arquivo marca os índices 0-6 como referenciados
por `validar_sem_pii`, e `sanitizar_pii_interno` fatia `[2:]`: guarda `(?<!\d)` no padrão
de telefone (mesma posição) e inclusão de CARTAO e CHAVE_PIX na segunda barreira.

| entrada | antes | agora |
|---|---|---|
| `4111 1111 1111 1111` | `41[TELEFONE] 1111` | `[CARTAO]` |
| `4111111111111111` | `[CARTAO]` | `[CARTAO]` |
| `4111-1111-1111-1111` | `41[TELEFONE]-1111` | `[CARTAO]` |
| `(31) 98888-7777` | `[TELEFONE]` | `[TELEFONE]` (inalterado) |
| `+55 31 98888-7777` | `[TELEFONE]` | `[TELEFONE]` (inalterado) |

Cartão em processo não é hipótese remota: ação de consumo sobre fraude, contestação de
compra e revisão de contrato bancário trazem o número no documento.

Regressão: `tests/test_sanitizer_cartao_barreira_externa.py`, 11 casos, incluindo o
percurso real pelo `_sanitizar_messages_externo`. Conferido contra a versão vulnerável:
**falha 6 de 11**.

### Observação registrada, não corrigida

`31988887777` (telefone de 11 dígitos sem separador) é mascarado como `[CPF]`, porque o
padrão de CPF (índice 0) casa 11 dígitos seguidos e roda primeiro. **Não há vazamento** —
o dado é mascarado —, apenas o rótulo é impreciso. Corrigir exigiria mexer na ordem dos
índices 0-6, que o arquivo proíbe explicitamente; fica como dívida registrada.

## 8-F. Rodada 7 — regra jurídica: o motor de prazos (22/08/2026)

Prioridade 11 do prompt e regra 5 do CLAUDE.md ("toda regra jurídica precisa de fonte
oficial, vigência e teste"). É o módulo de maior risco do sistema: prazo errado é dano
irreversível. Cada resultado abaixo foi conferido **à mão** contra o texto legal, não
contra o próprio código. **Nenhuma divergência.**

### Calendário

| item | sistema | esperado |
|---|---|---|
| Páscoa 2026 (computus de Gauss) | `2026-04-05` | 05/04/2026 ✓ |
| Carnaval (segunda e terça) | `2026-02-16`, `2026-02-17` | Páscoa −48 e −47 ✓ |
| Sexta-feira Santa | `2026-04-03` | Páscoa −2 ✓ |
| Corpus Christi | `2026-06-04` | Páscoa +60 ✓ |

Os oito feriados nacionais fixos (01/01, 21/04, 01/05, 07/09, 12/10, 02/11, 15/11,
25/12) são corretamente não úteis.

### Contagem — CPC arts. 219 e 224

Intimação em segunda 24/08/2026, 15 dias úteis. Conferência manual: 25–28/08 (4),
31/08 (5), 01–04/09 (9), **07/09 feriado pulado**, 08–11/09 (13), 14–15/09 (15).
Sistema: `2026-09-15`. **Confere.**

O termo final nunca cai em dia não útil — testado em quatro datas de início
consecutivas, todas prorrogando corretamente (01/09+3 → 04/09; 02/09+3 → **08/09**,
saltando o feriado de 07/09 e o fim de semana).

### Suspensão do recesso — CPC art. 220

Intimação 10/12/2026, 15 dias úteis:

- com `aplicar_recesso=True` → `2027-02-02`. Manual: 11/12 (1) … 18/12 (6), suspensão
  integral 20/12–20/01, 21/01 (7) … 02/02 (15). **Confere.**
- com `aplicar_recesso=False` → `2027-01-19`, que respeita o recesso forense parcial
  legado 20/12–06/01. Manual: 11/12 (1) … 18/12 (6), 07/01 (7) … 19/01 (15).
  **Confere.** As duas faixas são deliberadamente distintas e estão documentadas no
  próprio arquivo.

### Regimes não se contaminam

Mesmo início, mesmo número de dias:

| dias | penal (CPP art. 798, contínuo) | cível (CPC, dias úteis) | trabalhista (CLT art. 775) |
|---|---|---|---|
| 5 | 31/08 | 31/08 | 31/08 |
| 10 | **03/09** | 08/09 | 08/09 |
| 15 | **08/09** | 15/09 | 15/09 |
| 30 | **23/09** | 06/10 | 06/10 |

A coincidência em 5 dias é prorrogação de fim de semana, não contaminação de regime —
os demais divergem como deve ser. Prazo em dobro no regime penal é **recusado**
(`ValueError: prazo em dobro do CPC não se aplica ao regime penal`), correto porque o
CPP não tem a figura dos arts. 180/183/186/229 do CPC.

Prazo em dobro no cível: 15 → `2026-09-15`; em dobro (30) → `2026-10-06`. Confere à mão.

### Conclusão

O motor de prazos é a peça mais bem construída que encontrei nesta auditoria: fonte
legal citada em cada regra, regimes isolados, calendário correto inclusive nos feriados
móveis, e falha explícita quando se pede algo juridicamente inexistente. Nenhuma
correção necessária.

## 8-G. Rodada 8 — HITL de peça: etiqueta ou trava? (22/08/2026)

Prioridade 10 do prompt e regra 4 do CLAUDE.md ("jamais remover HITL"). Marcar a saída
de IA como "rascunho" não é HITL se qualquer um puder aprovar sem revisar. A pergunta
auditada foi: **o rótulo é enforçado?** Exercitado contra a API, com peça real
`ai_generated=true`. **É enforçado, em sete camadas.**

| # | tentativa | resultado |
|---|---|---|
| 1 | peça de IA recém-criada | nasce `rascunho`, `human_reviewed=false` |
| 2 | aprovar sem observações de revisão | **422** — "Peças geradas por IA exigem observações de revisão humana" |
| 3 | observações só com espaços | **422** — `strip()` antes de validar |
| 4 | status após as tentativas | segue `rascunho` (nada foi gravado a meio caminho) |
| 5 | aprovar como perfil `estagiario` | **403** — `requer_advogado` (Prov. OAB 205/2021) |
| 6 | aprovar sem validação jurídica com score mínimo | **422** — `_bloquear_sem_validacao` |
| 7 | gravar `revisor_id` inexistente direto no banco | recusado pela FK `legal_docs_revisor_id_fkey` |

O item 6 foi surpresa: eu esperava que a aprovação legítima passasse, e ela é barrada por
um gate a mais — controle de qualidade exigindo validação jurídica revisada/aplicada com
score mínimo antes de `aprovada`/`final`/`protocolada`. Não é defeito; é rigor que eu não
tinha previsto no roteiro.

### Aprovação não pode ser "lavada" por edição posterior

A propriedade mais importante da cadeia, e a mais fácil de faltar num sistema desses:

```
antes    status=aprovada    human_reviewed=true   versao=2   revisor=222ec407…
         PATCH /legal-docs/{id}  {"conteudo": "texto alterado depois da aprovação"}
depois   status=em_revisao  human_reviewed=false  versao=3   revisor=<nulo>
```

Alterar o conteúdo de uma peça aprovada **rebaixa o status, apaga o revisor e incrementa
a versão**. Não existe o caminho "aprovo a minuta limpa e depois troco o texto": a peça
volta para revisão. É o que impede que a assinatura do advogado cubra um conteúdo que ele
não leu.

### `AI_REQUIRE_HITL` não é interruptor de segurança

Conferido nos dois estados: com a flag em `false`, `requer_revisao` vira `False`, mas
`is_rascunho` **permanece `True`**. O toggle controla a exigência de revisão formal, nunca
o rótulo de rascunho — coerente com o que `hitl_policy.py` documenta. Uma peça de IA nunca
se apresenta como definitiva, em nenhuma configuração.

Nenhuma correção necessária.

## 8-H. Correção de um achado meu: o SHA-256 de documentos (22/08/2026)

Ao reconferir o Achado 6 antes de deixá-lo no relatório, descobri que eu havia
descrito mal a **remediação**. Registro a correção porque achado de auditoria com
diagnóstico errado é pior do que achado nenhum: manda o titular orçar o trabalho errado.

**O que eu disse:** "corrigir exige coluna nova (migration, exceção §6-A)".

**O que o repositório tem, de fato:**

| peça | onde | estado |
|---|---|---|
| primitiva de hash em streaming | `services/document_hash_service.py` | pronta, não materializa o arquivo em memória |
| variante remota (Drive/rclone) | `services/document_remote_hash_service.py` | pronta |
| orquestrador de rescan/backfill | `services/document_rescan_service.py` | pronto, com classificação de divergências |
| tabelas de persistência | migration `142_document_hash_rescan` | criadas |
| despacho Celery/BackgroundTasks | `tasks/rescan_tasks.py::agendar_rescan` | **pronto** |
| testes | `test_document_rescan_service.py`, `test_document_rescan_integracao_dblevel.py` | existem |
| **quem chama `agendar_rescan`** | — | **ninguém**: nenhum router, nenhum job do scheduler |

Ou seja: o Épico #1019 A3.2 foi construído inteiro, incluindo a camada de despacho, e
parou antes do último fio. Não falta migration nem coluna para o caminho de rescan — as
tabelas estão lá. Falta **acionamento**: um endpoint administrativo ou uma entrada no
`scheduler.py`.

Ficam então dois itens distintos, com tamanhos muito diferentes:

1. **Ligar o rescan** — pequeno. Wiring de algo pronto e testado.
2. **Hash no momento do upload** — aí sim exige coluna em `documents` (migration) e é
   decisão à parte. É o que dá prova de integridade *desde a origem*, em vez de
   reconstruída por lote depois.

Nota de contexto: o primeiro defeito corrigido nesta auditoria (PR #1234) foi justamente
um `pytest.skip()` mal formado em `test_document_rescan_integracao_dblevel.py` — o teste
de integração **deste** serviço, que derrubava a coleta da suíte inteira. O rescan de
hash já tinha, portanto, dois problemas independentes: o teste quebrado e a ponta solta.

## 8-I. Rodada 9 — responsividade e acessibilidade (22/08/2026)

Prioridades 16 e 17 do prompt. Medição no Chromium em três larguras (celular 390,
tablet 820, desktop 1440) sobre cinco rotas. Só o que é objetivamente verificável por
máquina — não substitui auditoria humana de acessibilidade.

### Achado 9 — a barra de ações transbordava e escondia o botão primário (CORRIGIDO)

`PageHeader` (`components/UI.tsx`) declarava o container de ações como
`flex shrink-0 flex-wrap`. **As duas últimas classes se anulam:** `shrink-0` prende o
container à largura de `max-content`, então ele **transborda** em vez de quebrar a linha.
O `flex-wrap` estava lá, sem efeito.

Quatro páginas agravavam o quadro passando uma única linha `flex` como filho — com um
filho só, não há o que o pai quebre.

| rota | viewport | transbordo antes | depois |
|---|---|---|---|
| `/prazos` | tablet 820 | **116px** | **0** |
| `/casos` | celular 390 | **28px** | **0** |
| `/casos` | tablet, desktop | 0 | 0 |

No celular, o transbordo cortava o botão primário **"Novo caso por documento"** — o
advogado não conseguia tocá-lo. Não é estética: é a ação principal da tela inacessível
no aparelho que ele carrega no fórum.

**Correção (revisada — ver §8-L):** `lg:shrink-0` no `PageHeader` e `flex-wrap` nas
quatro páginas com linha de ações não-quebrável (`Casos`, `CentralRelacionamento`,
`Intimacoes`, `Pecas`).

> A primeira versão removia `shrink-0` por completo, e eu afirmei aqui que "no desktop o
> layout é idêntico ao anterior". **Era falso** — eu havia validado só `/casos` por
> captura de tela e generalizado para as 56 páginas. A medição de §8-L mostrou quatro
> páginas quebrando linha a 1440px. O breakpoint corrige isso.

Regressão: `src/components/PageHeaderAcoesQuebramLinha.test.tsx`. jsdom não tem motor de
layout, então o teste protege o **contrato de classes** que causou o defeito — exige
`flex-wrap` e proíbe `shrink-0` no container de ações. Conferido contra a versão com
defeito: **falha 1 de 3**.

### Registrado, não corrigido — exige decisão de design

| achado | onde | por que não corrigi |
|---|---|---|
| Dashboard `/` sem `<h1>` | todas as larguras | leitor de tela não anuncia o título da página inicial; escolher o texto e a posição é decisão de design |
| Salto de nível de heading em `/casos` | todas as larguras | idem — reestruturar hierarquia semântica |
| 1 campo de formulário sem rótulo acessível em `/casos` | todas as larguras | precisa saber qual rótulo é o correto |
| Alvos de toque abaixo de 24×24 (WCAG 2.2 AA, 2.5.8) | `button 17×17`, `53×17`, `30×23` | 14 controles em `/casos`, 37 em `/honorarios`, já **excluindo** links de texto inline (isentos pela norma). Aumentar área de toque mexe no design system |
| 1 de 6 elementos sem anel de foco visível no login | `/login` | navegação por teclado; precisa definir o estilo de foco da marca |
| `/honorarios` celular: 8px de transbordo | tira de abas com 1228px | a tira é rolável na horizontal **de propósito** (padrão móvel legítimo); mexer arrisca quebrar a rolagem. 8px é cosmético |

### Conforme

Zero imagem sem `alt` e zero botão sem nome acessível em todas as rotas e larguras.
`<html lang="pt-BR">` declarado — o leitor de tela usa a pronúncia correta.

## 8-J. Rodada 10 — jurimetria e Visual Law (22/08/2026)

Últimas duas frentes da lista. **Nenhum defeito.**

### Jurimetria — honestidade estatística verificada

Num sistema jurídico, taxa de êxito é número que muda decisão de estratégia e de proposta
de acordo. Uma taxa calculada sobre 2 casos e apresentada como "100% de êxito" é pior que
nenhuma taxa. Testado o cálculo direto:

| amostra | n | taxa_exito | com acordo | `amostra_suficiente` |
|---|---|---|---|---|
| 2 casos, ambos êxito | 2 | 100,0 | 100,0 | **false** |
| 4 casos, três êxitos | 4 | 75,0 | 75,0 | **false** |
| 5 casos, três êxitos | 5 | 60,0 | 80,0 | true |
| vazia | 0 | `None` | `None` | false |

`MIN_AMOSTRA = 5`. A distribuição bruta acompanha **toda** taxa, permitindo recálculo. A
amostra vazia devolve `None`, não zero nem divisão por zero. E há duas taxas separadas —
com e sem acordo — porque contar acordo como êxito infla o número.

Na interface, o denominador viaja junto: "Desfechos Reais — N casos encerrados",
`{total} ({pct}%)`, "Amostra: N decididos". Há ainda o aviso explícito *"Indicador
descritivo dos casos decididos do escritório. Não é modelo [preditivo]"*, e o endpoint
`/predicao-exito` está marcado `deprecated` em favor de `/analise-prospectiva` — a
renomeação acompanha a postura, em vez de vender previsão onde há descrição.

### Visual Law — determinístico por desenho

`visual_law_core.py` (linha do tempo, matriz de risco probabilidade × impacto com
tratamento contábil do CPC 25, badges de alerta, breakeven de acordo) é **100%
determinístico**, declarado no cabeçalho: *"sem IA — não inventa nada"*. É a escolha
certa: uma linha do tempo processual alucinada seria pior que a ausência do módulo. O
serviço homônimo que gera diagramas Mermaid por IA é outro arquivo e passa pelo
`ai_gateway`.

### Regra 4 do CLAUDE.md, verificada sistemicamente

*"Chamadas de IA sempre via `ai_gateway.py`; jamais chamar provider direto de um router."*

- Nenhum router importa `app.services.providers`, `anthropic`, `groq` ou `ollama`.
- O único módulo fora do gateway que toca `app.services.providers` é o `__init__.py` do
  próprio pacote.

Ou seja, não há rota de fuga: toda chamada de IA atravessa o ponto onde vivem o
kill-switch, a política de provedores e a sanitização de PII. O Achado 8 (cartão) importa
justamente por isso — aquela era a barreira única, e valia para tudo.

## 8-K. Rodada 11 — desempenho e banco sob volume (22/08/2026)

Prioridades 13 e 15. N+1 é o defeito que não aparece em teste: com 14 casos o sistema
responde em milissegundos e ninguém nota que fez 15 consultas em vez de 2; com 3.000, a
mesma tela trava. Por isso a medição foi feita **contando consultas de verdade**
(`pg_stat_statements` antes e depois de cada requisição), e repetida depois de carregar
volume realista de escritório: **2.014 clientes, 3.014 casos, 6.011 prazos, 4.021
honorários** — cerca de 215× o volume inicial. Dados fictícios, banco local descartável,
removidos ao fim.

### Nenhum N+1 — e isso é escalável por construção

| rota | 5 por página | 100 por página | veredito |
|---|---|---|---|
| `/cases/` | 8 consultas (5 itens) | 8 consultas (100 itens) | +95 itens custaram **+0 consultas** |
| `/clients/` | 8 (5 itens) | 8 (100 itens) | +95 itens, +0 consultas |
| `/deadlines/` | 8 (5 itens) | 8 (100 itens) | +95 itens, +0 consultas |
| `/fees/` | 8 (5 itens) | 8 (100 itens) | +95 itens, +0 consultas |

Contagem **constante**, independente do tamanho da página. Das 8 consultas, ~5 são
protocolo (BEGIN/COMMIT/ROLLBACK, typeinfo do asyncpg) e uma é a busca do usuário pelo
middleware de auth; o trabalho real são 2. É o resultado mais importante desta rodada
porque é **independente de escala**: contagem constante hoje continua constante com
30.000 casos.

### Latência sob volume real

| medição | resultado |
|---|---|
| `/dashboard/` (com 6.011 prazos) | mediana **4,0 ms** |
| `/cases/` 100 por página | mediana **12,2 ms** |
| `/deadlines/` 100 por página | mediana **13,4 ms** |
| paginação profunda, `page=30` (offset 2.900) | **17,7 ms** — mais rápido que a página 1 |
| busca global `q=Carga` (casa 3.000 registros) | **28,9 ms** |
| `/cases/stats` | **13,4 ms** |

Offset profundo é o assassino clássico de paginação e aqui **não degrada**. A consulta
mais lenta do banco inteiro no período foi de 1,24 ms.

### Concorrência — sem erro em nenhum nível

| simultâneas | mediana | p95 | resultado |
|---|---|---|---|
| 1 | 19,7 ms | — | 200 |
| 5 | 103,4 ms | 125,3 ms | 5× 200 |
| 20 | 51,1 ms | 259,1 ms | 20× 200 |
| 50 | 128,2 ms | 515,0 ms | 50× 200 |

Nenhum 5xx, nenhuma recusa por rate limit. Para um escritório com equipe de uma dezena
de pessoas, 20 requisições simultâneas já é folgado, e o p95 aí é 259 ms. O teto de
vazão em 50 simultâneas reflete a **premissa de worker único** que o próprio CLAUDE.md
declara — e para a qual o repositório já documenta o caminho de escala
(`RATE_LIMIT_REDIS_ENABLED=true` e `ENABLE_SCHEDULER=false` nos workers extras).

### Índices — o núcleo está certo

Todas as tabelas quentes têm índice na coluna pela qual o advogado filtra:
`deadlines.case_id`, `fees.case_id`, `fees.client_id`, `documents.case_id`,
`documents.client_id`, `legal_docs.case_id`, `case_movimentos.case_id`, `tasks.case_id`.

74 chaves estrangeiras não têm índice, mas o número isolado engana: a esmagadora maioria
é coluna de autoria (`created_by`, `aprovado_por`, `revisado_por`), que ninguém usa como
filtro. Filtrando pelas colunas que **de fato** são critério de busca neste domínio
(`case_id`, `client_id`, `user_id`), sobram **6 tabelas periféricas**:
`contratos_societarios`, `diario_oficial_alertas`, `diario_oficial_keywords`,
`inadimplencia_alerts`, `legal_chat_messages`, `preliminar_mensagens`.

**Não corrigido, e o motivo é honesto:** todas essas tabelas estão vazias no ambiente
local, então **não consegui medir impacto nenhum**. É observação estrutural, não problema
de desempenho demonstrado — e criar índice exige migration. Registrado para decisão.

### Limites desta medição — o que ela NÃO prova

- 3.000 casos é porte realista para o escritório, **não** é teste de estresse a 100 mil.
- Máquina local, sem rede, sem nginx no caminho, backend em modo desenvolvimento.
- Cada requisição do teste de concorrência abriu conexão TCP nova, o que **infla** os
  números de concorrência — o teto real de vazão é melhor que o medido.
- Os dados de carga são uniformes (todos `civil`/`aberto`), então a seletividade dos
  índices é mais otimista do que seria com dados reais variados.

## 8-L. Fechando o risco residual do Achado 9 — e uma afirmação minha que era falsa

No §8-I registrei que a correção do `PageHeader` alcançava as 56 páginas que usam o
componente, mas que eu só havia validado **quatro** por captura de tela; o resto era
raciocínio ("em telas largas nada muda, porque há espaço"). Em vez de deixar isso para
quem fosse integrar, medi.

**O raciocínio estava errado.** Percorri 20 rotas em 5 larguras (390, 820, 1024, 1280,
1440), medindo a caixa do container de ações e o transbordo da página, com e sem a
correção. A 1440px, quatro páginas mudavam de `647×34` para `540×75` — as ações
**quebravam em duas linhas numa tela larga**, onde antes cabiam numa só.

A causa: sem `shrink-0`, o subtítulo (`max-w-3xl`, até 768px) passa a disputar a linha
com as ações. Antes, `shrink-0` fazia o título ceder; depois, ambos encolhiam e as ações
quebravam. O transbordo sumia, mas ao custo de mexer no layout onde não havia problema.

**Correção da correção:** `lg:shrink-0` — abaixo de 1024px o container pode encolher e
quebrar (some o transbordo); de 1024px para cima o comportamento original volta.

### Medição final: 20 rotas × 5 larguras, contra o estado original

| largura | rotas com `PageHeader` | geometria idêntica ao original | transbordo antes | depois |
|---|---|---|---|---|
| 390 (celular) | 15 | 13 | 2 | **1** |
| 820 (tablet) | 15 | 10 | 4 | **0** |
| 1024 (médio) | 15 | **15** | 0 | 0 |
| 1280 (grande) | 15 | **15** | 0 | 0 |
| 1440 (desktop) | 15 | **15** | 0 | 0 |

De 1024px para cima, **nenhuma das 15 rotas muda um pixel**. Toda alteração de geometria
que sobrou corresponde a um transbordo eliminado:

- tablet: `/agenda`, `/intimacoes`, `/prazos`, `/tarefas` (116px cada) e `/casos`;
- celular: `/casos` (28px) e `/pecas`.

A medição também revelou que o defeito era **mais amplo do que eu havia diagnosticado**:
`/agenda`, `/intimacoes` e `/tarefas` também transbordavam 116px no tablet — eu só tinha
detectado `/prazos` e `/casos`. O transbordo remanescente no celular é o `/honorarios`
(8px, tira de abas rolável de propósito), já registrado no §8-I como cosmético.

O teste de regressão foi ajustado ao contrato novo: exige `flex-wrap`, proíbe `shrink-0`
**sem prefixo** e exige `lg:shrink-0`. Os dois regimes ficam travados.

### A lição, que vale além deste achado

Eu tinha escrito "em telas largas nada muda, porque há espaço de sobra" — plausível,
coerente com como flexbox funciona, e **errado**. O que salvou não foi revisar o
raciocínio com mais cuidado: foi trocá-lo por medição. É a mesma lição do Achado 7, onde
o defeito só apareceu quando dois números incompatíveis ficaram lado a lado na tela.

---

## 8-M. Revisão independente do Codex — três P1, todos procedentes (22/08/2026)

O titular pediu revisão do Codex no HEAD exato `7780e12a`, com instrução explícita de **não
tratar CI verde como substituto de revisão**. Voltaram três achados P1. Conferi os três
contra o código antes de aceitar qualquer um. **Os três procedem** — e um deles é regressão
introduzida por mim nesta mesma auditoria.

### Achado 10 — cartão de crédito de 13, 15 e 19 dígitos vazando inteiro (regressão minha)

O mais grave, e o mais desconfortável: **a minha correção do Achado 8 piorou o que não
consertou.**

O padrão de cartão exigia exatamente 16 dígitos. Um PAN de outro comprimento — AmEx (15),
Visa antigo (13), Maestro (19) — nunca casou nele. Só era mascarado por **acidente**: o
padrão de TELEFONE, que roda antes, mordia o final da sequência. Ao pôr a guarda `(?<!\d)`
no telefone para consertar o cartão de 16 dígitos, tirei o acidente:

| entrada `cartao 378282246310005` (AmEx) | saída | em claro |
|---|---|---|
| antes do Achado 8 | `cartao 37828[TELEFONE]` | 5 dígitos |
| **depois do Achado 8 (HEAD `7780e12a`)** | `cartao 378282246310005` | **15 dígitos** |
| depois desta correção | `cartao [CARTAO]` | nenhum |

E a segunda barreira respondia `[]` — "sem PII residual" — nos três casos. Uma barreira que
passou a mentir com mais confiança do que antes é pior do que a barreira original.

Medido nos cinco comprimentos, no HEAD `7780e12a`:

```
AmEx 15 sem separador   -> 'cartao 378282246310005'      residual=[]
AmEx 15 agrupado 4-6-5  -> 'cartao 3782 822463 10005'    residual=[]
Visa 16                 -> 'cartao [CARTAO]'             residual=[]   <- único coberto
Maestro 19              -> 'cartao 6011111111111111117'  residual=[]
Visa antigo 13          -> 'cartao 4222222222222'        residual=[]
```

**Correção:** padrão ampliado para 13–19 dígitos, mantida a posição no índice 7 (`validar_sem_pii`
e `sanitizar_pii_interno[2:]` dependem dos índices).

Um cuidado que o achado do Codex não mencionava e que o teste agora trava: nas alternativas
**agrupadas** o separador é obrigatório. Com separador opcional, o padrão atravessaria duas
datas vizinhas — `31-12-2026 01-01-2027` são 16 dígitos — e mascararia **data de audiência
como cartão**. Sobra-mascarar não é o lado seguro quando o dado engolido é um prazo.

Regressão em `test_sanitizer_cartao_barreira_externa.py`: 26 casos, **10 falham** no HEAD
anterior.

### Achado 11 — validação de honorário fechou um caminho que a tela não oferece

`FeeCreate` passou a exigir `valor` **ou** `percentual_exito` (Achado 5). O modal de novo
lançamento em `Honorarios.tsx` oferecia só "Valor (R$)". Resultado: o contrato de êxito
puramente percentual — o arranjo mais comum em ação indenizatória, que o schema declara
suportar — ficou **impossível pela interface**. O advogado ou batia num 422, ou preenchia um
valor fixo que não era o contratado, e aí o registro passa a dizer outra coisa sobre o
contrato.

Uma validação de backend que fecha um caminho legítimo porque a tela não tem o campo
correspondente não é correção completa — é meia correção com aparência de rigor.

**Correção:** campo "Percentual de êxito (%)" no formulário, com o texto de apoio dizendo que
um dos dois é obrigatório. Junto, o payload passou a descartar campo vazio: campo numérico
que o usuário esvazia vira `""`, e o Pydantic responde "Input should be a valid decimal" —
mensagem sobre digitação, quando a regra real é outra. Com **dois** campos numéricos onde
preencher um e deixar o outro vazio é o fluxo normal, isso deixou de ser detalhe.

Conferido em separado, sem defeito: `normalizarMensagemToast` (`components/Toast.tsx`) já
trata array de erro do Pydantic e extrai `msg` — a mensagem do 422 chega legível ao usuário.

Regressão em `HonorariosPercentualExito.test.tsx`: 3 casos, **2 falham** no HEAD anterior.

### Achado 12 — o radar de prazos contava só a primeira página

`GET /deadlines/` pagina: devolve no máximo `page_size` itens e a contagem real em `total`.
O `DeadlineRiskStrip` pedia 100 e contava **o tamanho do array**. Com 300 prazos vencidos,
exibia "100 vencido(s)".

É o mesmo defeito do Achado 7 — um contador de prazos que mente para menos — aparecendo por
**volume** em vez de por **status**. Consertei o eixo do status e não olhei o do volume, na
mesma tela e no mesmo componente.

**Correção:** pagina até o fim (página de 200, teto do backend; até 5 páginas). Passando
disso, o número vira piso explícito — `1000+ vencido(s)` — em vez de número errado. Vale
para os cinco contadores da tira, que saem todos da mesma lista.

Regressão em `DeadlineRiskStrip.test.tsx`: servidor falso que pagina de verdade e respeita
`page`/`page_size`; 6 casos, **2 falham** no HEAD anterior.

### O que esta rodada diz sobre as onze anteriores

Nenhum dos três é achado de estilo, e nenhum apareceu em onze rodadas minhas. O padrão
comum entre eles: **os três estão na borda da correção que eu mesmo tinha acabado de
fazer**. Consertei cartão de 16 dígitos e quebrei os outros comprimentos; exigi percentual
no schema sem olhar se a tela tinha o campo; consertei a contagem por status sem olhar a
contagem por volume — no mesmo componente.

Auditar o próprio remendo é exatamente o ponto cego que revisão independente cobre, e o
`governanca.yml` desligado (#1235) tira essa camada de todo PR do repositório. Registro
como argumento concreto para reativá-lo: aqui ela pegou três P1, um deles uma regressão de
LGPD que eu introduzi enquanto corrigia LGPD.

### Correção de contagem em comentário anterior do PR

Escrevi que `POST /fees/{id}/pagamentos` tinha "o único consumidor (`Honorarios.tsx:133`)"
ao justificar o `extra="forbid"`. São **dois**: o frontend e
`scripts/inventory/m34_honorarios_propostas_tests.py` (linhas 177 e 194). Fui ler o segundo
— envia exatamente `{valor, data_pagamento, forma}` nos dois pontos, nenhum campo extra. A
conclusão não muda; a contagem que escrevi estava errada.

---

## 8-N. Segunda revisão do Codex — quatro P1, e a lição sobre enumerar formato (22/08/2026)

O titular pediu revisão do HEAD `55eba9ef` com instrução explícita de confirmar que os três
P1 anteriores foram corrigidos **sem regressão**. Voltaram quatro P1 novos. Conferi os quatro
contra o código: **os quatro procedem.** Dois deles são correções minhas incompletas — a
mesma classe de erro que o §8-M já tinha registrado, agora com um agravante: **repeti a
técnica que falhou.**

### Achado 13 — PAN agrupado de 13 a 18 dígitos (segundo erro pela mesma causa)

Na rodada anterior ampliei o padrão de cartão **enumerando formatos**: contíguo, 4-4-4-4,
4-6-5. Um SHA depois, o Codex mostra que a enumeração continuou incompleta — todo agrupamento
fora da lista escapa:

```
'cartao 4222 2222 2222 2'     -> intacto,  residual=[]
'cartao 3782 822463 1000 5'   -> 'cartao 3782 [TELEFONE] 5'
```

O segundo é **o sintoma exato do Achado 8 reaparecendo**: o padrão de TELEFONE (índice 5)
roda antes do de cartão (índice 7), morde o miolo do PAN e deixa dígitos em claro rotulados
como telefone. Corrigi esse sintoma para 16 dígitos duas rodadas atrás e ele voltou por outro
comprimento.

**A causa não era o padrão — era a técnica.** "13 a 19 dígitos" não é um formato; é uma
**contagem**, e regex não conta dígitos através de separadores. Enquanto a regra estivesse
escrita como lista de formatos, sempre faltaria um.

**Correção:** `_MatcherCartao` — um objeto com a interface de `re.Pattern` (`sub`, `search`,
`finditer`) cuja regra é contagem, não formato. O regex delimita só o *candidato*; quem decide
é a contagem de dígitos.

Duas consequências de projeto que o achado não pedia:

1. **O piso de 3 dígitos nos grupos intermediários** impede a contagem de atravessar datas
   vizinhas: `2026-08-22 2027-09-30` são 16 dígitos. Sem esse piso, **data de audiência
   viraria cartão**. Sobra-mascarar não é o lado seguro quando o dado engolido é um prazo.
2. **O cartão passou para ANTES do telefone na lista.** Era o ponto que faltava: a lista é
   aplicada em ordem, e o telefone morde o miolo do PAN agrupado.

O segundo ponto tem uma história que vale registrar, porque envolve uma afirmação minha que
estava errada. O arquivo dizia *"reordenar a lista não é opção: os índices 0-6 são
referenciados"* — comentário que eu mesmo havia reforçado. Era exagero: **todas** as
referências de índice estão dentro do próprio `sanitizer.py` (`validar_sem_pii` e a lista da
variante interna), conferido por busca em `backend/app` e `backend/tests`. O que não pode é
reordenar sem atualizá-las.

Minha primeira tentativa aceitou o comentário como verdade e contornou: manteve o cartão no
índice 7 e aplicou uma passada extra na posição certa, dentro de cada função. Isso obrigava
**cada consumidor** a reimplementar a ordem — inclusive `ai/pseudonymizer.py`, que percorre
`_PATTERNS` por conta própria e está no caminho externo (`ai_gateway`). Editá-lo acionou o
gate de **certificação humana do núcleo jurídico de IA** (`ejc-release-gate.yml`), que exige
gold set humano-curado de 105 casos em 7 áreas — corpus que não existe no repositório e que,
por definição, não é meu para produzir. **CI vermelho, e a trava estava certa.**

Corrigir a premissa em vez de contorná-la resolveu as duas coisas: com a ordem certa dentro da
própria lista, todo consumidor herda a correção sem alteração, o núcleo de IA fica intocado e
o gate não dispara. O empate de 14 dígitos (CNPJ × Diners) resolve-se a favor do CNPJ só na
variante interna, que nunca sai do VPS.

Regressão: 45 casos no arquivo, **12 falham** no HEAD anterior — entre eles um que exercita a
pseudonimização reversível ponta a ponta, provando que o consumidor não editado ficou coberto.

### Achado 14 — o teto de páginas ainda subnotificava

Paginar até 5 páginas resolvia até 1.000 prazos e exibia `1000+` acima disso. O Codex apontou
o óbvio que eu não vi: **o `total` exato vem na primeira resposta e eu o estava descartando.**
"1000+" é piso, não contagem — subnotificação mais educada, não corrigida.

**Correção:** o contador de vencidos passa a ser `total` da faixa `vencido` (servidor, exato,
sem teto) **mais** os pendentes já estourados que o job das 07:10 ainda não virou — janela em
que os dois convivem. Os estourados são contados sobre a faixa `pendente` apenas, para não
depender de cada item trazer `status` e não somar ninguém duas vezes. A paginação continua,
mas só para os outros quatro contadores, que dependem de campo de cada item e não têm
agregação pronta.

### Achado 15 — o percentual salvo não aparecia em lugar nenhum

Consequência direta do Achado 11: liberei o cadastro percentual e não olhei a leitura. `Fee`
não declarava `percentual_exito`, a tabela renderizava só `fmtMoney(f.valor)` e os exports
CSV/PDF idem. Depois de salvar 20% de êxito, **a própria tela mostrava "—"**.

Corrigir a escrita e deixar a leitura para trás é meia correção pela metade oposta à do §8-M.

**Correção:** campo na tipagem, `quantoCobrar()` como definição única (tabela, CSV e PDF) e a
coluna do PDF renomeada para "Valor ou %".

### Achado 16 — percentual em tipo que o cálculo ignora

Com o campo novo e o tipo nascendo `fixo`, bastava preencher o percentual e salvar:
`FeeCreate` exigia "valor **ou** percentual", então passava — e `routers/honorarios_oab.py`
só lê o percentual quando `tipo in (exito, misto)`. Registro sem valor fixo e com percentual
que nenhum cálculo enxerga: **cobrança que existe no cadastro e não existe na conta**. Mesma
classe do honorário vazio que abriu este PR.

E o **meu próprio teste reproduzia a combinação**, por não trocar o tipo antes de postar.

**Correção:** `FeeCreate` recusa percentual fora de `exito`/`misto`, com mensagem que diz o
que fazer; o formulário só mostra o campo nesses tipos e limpa o valor ao trocar de tipo.
Nenhum caminho legítimo fechou — valor em reais segue válido em todos os tipos, e êxito com
piso contratado (os dois juntos) continua passando; ambos com teste.

### O que estas duas rodadas dizem

Dezesseis achados, e os oito últimos vieram de revisão independente — nenhum de onze rodadas
minhas. O padrão não é aleatório: **todos estão na borda de uma correção minha recém-feita.**
Duas vezes o mecanismo foi o mesmo — consertar um lado e não olhar o outro (escrita sem
leitura, status sem volume, um comprimento sem os demais).

O Achado 13 acrescenta um agravante que vale registrar: eu não só errei de novo no mesmo
ponto, **errei com a mesma técnica**. Enumerar formato falhou, e minha resposta foi enumerar
mais formatos. Só saiu do lugar quando a regra deixou de ser "casa este padrão" e virou
"conta os dígitos".

O `governanca.yml` desligado (#1235) tira essa camada de revisão de todo PR do repositório.

---

## 8-O. Terceira revisão do Codex — seis P1, quatro corrigidos e dois que não são meus (22/08/2026)

Seis achados P1 no HEAD `ac2bf010`. **Os seis procedem**, com uma ressalva de enquadramento
registrada abaixo. Quatro corrigidos aqui; dois exigem decisão do titular e estão descritos
com proposta, não implementados.

### Achado 17 — PAN com separador repetido (terceiro furo no mesmo ponto)

`4111  1111  1111  1111` — espaço duplo, como sai de cópia de PDF/OCR. O delimitador aceitava
`[\s.-]` (um só), o candidato nem era reconhecido, e os 16 dígitos seguiam intactos com
`validar_sem_pii` devolvendo `[]`.

É a **terceira** vez que o cartão volta, e as três pelo delimitador, nunca pela contagem:
primeiro só 16 dígitos contíguos, depois agrupamentos fora da lista, agora separador repetido.
A contagem estava certa desde o §8-N; o que continuava estreito era o que ela recebia para
contar.

**Correção:** `[\s.-]+`. `\s` inclui quebra de linha de propósito — PAN partido em duas linhas
por OCR é caso real num sistema que recebe documento digitalizado. O custo aceito é
over-masking de uma coluna de números de 4 dígitos cuja soma caia em 13–19. Trade deliberado:
over-masking degrada um prompt, under-masking vaza cartão para fora do VPS, e a prioridade
§71 põe LGPD (2) acima de UX (16). O piso de 3 dígitos nos grupos intermediários continua
segurando as datas — há teste para "2026-08-22  2027-09-30" com espaço duplo.

**Achado de limpeza, meu:** ao aplicar isso descobri que o `ac2bf010` tinha **duas** definições
de `_CARTAO_TRECHO` (linhas 29 e 133), resto da versão anterior desta mesma correção. Idênticas,
então sem efeito de comportamento — mas era duplicação que eu não tinha visto. Removida.

### Achado 18 — o teto de páginas ainda subnotificava, agora do outro lado

O §8-N usou o `total` exato da faixa `vencido`, o que resolveu **aquela** faixa. Os pendentes
já estourados continuavam vindo da lista paginada: com 1.200 deles (job das 07:10 atrasado), o
radar exibia `1000+`.

### Achado 19 — contar por status exibe prazo reagendado como vencido

Este é o mais interessante, porque foi **criado pela correção anterior**. `PATCH
/deadlines/{id}` usa `exclude_unset`, e `CentralAtividades.tsx:1259` envia só `data_prazo` ao
reagendar. Um prazo que estava `vencido` e foi remarcado para o futuro **mantém o status**. Ao
passar a contar pelo `total` da faixa `vencido`, o radar passou a exibi-lo como vencido.

Medido no `ac2bf010`, prazo com `data_prazo: 2026-12-01` e `dias_restantes: 101`:
`ROTULO RENDERIZADO: 1 vencido(s)`.

**Ressalva ao enquadramento do Codex.** Ele afirma que a consulta de `dashboard.py:99-109`
*"incluí-lo simultaneamente entre os próximos 3/7 dias"*. Não é simultâneo: `data_prazo < hoje`
e `BETWEEN hoje AND d3` são mutuamente exclusivos, e a consulta classifica **pela data**. O
dashboard está correto — conta esse prazo em "próximos", que é onde ele deve estar. Quem
passaria a divergir é o radar. Ou seja: eu teria recriado o defeito do Achado 7, dois painéis
mostrando números diferentes para o mesmo fato.

**Correção de 18 e 19, a mesma:** o contador passa a consumir `GET /dashboard/` →
`prazos.vencidos`, que é agregação de servidor, **por data**, sem teto e atravessando as duas
faixas. Sem ela (endpoint fora do ar), degrada para o cálculo local com o `+` de piso — o radar
não some nem mente. Há teste para a degradação.

Detalhe do teste que vale registrar: o primeiro falso servidor que escrevi contava só a faixa
`vencido`, e um teste falhou. O erro era do **mock**, não do código — um falso servidor que não
imita a regra real testa a coisa errada. Passou a contar por data, como o backend.

### Achado 20 — valor e percentual juntos, só o valor aparecia

`quantoCobrar` tinha retorno antecipado no valor fixo. Com os dois contratados — combinação que
o próprio formulário passou a permitir no §8-M — a tabela e o PDF mostravam só os reais. O
registro dizia menos do que o contrato. Corrigido: os dois, unidos por `+`.

### Achados 21 e 22 — NÃO corrigidos: exigem decisão de regra financeira

Os dois são reais, verificados no código, e **não implemento sozinho** porque a resposta é uma
regra de negócio/jurídica, não uma escolha de implementação (§10 e regra 5 do `CLAUDE.md`:
"toda regra jurídica precisa de fonte oficial, vigência e teste").

**21. Honorário só-percentual não tem como ser quitado.** `routers/fees.py:266`:

```python
if fee.valor and Decimal(total_pago) >= fee.valor:
```

Com `valor=None`, `quitado` é sempre `False`, o status nunca sai de pendente, e o rateio de
êxito — condicionado a `status === "pago"` na tela — nunca abre. **A decisão que falta:** o
valor devido é `percentual × proveito`, e `proveito` não vive no honorário. Ou o lançamento
passa a registrar o proveito realizado, ou a quitação de honorário percentual ganha regra
própria. Proposta: registrar o proveito no momento do pagamento e derivar o devido dali.

**22. Com valor e percentual, o teto ético ignora o percentual.**
`routers/honorarios_oab.py:526-529` usa `if f.valor: ... elif ... percentual_exito`. Existindo
valor, o percentual nunca entra no teto — o que **subestima** os honorários e pode deixar de
emitir o alerta de 50%. Num cálculo que existe para sinalizar limite ético da OAB, errar para
menos é o lado ruim de errar. **A decisão que falta:** com os dois contratados, o teto usa a
soma, o maior, ou o percentual como piso? São regras contratuais diferentes, com resultados
financeiros diferentes.

**O que fiz enquanto não há decisão:** parei de *convidar* a combinação. O texto de apoio do
formulário dizia "ou os dois (êxito com piso contratado)" — eu estava anunciando um arranjo que
o cálculo ignora. Agora ele diz explicitamente que, preenchendo os dois, o teto é calculado só
sobre o valor fixo. Continuar aceitando é correto (dados existentes podem ter os dois, e
recusar quebraria fluxo), mas anunciar sem ressalva não era.

### O que esta rodada acrescenta

Vinte e dois achados, treze deles de revisão independente. O Achado 19 é o exemplar mais claro
do padrão: **a correção anterior criou o defeito seguinte**. Consertar a contagem trocando de
eixo (de status para total-por-status) resolveu o volume e abriu a divergência de data. Só
saiu do lugar ao parar de contar no cliente e consumir a agregação que o servidor já fazia
certo — a mesma que o Achado 7 tinha consertado, e que eu não usei quando deveria.

---

## 8-P. Achado 23 — o gate antialucinação estava cego para a forma dominante (22/08/2026)

Rodada iniciada por conta própria, a partir de um item que eu havia **registrado e não
corrigido** nas rodadas anteriores: "o extrator de citações não pega um `artigo 42.789`
fabricado". Fui medir e o achado era muito maior do que eu tinha anotado.

### O que estava registrado × o que a medição mostrou

Eu tinha registrado um caso pontual, de artigo inventado. Medindo 12 formas de citar no HEAD
`8b65cc11`, **5 passavam sem serem sequer extraídas** — e não são formas exóticas:

| forma | extraído |
|---|---|
| `art. 927 do CC` (sigla) | ✅ |
| `artigo 927 do Código Civil` | ❌ |
| `artigo 300 do Código de Processo Civil` | ❌ |
| `artigo 5º da Constituição Federal` | ❌ |
| `artigo 477 da Consolidação das Leis do Trabalho` | ❌ |
| `artigo 14 do Código de Defesa do Consumidor` | ❌ |
| `art. 1.234 do CPC` (separador de milhar) | ❌ |
| `artigo 42.789 do Código Civil` (fabricado) | ❌ |

O artigo 927 do Código Civil é a cláusula geral de responsabilidade civil. Se a citação mais
frequente do direito brasileiro não é extraída quando escrita por extenso, o gate não estava
protegendo peça nenhuma contra citação inventada nessa forma.

**Citação não extraída é citação não verificada.** O gate só bloqueia o que enxerga, e
`CLAUDE.md` (regra 4) trata contornar o citation gate como inegociável — um gate cego para a
forma dominante não precisa ser removido, ele já não age.

### Causa

`_RE_ARTIGO` exigia duas coisas que a redação natural não entrega:

1. **Sigla de uma lista fechada** (`cf|cpc|cc|clt|cdc|cpp|cp|ctn|lei nº`). Diploma escrito por
   extenso — a forma que uma peça usa — não casava.
2. **Número de até 4 dígitos sem separador.** `\d{1,4}` não abrange `1.234`, e a janela
   `[^.;\n]{0,45}` entre número e diploma **proíbe ponto**, então o separador de milhar
   quebrava o casamento duas vezes.

### Correção, e o cuidado que quase virou outro defeito

Diploma por extenso passa a casar, e o número aceita separador de milhar dentro do próprio
grupo. Mas a parte que importa é a **normalização**: `citation_check._restringir_ao_diploma`
procura a chave em `_SLUG_POR_DIPLOMA`, que só conhece siglas. Extrair `Código Civil` sem
normalizar para `CC` faria o lookup falhar — e pela política P0.1, artigo não confirmado
**bloqueia a aprovação**. Ou seja: corrigir a cegueira sem normalizar teria trocado "citação
inventada passa" por "citação legítima bloqueia". `_canonizar_diploma` fecha isso, e há teste
exigindo a sigla, não só a extração.

Um segundo cuidado, medido: a janela entre número e diploma **continua proibindo ponto**.
Cheguei a testar uma versão permissiva, que fazia o padrão atravessar fim de frase —
`"Vendeu o art. 42 ontem. O Código Civil regula..."` pareava o artigo de uma frase com o
diploma da seguinte, criando citação inexistente que, sendo inconfirmável, bloquearia a peça.
Preferi a limitação conhecida: a forma com abreviação no meio (`art. 5º, inc. II, da CF`)
segue não extraída, e está registrada como tal.

Detalhe de implementação que evitou acionar trava: a correção fica em
`verificador_jurisprudencia.py`, que **não** casa o padrão do gate de certificação humana do
núcleo de IA. `citation_check.py` casa (`services/citation[^/]*\.py`) e não foi tocado — a
normalização foi feita do lado do extrator justamente para não precisar mexer lá.

### Verificação

`test_citacao_artigo_diploma_por_extenso.py`: 24 casos, **13 falham** no HEAD anterior. Cobrem
as 10 formas por extenso, o separador de milhar, o artigo fabricado, o que já funcionava (para
não regredir), 4 textos que **não** podem virar citação, e 3 travessias de fim de frase.

### O que este achado diz sobre os anteriores

Ele não veio de revisão externa: veio de eu reler a minha própria lista de "registrado e não
corrigido" e **medir em vez de reler a anotação**. A anotação dizia "não pega um artigo
fabricado" — verdadeiro, e enganosamente pequeno. O defeito real era estrutural.

Vale como método: item registrado numa auditoria não é item entendido. A anotação carrega o
tamanho que o problema tinha aos olhos de quem passou correndo por ele.

---

## 8-Q. Achado 24 e uma varredura que fechou mais itens do que abriu (22/08/2026)

Mudança de método pedida pelo titular: parar de serializar cada correção num ciclo
*corrige → empurra → espera CI → espera revisão*. O portão local roda exatamente o que o CI
roda; o GitHub passa a ser registro, não etapa. Esta rodada foi inteira local, com a stack de
pé (Postgres 16 + pgvector, 147 migrations do zero, backend em :8011).

### Primeiro resultado: metade da lista registrada já estava corrigida

A lista de "armadilhas confirmadas em produção" do `CLAUDE.md` descreve a auditoria externa de
**julho, contra produção**. O repositório andou desde então, e re-corrigir o que já foi
corrigido é desperdício. Medido:

| item registrado | estado real |
|---|---|
| smoke E2E roda contra produção | **já protegido** — `run_fictitious_smoke.py:1025` recusa alvo fora de staging/homolog/localhost sem `EJC_ALLOW_PRODUCTION_E2E=true` |
| `?status=all` devolve 500 | **já corrigido** — `validar_status_caso` devolve 422; o comentário no código diz "era o caso de `?status=all`" |
| exclusão de caso não cascateia | **protegido** — `DELETE /cases/{id}` devolve 422 com a lista de pendências e manda arquivar |

Ponto fraco anotado e não corrigido: o guard do smoke testa substring na URL inteira, então
`https://…adv.br/?x=staging` passaria. Verificar o **hostname** seria mais firme.

### Achado 24 — documento juntado sem prova de integridade

Prioridade 8 (documentos). O EJC é sistema de prova documental: o hash é o que sustenta que o
arquivo juntado hoje é o mesmo de amanhã.

A maquinaria de SHA-256 existia **inteira** desde a migration 142 — serviço local, variante
remota via rclone, `document_rescan_service`, task de backfill. Faltava o começo:
`POST /documents/upload` não calculava nada e `documents` não tinha coluna (25 colunas,
nenhuma de integridade). O SHA-256 existente vivia só em `document_intake_items`, alimentada
apenas pelo fluxo de intake — documento juntado **pela tela** ficava sem evidência nenhuma.

**Correção:** migration `147_documents_sha256_integridade` (coluna nullable + índice), campo no
model, e o cálculo no upload a partir dos bytes que já estão em memória — sem I/O extra, sem
reler o disco.

`nullable=True` é decisão, não descuido: documento anterior à coluna **não tem** hash, e `NULL`
diz isso. Preencher com qualquer coisa fingiria integridade que ninguém verificou. O backfill
é do rescan, que sabe ler arquivo local e remoto.

**Correção de uma afirmação minha.** Numa rodada anterior escrevi que corrigir isto "exige
coluna nova — migration, exceção §6-A" e parei aí. A parte da migration era verdadeira; a
frase dava a entender que faltava construir a maquinaria, quando faltavam a coluna e o caller.

**Verificação — migration:** aplicada do zero (147 de 147), coluna `varchar(64) NULL` e índice
`ix_documents_sha256` conferidos no `information_schema`, downgrade removendo limpo
(`count=0`) e re-upgrade voltando ao head.

**Verificação — comportamento (§2: "HTTP 201 não significa que funciona"):** três uploads reais
pela API, hash conferido **na coluna do banco**, não na resposta:

```
peticao.pdf   201  SIM  894ab840abcc452b290fb660e5ba177b51f5af28dda2a39797ac4cdd47f3a3ff
contrato.pdf  201  SIM  66e1ca419a01264b33989494203672cfe94542e0ec87f4b435c1c5062876ff1e
peticao.pdf   201  SIM  a12c7e0a164a9f0e96b869f913c48ccfa36f94386669b47e24ca41ef883d2fed
conteúdos diferentes geraram hashes diferentes: True
documentos sem hash: 0 de 3
```

Regressão: 4 casos, **2 falham** sem a correção.

### Dois falsos positivos meus, pegos antes de virarem achado

Registro porque o padrão é o mesmo das rodadas anteriores — e desta vez quem produziu o erro
foi o meu instrumento.

**1. "ÓRFÃO: 4 peças, 1 prazo, 1 honorário".** O roteiro contou dependentes vivos depois de um
`DELETE` que devolvera **422**. O caso não fora excluído; os dependentes estarem vivos era o
comportamento correto. Veredito que não confere o passo anterior é ruído.

**2. "Arquivar removeu o prazo dos indicadores".** O dashboard marcou 0 **antes e depois** do
arquivamento — e marcava 0 já com o prazo criado. Não era arquivamento: é o cache de 30 s
(`_DASHBOARD_TTL_S`). Medindo fora da janela, o dashboard confere **exatamente** com o banco
(`vencidos=1 criticos3d=2 proximos7d=3`, `degradado=[]`).

### Registrado como decisão, não como defeito

**Prazo de caso arquivado continua contando.** Medido: `GET /deadlines/?status=pendente`
devolve o prazo de um caso arquivado, e o dashboard o conta. Não corrijo por conta própria, e
a razão é jurídica: prazo processual não desaparece porque o caso foi arquivado
administrativamente, e esconder um prazo real é o dano de prioridade 3 que este sistema
existe para evitar. O comportamento atual é o lado seguro do erro. Se o titular decidir que
arquivar deve encerrar os prazos, é mudança de regra, com fonte e teste.

**Telefone de 11 dígitos rotulado `[CPF]`.** Medido: `31988887777` → `[CPF]`. Ambos são
**mascarados** — não há vazamento, é rótulo errado. Distinguir exigiria validar o dígito
verificador do CPF, mexendo de novo na camada de PII que já produziu três achados hoje. O
custo supera o ganho enquanto o dado está protegido.

### O gate de deploy reprovou a minha migration — e estava certo

A primeira versão da `147` trazia guarda de idempotência por introspecção
(`op.get_bind()` + `if "sha256" not in cols`). A suíte completa reprovou em
`test_migrations_reais_passam_no_gate.py`:

```
147_documents_sha256_integridade.py: linha 39: estrutura dinâmica Assign exige revisão humana;
linha 40: estrutura dinâmica If exige revisão humana; linha 39: op.get_bind exige revisão
```

O repositório exige migration **analisável estaticamente**: uma que ramifica em tempo de
execução não pode ser conferida antes de ir para produção. A defesa que eu tinha posto por
hábito era exatamente o que a trava existe para barrar — e o Alembic já garante execução única
pela tabela de versão. Reescrita declarativa, revalidada em banco limpo: aplica, cria coluna e
índice, downgrade remove (`count=0`).

As outras quatro falhas eram os guards de head fixado em `146` — atualizar é a manutenção
deliberada que eles existem para forçar quando alguém adiciona migration. Atualizados para
`147` em `test_alembic_single_head.py`, `test_schema_dr_parity.py` e
`test_preliminares_fundacao_schema_140.py`.

Vale o registro de método: **eu não teria descoberto nenhuma das cinco pelo caminho antigo**
sem esperar o CI. O portão local pegou tudo em dois minutos — que é o argumento do titular
para trabalhar localmente e deixar o GitHub para o fim.
