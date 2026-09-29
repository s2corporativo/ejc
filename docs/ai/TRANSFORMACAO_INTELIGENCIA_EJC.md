# TRANSFORMAO DE INTELIGENCIA DO EJC — indice unico de progresso

> Documento indice do programa de evolucao do nucleo de IA juridica do EJC
> (17 modulos, referencias do pedido do titular). **Este arquivo nao e um
> relatorio**: ele aponta, por modulo, para o PR, o estado e a evidencia.
> Relatorio completo vive no corpo do PR; aqui basta uma linha por item.
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
| `main` no GitHub ao iniciar este ciclo | `d1553f1252bd1c25cf76377b7b28da4193f75d54` (2026-09-29) |
| Ambiente de execucao local | `C:\Users\User\.agent-browser` — **sem diretorio `.git`** (ver bloqueios) · Python 3.14.7 · Windows 11 |
| `main` verificada na publicacao | `144d703` (2026-09-29, `fix(frontend): alinhar cadastro manual ao gate de proxima acao (#1896)`) |
| Data de inicio do ciclo | 2026-09-29 |

### Bloqueios de ambiente (nao bloqueiam correcao local)

1. **Sem repositorio git local.** A pasta de trabalho nao tem `.git`, portanto
   branch/commit/PR nao podiam ser feitos daqui. Todo o trabalho foi aplicado
   direto na arvore de trabalho.
   **RESOLVIDO EM 2026-09-29 para fins de publicacao**: `gh` esta autenticado
   como `s2corporativo` e a `main` foi clonada em `.publish/ejc` (ver §5). A
   arvore de trabalho continua sem git e **nao deve mais ser tratada como fonte
   de verdade** — a `main` e o PR #1903 sao.
2. **Coleta da suite completa interrompida no Windows**: 13 arquivos de teste
   nao importam (`fcntl` ausente — `app/services/backup_lock.py`;
   `googleapiclient` ausente). Erro ambiental, pre-existente, alheio a IA.
   Afeta backup/health/readiness; nao afeta a area de IA.
3. Sem `.github/workflows` neste checkout: verificacao e a suite local
   (`scripts/ci-local.sh`).

## 1. Baseline revalidado no ambiente (Modulo 0)

Medido por leitura de codigo e coleta de testes, na arvore de trabalho local
(hash local nao verificavel contra o GitHub — ver bloqueio 1).

| Medida | Baseline declarado (7034f2b) | Revalidado local | Como foi medido |
|---|---|---|---|
| Testes focados de IA aprovados | 207 | 46 arquivos de teste / ~207 testes na area IA (coletados; suite completa bloqueada por `fcntl`) | `pytest tests/ -k "ia or ai_ or citac or guard or provider or rag or embed or pertin or rerank"` |
| Casos no gold set | 10 candidatos, 0 atestados | 10, todos `status: candidato`, `atestado_por` vazio em 10/10 | `app/eval/gold_set_ia_candidatos.jsonl` |
| Cenarios sinteticos do benchmark | 10 cenarios, 17 questoes esperadas | 10 cenarios, 17 questoes esperadas | `app/eval/benchmarks/legal_bench.synthetic.jsonl` |
| Resposta vazia na nota agregada | 64% | reproduzido pela frente do Modulo 3 (ver PR) | `app/eval/legal_bench.py` |
| Modulos/routers de IA | — | 13 arquivos de router `ia_*`/`ai_*` + 6 servicios de gateway/guard | `backend/app/routers/` |
| Saidas para provider fora do gateway | 0 (esperado) | 0 — `AsyncAnthropic`/`AsyncOpenAI` so em `ai_gateway.py` e `providers/anthropic_provider.py` | grep |
| Rotas de governanca sem guard | — | 0 — as 13 rotas de `ia_governanca.py` usam o guard `_req_admin_socio` | leitura |
| Kill-switch | leido em 1 ponto (`dispatcher.py`) | 1 ponto, **por desenho**: `AI_CLAUDE_KILL_SWITCH` cobre so a camada Claude Complex; o gateway legado tem `AI_ENABLED`/`AI_AGENT_ENABLED` proprios | `config.py:412-435` |
| Streaming de IA | inexistente | inexistente (`stream: False` em todo o sistema) | leitura |

