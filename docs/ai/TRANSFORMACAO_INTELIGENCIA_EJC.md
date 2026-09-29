# TRANSFORMACAO DE INTELIGENCIA DO EJC — indice unico de progresso

> Documento indice do programa de evolucao do nucleo de IA juridica do EJC
> (17 modulos, referencias do pedido do titular). **Este arquivo nao e um
> relatorio**: por modulo, ele aponta o estado, o PR e a evidencia. A causa-raiz,
> a implementacao, os testes, o rollback e a nota de publicacao vivem no corpo do
> PR — duplicar aqui foi o que deixou as tabelas divergirem do que o PR dizia.
>
> Regra de precedencia: `docs/GOVERNANCA_IA.md` → `CLAUDE.md` → `AGENTS.md` →
> este indice. Em divergencia, o canonico prevalece e a divergencia e
> corrigida aqui.

## 0. Identificacao

| Item | Valor |
|---|---|
| Issue coordenadora | [#1901](https://github.com/s2corporativo/ejc/issues/1901) |
| Repositorio | `s2corporativo/ejc` |
| Baseline declarado (medicao do titular) | `7034f2bbcea7924ffdccc2f85fd1d9433a4b14c5` |
| `main` de referencia desta medicao | `d688d58` (2026-09-29) |
| Ambiente de execucao local | `C:\Users\User\.agent-browser` — arvore de trabalho **sem `.git`** (ver bloqueio 1); clone de publicacao em `.publish/ejc` · Python 3.14.7 · Windows 11 |
| Data de inicio do ciclo | 2026-09-29 |

### Bloqueios de ambiente

1. **Sem repositorio git local.** A arvore de trabalho nao tem `.git`; branch,
   commit e PR passaram a ser feitos no clone `.publish/ejc`, autenticado como
   `s2corporativo` (config **repositorio-local**; nenhum `git config --global`
   foi alterado). A arvore de trabalho segue dessincronizada da `main` e **nao e
   fonte de verdade** — a `main` e o PR sao.
2. **Treze arquivos de teste nao importam no Windows** (`fcntl` ausente em
   `app/services/backup_lock.py`; `googleapiclient` ausente). Erro ambiental,
   pre-existente, alheio a area de IA. Afeta backup/health/readiness.
3. **CI.** O GitHub Actions da conta esta indisponivel desde ~22/08. A esteira
   real e o **Woodpecker** (`.woodpecker.yml`), que roda testes e *valida* o
   script de deploy, mas nao faz deploy. Ate 2026-09-29 os checks apareciam
   como `pending` por conta disso; ao revalidar, o Woodpecker executou e passou
   — entao a verificacao nao esta mais indisponivel, e o portao local (abaixo)
   continua sendo a evidencia oficial exigida pelo repositorio.

### Portao de verificacao (local, proporcional ao diff)

`ruff check app` limpo + `pytest` da area alterada + suite completa antes do
push. A arvore sem git nao roda suite: ela nao tem os testes novos.

## 1. Baseline medido

Medido por leitura de codigo e coleta de testes, na `main` de referencia.

| Medida | Valor | Como foi medido |
|---|---|---|
| Casos no gold set | 10 candidatos, 0 atestados (`atestado_por` vazio em 10/10) | `app/eval/gold_set_ia_candidatos.jsonl` |
| Cenarios sinteticos do benchmark | 10 cenarios, 17 questoes esperadas | `app/eval/benchmarks/legal_bench.synthetic.jsonl` |
| Resposta vazia na nota agregada | **0.00** — defeito C ja corrigido na `main` | `score_structured_answer(case, {})` medido na `main` |
| Modulos/routers de IA | 13 routers `ia_*`/`ai_*` + 6 servicos de gateway/guard | `backend/app/routers/` |
| Saidas para provider fora do gateway | 0 (esperado) — `AsyncAnthropic`/`AsyncOpenAI` so em `ai_gateway.py` e `providers/anthropic_provider.py` | grep |
| Rotas de governanca sem guard | 0 — as 13 rotas de `ia_governanca.py` usam `_req_admin_socio` | leitura |
| Streaming de IA | **existe** em uma superfície: `POST /ia/agente/stream`, `ia_agente.router` registrado em `main.py:467`, devolve `EventSourceResponse` (SSE dos eventos do loop) | `main.py:89,467` · `routers/ia_agente.py:35` |
| Streaming de token do **provider** | inexistente (`stream: False` no sistema) | leitura |
| Controle de desligamento da IA | `AI_PROFILE`, `AI_ENABLED`, `AI_EXTERNAL_PROVIDERS_ALLOWED` e flags por provider, em `backend/app/core/config.py`. **Nao existe** `AI_CLAUDE_KILL_SWITCH` — nenhuma camada tem kill-switch dedicado | `git grep` na `main` |

**Nao medido / nao verificavel aqui:** corpus RAG em producao (exige VPS),
conectividade a DataJud, custos reais, numero de casos juridicos reais (zero por
definicao — o gold set so tem candidatos).

### Matriz de inventario: capacidade → implementacao → estado

| Capacidade | Servico real | Estado |
|---|---|---|
| Chamada a provider (fonte unica) | `ai_gateway.chat` / `executar_tarefa_ia` | **existente e validado** (barreira de PII) |
| Log de auditoria de IA | `ai_guard.registrar_ai_log` + `AILog` | **em correcao** — PR #1903 (ver §3) |
| Recuperacao RAG com escopo | `ai_service.buscar_contexto_rag` | **existente e validado** (filtro fail-closed) |
| Rerank + governanca de fonte | `ai/reranker.py` | **existente** — penalidade de governanca em duas escalas, achado aberto |
| Pertinencia de citacao | `ai/pertinencia.py` | **existente e validado** |
| Gate de citacoes (HITL) | `citation_gate.py` | **parcial** — aplicado na aprovacao HITL, nao na entrega |
| Guardrails juridicos | `ai/juridico_guardrails.py` | **parcial / aberto** — `ja_corrigido` confia no marcador `MARCADOR_CORRECAO_MERITO in texto`; resposta de modelo que reproduza o marcador **pula** a correcao deterministica. Anti-falsificacao pendente |
| Deteccao de questoes | `legal_brain/issue_engine.py` | **em correcao, concorrente** — ver §4 |
| Avaliacao (regua) | `eval/legal_bench.py` | **ja corrigido na `main`** por `5bd6ac7` |
| Gold set juridico | `eval/gold_set_ia_candidatos.jsonl` | **nao homologado** — 10 candidatos, 0 atestados |
| Loop de agente | `ai/agent/loop.py` | **parcial** — budget sem timeout; sem leitura de kill-switch |
| Fila de jobs | `ai/jobs/` | **nao existe na `main`** — ver §4 |
| Skills por area | `seeds/skills_*.py` + `ai_skill_service` | **parcial** — 11 lacunas nativas |
| Manus como planejador | — | **nao implementado** |
| Estado persistente caso→tese→peça→decisao | parcial (`matriz_teses_service`) | **parcial** |
| Radar / memoria juridica | — | **nao implementado** |
| Ferramentas autorizadas (Tool Broker) | `ai/agent/` | **parcial** |
| Simulacao decisoria | `ai/adversarial.py` | **existente** — nunca bloqueia, por desenho |

## 2. Estado por modulo

| Modulo | Estado | PR | Evidencia |
|---|---|---|---|
| 0 — Inventario e baseline | medido | — | §1 |
| 1 — P0 logging e protecao de dados | **CORRIGIDO, aguardando merge** | [#1903](https://github.com/s2corporativo/ejc/pull/1903) | §3 |
| 2 — Upload e ingestao segura | em diagnostico | — | — |
| 3 — Regua de avaliacao | **ja corrigido na `main`** (`5bd6ac7`) | — | medido: resposta vazia = 0.00 |
| 4 — Deteccao de questoes | **em correcao, concorrente** | [#1866](https://github.com/s2corporativo/ejc/pull/1866) em voo | §4 |
| 5 — Nucleo unico e provedores | **inexistente na `main`** | — | §4 |
| 6 — RAG, fontes e validade | em diagnostico | — | achados 1–12 |
| 7 — Pesquisa iterativa | em implementacao | — | — |
| 8 — Estado persistente / Tool Broker | em implementacao | — | — |
| 9 — Manus subordinado | em implementacao | — | — |
| 10 — Leitura documental | em implementacao | — | — |
| 11 — Provas e contradicoes | em implementacao | — | — |
| 12 — Teses e estrategia | em implementacao | — | — |
| 13 — Adversarial e simulacao | em implementacao | — | — |
| 14 — Memoria e radar | em implementacao | — | — |
| 15 — Skills e gold set | em implementacao | — | — |
| 16 — Benchmark, custos, observabilidade | em implementacao | — | — |
| 17 — Shadow / homologacao / rollout | em implementacao | — | — |

## 3. Modulo 1 — P0 logging e protecao de dados

**Relatorio completo no corpo do PR #1903** (causa-raiz, correcao, portao e
rollback). Em uma linha: `AILog.prompt_sanitizado` e `resposta` recebiam a
versao **reidratada** do prompt/ resposta — com PII real em claro; o patch leva
a versao pseudonimizada junto do `GatewayResponse`, restringe o cache a ela e
estende a barreira do model a `prompt_sanitizado`.

Correcoes de review aplicadas no mesmo PR (4 threads P1 do codex-connector,
resolvidas): o marcador `LEGAL_DOC_ID:<uuid>` era destruido pelo pseudonimizador
(casava com chave Pix) e quebrava a contagem `pecas_sem_validacao` de
`ia_governanca.py`; e o sanitizador, sem as entidades do caso, deixava passar
marca comercial de uma palavra.

## 4. Modulo 4 e Modulo 5 — nao publicaveis como correcao

**Relatorio completo no corpo dos PRs correspondentes.** O essencial para quem
ler so este indice:

- **Modulo 5 — as rotas de job nao existem na `main`.** `ai/jobs/`, `ia_jobs.py`
  e o proprio teste de regressao estao **apenas na arvore local**; nenhum dos
  PRs abertos os contem. **Nao estao operacionais** — sao experimento local nao
  publicado. Landar a correcao implicaria introduzir a subcamada inteira, o que
  e decisao de produto, nao de bug. Enquanto nao houver decisao, nenhum modulo
  pode tratar "fila de jobs" como capacidade disponivel.
- **Modulo 4 — defeito aberto, porem `#1866` em voo** no mesmo arquivo. Medido
  contra o branch do `#1866`: 10 falham / 16 passam, ou seja, resolve
  parcialmente. Publicar em paralelo criaria branch concorrente no mesmo
  arquivo. Decisao do titular: deixar o `#1866` seguir ou substitui-lo.

## 5. Licao de metodo (obrigatoria em qualquer proximo ciclo)

A arvore de trabalho nao tem git e estava dessincronizada da `main`. Publicar
a partir dela, sem comparar arquivo a arquivo, teria **revertido** a correcao do
Modulo 3 e criado branch concorrente no Modulo 4. O confronto por arquivo e a
leitura dos PRs abertos e o que evitou isso.

Corolario, com o preco medido: **todo numero deste indice precisa vir de
`git grep`/`git show` contra a `main`, nunca de leitura da arvore local.** Quatro
linhas daqui estavam erradas por nao ter sido conferidas assim — o kill-switch
inexistente, o streaming dado como ausente, o guardrail "validado" e forjavel ao
mesmo tempo, e as rotas de job dadas como operacionais. A review do PR #1906
achou as quatro.
