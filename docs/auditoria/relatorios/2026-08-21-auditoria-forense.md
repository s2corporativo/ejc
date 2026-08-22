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
que o upload direto não alimenta. A migration `142_document_hash_rescan` criou
um *backfill* — a ausência é conhecida; a origem segue sem gerar. Corrigir exige
coluna nova (migration, exceção §6-A) e é escopo próprio.

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

**Correção:** `valor: condecimal(gt=0)` (zero não é pagamento) e
`model_config = ConfigDict(extra="forbid")`. O frontend (`pages/Honorarios.tsx`) já
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