**Nao medido / nao verificavel aqui:** corpus RAG em producao (exige VPS),
conectividade a DataJud, custos reais, numero de casos juridicos reais
(zero por definicao — gold set so tem candidatos).

### Matriz de inventario (Modulo 0): capacidade → implementacao → estado

| Capacidade | Servico real | Controles | Testes | Estado |
|---|---|---|---|---|
| Chamada a provider (fonte unica) | `ai_gateway.chat` / `executar_tarefa_ia` | `_chamar_com_barreira` (PII), provider_policy, model_router, cache, custo | `test_ai_gateway_barreira`, `test_ai_routing_policy`, `test_provider_explicito_fail_closed` (PR #1869) | **existente e validado** (barreira), em evolucao neste ciclo |
| Log de auditoria de IA | `ai_guard.registrar_ai_log` + `AILog` | pseudonimizador no model (resposta, critica, prompt) | `test_ailog_pseudonimiza_resposta_reidratada`, `test_ai_log_prompt_composto_sem_pii` (novo) | **existente e validado** apos Modulo 1 |
| Recuperacao RAG com escopo | `ai_service.buscar_contexto_rag` | `_FILTRO_ESCOPO_RAG` fail-closed, escopo cliente/caso | `test_ai_idor_case_id_gates` | **existente e validado** |
| Rerank + governanca de fonte | `ai/reranker.py` | `_hidratar_governanca` (fail-closed p/ normativos) | `test_ia_governanca_gates` | **existente e validado** (a penalidade de governanca em duas escalas — achado A4 da auditoria) |
| Pertinencia de citacao | `ai/pertinencia.py` | `trecho_confere` literal, canonicalizacao `NAO_SUSTENTADA` | `test_pertinencia_citacoes` | **existente e validado** |
| Gate de citacoes (HITL) | `citation_gate.py` | aplicado so na aprovacao HITL, nao na entrega | `test_citation_gate`, `test_citation_gate_hardening` | **existente parcialmente** (achado A3) |
| Guardrails juridicos | `ai/juridico_guardrails.py` | marcadores forjaveis pelo texto de entrada | `test_ai_skill_guardrail_decadencia`, `test_ai_skill_oab_gate` | **existente e validado** |
| Deteccao de questoes | `legal_brain/issue_engine.py` | — | `test_legal_brain_issue_engine_deteccao` (Modulo 4) | **em correcao** (defeito B) |
| Avaliacao (regua) | `eval/legal_bench.py` | versao 2.0.0 apos Modulo 3 | `test_legal_bench_regua` (Modulo 3) | **em correcao** (defeito C) |
| Gold set juridico | `eval/gold_set_ia_candidatos.jsonl` | — | `test_gold_ia_regua` | **candidato, 0 atestados** — nao homologado |
| Loop de agente | `ai/agent/loop.py` | budget (passos/tokens/custo), sem timeout | `test_ia_nucleo_onda1` | **existente parcialmente** (sem timeout; achado A8) |
| Fila de jobs | `ai/jobs/` | kill-switch, Celery opcional, thread pool inline | `test_ia_jobs_rotas_operantes` (novo, 8) | **rotas operantes** desde o ciclo 2026-09-29 (§4); loop/kill-switch em aberto |
| Skills por area | `seeds/skills_*.py` + `ai_skill_service` | sigilo, delimitadores, guardrails | `test_ai_skill_*` | **parcial** — 11 lacunas nativas (Modulo 15) |
| Manus como planejador | — | — | — | **nao implementado** (Modulo 9) |
| Estado persistente de caso→tese→peça→decisao | parcial (`matriz_teses_service`, `jurisprudencia_interna`) | — | — | **parcial** (Modulo 14) |
| Radar / memoria juridica | — | — | — | **nao implementado** (Modulo 14) |
| Ferramentas autorizadas (Tool Broker) | `ai/agent/` tools | — | — | **parcial** (Modulo 8) |
| Simulacao decisoria | `ai/adversarial.py` | nunca bloqueia (por desenho) | `test_ai_prompt_injection_delimitadores` | **existente parcialmente** (Modulo 13) |

## 2. Estado por modulo

| Modulo | Estado | PR | Evidencia / nota |
|---|---|---|---|
| 0 — Inventario e baseline | TESTADO LOCALMENTE | — | §1 deste indice |
| 1 — P0 logging e protecao de dados | **TESTADO LOCALMENTE** | pendente (bloqueio 1) | correcao aplicada + 6 testes; ver §3 |
| 2 — Upload e ingestao segura | EM IMPLEMENTACAO | — | (frente de auditoria) achados em aberto |
| 3 — Regua de avaliacao | **JA CORRIGIDO NA MAIN** | — | `5bd6ac7` ja entregou a correcao do defeito C; medido na `main`: resposta vazia = **0.00**. A reescrita local NAO foi publicada — ver §5 |
| 4 — Deteccao de questoes | EM CORRECAO, **CONCORRENTE** | — | defeito B confirmado aberto na `main`; mas o PR #1866 ja ataca o mesmo arquivo e resolve **parcialmente** (10 dos 26 testes ainda falham nele) |
| 5 — Nucleo unico e provedores | **NAO PUBLICAVEL COMO CORRECAO** | — | a camada `ai/jobs/`, `ia_jobs.py` e `ia_entrada_unica.py` **nao existem na `main` nem em PR aberto** — sao codigo so local. Ver §4 e §5 |
| 6 — RAG, fontes e validade | EM DIAGNOSTICO | — | auditoria concluida (achados 1–12) |
| 7 — Pesquisa iterativa | EM IMPLEMENTACAO | — | — |
| 8 — Estado persistente / Tool Broker | EM IMPLEMENTACAO | — | — |
| 9 — Manus subordinado | EM IMPLEMENTACAO | — | — |
| 10 — Leitura documental | EM IMPLEMENTACAO | — | — |
| 11 — Provas e contradicoes | EM IMPLEMENTACAO | — | — |
| 12 — Teses e estrategia | EM IMPLEMENTACAO | — | — |
| 13 — Adversarial e simulacao | EM IMPLEMENTACAO | — | — |
| 14 — Memoria e radar | EM IMPLEMENTACAO | — | — |
| 15 — Skills e gold set | EM IMPLEMENTACAO | — | — |
| 16 — Benchmark, custos, observabilidade | EM IMPLEMENTACAO | — | — |
| 17 — Shadow / homologacao / rollout | EM IMPLEMENTACAO | — | — |

## 3. Modulo 1 — P0 logging e protecao de dados (detalhe minimo)

**Causa-raiz.** A barreira do gateway produz duas versoes da resposta —
`texto` (reidratado, para o usuario) e `texto_para_log` (pseudonimizado) — mas
`GatewayResponse` so transportava a primeira. Todo `AILog` gravado pelos
call sites (25+) recebia a versao reidratada. O `prompt_sanitizado`, cuja
coluna e declarada "sem PII", nao tinha nenhum validador no model e recebia o
prompt composto cru (dossie + precedentes + RAG), enquanto a sanitizacao do
chamador so cobria `descricao_fatos`.

**Correcao (3 pontos, sem migration).**
1. `GatewayResponse.texto_para_log` — a versao pseudonimizada viaja com a
   resposta; `chat()` popula nos caminhos normal e cache-hit.
2. `chat()` deixa de gravar no cache a resposta reidratada (paridade com
   `executar_tarefa_ia`, que ja restringia o cache a `not pii_removida_log`).
3. `AILog` ganha `@validates("prompt_sanitizado")` com o mesmo
   pseudonimizador de auditoria que `resposta`/`critica_adversarial` ja
   usavam. A garantia passa a viver na barreira, nao na disciplina de cada
   call site.

**Testes.** `tests/test_ai_log_prompt_composto_sem_pii.py` (6): prompt
composto com PII pelo dossie/precedente e pseudonimizado na persistencia;
resposta reidratada pseudonimizada; marcador estrutural preservado;
`GatewayResponse` transporta as duas versoes; `chat()` nao persiste PII real
no cache; `analisar_caso` fim a fim (PII so pelo dossie e pela resposta
reidratada) nao chega ao objeto INSERT, e a rastreabilidade (fonte RAG) e a
UX (usuario ve o nome) permanecem.

**Portao.** `ruff check app` limpo; suite afetada 134 passed (unica falha:
`test_citation_gate.py::test_rota_validar_citacoes_montada`, `fcntl` ausente —
pre-existente do Windows). **Suite completa: ainda nao executada
** neste ambiente (13 arquivos nao importam — bloqueio 2 da §0). Registrado como
lacuna, nao como verde.

**Nao comprovado por esta correcao.** A barreira de **envio** externo
(`_chamar_com_barreira` → `_preparar_mensagens_externo` →
`validar_sem_pii_pseudonimizado`, fail-closed) nao foi alterada: corrigir o log
nao comprova nem substitui a barreira de envio. Auditoria independente
confirmou a barreira de envio como solida (unico ponto de saida, re-sanitizacao
por turno no loop, zero bypass).

**Rollback.** Reverter `ai_gateway.py` (3 blocos) e remover o decorator de
`prompt_sanitizado` em `ai_log.py`. Sem migration, sem estado persistido.
Logs ja gravados com PII real **nao** sao corrigidos por esta mudanca —
remediacao historica fica para decisao do titular (retencao/autorizacao/
backup), nao e parte deste modulo.

## 4. Modulo 5 — frente A: rotas de job inoperantes

Nenhuma rota de `ia/jobs` ou `ia/entrada-unica` respondia. Quatro defeitos,
todos reproduzidos por leitura do codigo real (nao por inferencia) e hoje
cobertos por `tests/test_ia_jobs_rotas_operantes.py` (8 testes).

| # | Defeito | Efeito | Correcao |
|---|---|---|---|
| A1 | `job_para_snapshot` lia `job.requires_review` — atributo que **nao existe** em `AIJob` (`ai_job.py:82-127`; so ha o membro de enum `AIJobStatus.requires_review`) | `AttributeError` em `criar_job`, `obter_job`, `cancelar_job`, `listar_jobs` e no stream | deriva de `job.status == AIJobStatus.requires_review` |
| A2 | `ia_jobs.py` definia um `verificar_acesso_caso` **local** que sombreava `app.core.ownership.verificar_acesso_caso`: nao filtrava `deleted_at` e comparava so `scope_client_id` — sem o vinculo (responsavel/auxiliar/gestao) | qualquer usuario do mesmo cliente abria job sobre **qualquer** caso do escopo | copia local removida; importa-se o gate canonico, assinatura `(db, cu, case_id)` |
| A3 | `User` nao tem `scope_client_id` (coluna real: `client_id`), e `Case` nao tem `scope_client_id` (coluna real: `client_id`) | `AttributeError` em `criar_job` e `entrada_unica` — a rota morria antes de criar o job | escopo derivado de `caso.client_id` (mesma chave de `_escopo_cliente_do_caso`, que isola o RAG); sem caso, `user.client_id`. Nunca o cliente de outro |
| A4 | `criar_ou_obter_job` termina em `flush()`, nao `commit()`; `ia_jobs` e `ia_entrada_unica` despachavam sem commitar | rollback do `get_db` apaga o job; o worker (sessao propria) nao o encontra e o job some sem erro | `await db.commit()` + `db.refresh(job)` antes de despachar, como em `ai_core.py:331-344` |

**Achado adjacente corrigido (manager).** `idempotency_key` tem indice simples,
nao `UniqueConstraint` (`100_ai_job_e_prompt_profile.py:158`), e o caminho de
"refaca porque falhou/cancelou" reinsere **com a mesma chave**. A partir do 2o
retry havia duas linhas e `scalar_one_or_none` levantava `MultipleResultsFound`
(500). Agora resolve pela linha mais recente — a unica que representa o estado
corrente.

**Portao.** `ruff check app` limpo; 8/8 testes novos verdes; `sse-starlette==2.1.0`
(dependencia declarada em `requirements.txt:132`) foi instalada no ambiente, que
nao a tinha. Area de IA com as rotas: 2165 passed / 70 failed — as 70 sao
pre-existentes e ambientais (`fcntl` ausente no Windows, `KeyError: '099'` em
testes de alembic que exigem `.git` — bloqueios 1 e 2 da §0), e nenhum arquivo
que falha importa os tres modulos tocados.

**Rollback.** Reverter `ia_jobs.py`, `ia_entrada_unica.py` e o bloco de
idempotencia em `ai/jobs/manager.py`. Sem migration, sem mudanca de schema.

**Nao comprovado por esta correcao.** A2/A3/A4 tornam as rotas **chegaveis**;
nao provam que o trabalho executado por elas faz o que deveria. Permanecem
abertos no Módulo 5: `rodar_agente` sem leitura do kill-switch e sem timeout
(`ai/agent/loop.py:249,414-421`), `asyncio.run(engine.dispose())` no
`_bridge_sinc` do dispatcher sobre o engine global compartilhado, e a cobertura
do kill-switch, que hoje alcanca so a camada Claude Complex
(`config.py:412-435`) e nao o gateway legado.

## 5. Estado de publicacao e revisao de premissas (2026-09-29)

Antes de publicar, a arvore local foi confrontada com a `main` real
(`144d703`, clonada em `.publish/ejc`) e com os **8 PRs abertos**. O resultado
muda o que era publicavel:

| Modulo | Estado na `main` | Verificacao | Decisao |
|---|---|---|---|
| 1 — P0 logging | **aberto** (confirmado) | o teste novo roda contra a `main` e falha: PII persiste em `prompt_sanitizado`; `GatewayResponse` nao tem `texto_para_log` | **publicado** — PR #1903 |
| 3 — Regua | **ja corrigido** por `5bd6ac7` | `score_structured_answer` com resposta vazia na `main` devolve `total=0.0` (defeito C resolvido) | reescrita local **nao publicada** — substituiria uma regua v2 funcional por uma v2.0.0 de estrutura diferente |
| 4 — Detector | **aberto**, mas com `#1866` em voo | meu teste contra o branch do #1866: 10 falham / 16 passam (ainda falta `prova_onus_lacunas` em varios cenarios e `evidence_snippets`) | **nao publicado** — evitar branch concorrente no mesmo arquivo. Decisao do titular: deixar o #1866 seguir ou substitui-lo |
| 5 — Rotas de job | **inexistente na `main`** | `git log --all` nao acha `ai/jobs/` nem `ia_jobs.py`; nenhum dos 8 PRs abertos os contem | **nao publicado** — o defeito que corrigi era de codigo nunca publicado; landar a correcao implicaria introduzir a subcamada inteira, que e decisao de produto, nao de bug |

**Licao de metodo.** A arvore de trabalho nao tem git e estava dessincronizada
da `main`. Publicar a partir dela, sem comparar arquivo a arquivo, teria
**revertido** a correcao do M3 e criado uma branch concorrente no M4. O confronto
por arquivo e a leitura dos PRs abertos e o que evitou isso — e e obrigatorio
em qualquer proximo ciclo deste programa.

**Identidade usada no commit:** `s2corporativo` via e-mail noreply, configurada
**apenas** no clone de publicacao (`.publish/ejc`); nenhum `git config --global`
foi alterado.
