# Avaliação do RAG / IA jurídica (harness O-4)

Ciclo **eval-driven**: meça o baseline **antes** de mudar qualquer coisa
(reranker, embedding, prompt, threshold), depois itere medindo cada passo.
Sem régua, toda melhoria é aposta.

> Três gold sets, mesma filosofia:
> - **RAG** (`run_eval.py`, este documento): mede o *retrieval* e a resposta.
> - **Trajetória do agente** (`agent_trajectory.py`, seção 6): mede as *decisões*
>   do loop de tool-use (qual tool chamou, se fundamentou, se respeitou HITL/leitura
>   e o orçamento). É OFFLINE — o LLM é mockado, sem rede/banco/Redis.
> - **Peças** (`gold_set_pecas.jsonl`, seção 7): casos curados para avaliar o
>   pipeline de geração de peças (incl. o laço de auto-crítica das Duas IAs).

## 1. Monte o gold set

Consulte também [`GUIA_CURADORIA_GOLD_SET.md`](GUIA_CURADORIA_GOLD_SET.md) e
[`gold_set.template.json`](gold_set.template.json).

Copie `gold_set.example.jsonl` para `gold_set.jsonl` e cresça para **50–150 casos
reais** (pseudonimizados), cobrindo as áreas de atuação. Cada linha é um JSON:

```json
{"id": "trab-001", "area": "trabalhista",
 "query": "prazo prescricional para verbas rescisórias",
 "expected_titulos": ["CLT art. 11", "Súmula 308 TST"],
 "expected_categorias": ["legislacao", "sumula"],
 "expected_citacoes": ["Súmula 308 do TST"],
 "notes": "referência humana"}
```

O gold set é o ativo mais valioso do processo — só o escritório o produz.

## 2. Rode

Dentro do backend, com `DATABASE_URL` no banco a avaliar:

```bash
# Só retrieval (rápido, determinístico) — mede hit@k / precision / recall / MRR
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6

# Completo — roda a IA e mede alucinação de citação + groundedness (LLM-judge)
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --full --judge

# Baseline para diff entre execuções
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --out baseline.json

# Comparação controlada de providers sobre a MESMA query e o MESMO contexto RAG
python -m app.eval.compare_providers \
  --gold app/eval/gold_set.jsonl \
  --providers anthropic,maritaca \
  --k 6 --judge --out comparacao.json
```

No comparador, fallbacks são registrados separadamente e **não entram nas
métricas do provider solicitado**. O comando não habilita providers nem altera o
roteamento de produção.

## 3. Métricas

| Métrica | O que mede | De onde vem |
|---|---|---|
| `hit@k`, `precision@k`, `recall@k`, `MRR` | o retrieval trouxe as fontes certas? | `buscar_contexto_rag` vs `expected_titulos` |
| taxa de citações não confirmadas | alucinação de jurisprudência | gate `citation_check` (`--full`) |
| groundedness | a resposta se apoia no contexto? | LLM-as-judge Haiku (`--judge`) |
| custo e latência por provider | eficiência comparativa | `compare_providers.py` |

Métricas de baseline **imediato** que já existem sem gold set: a taxa de citações
não confirmadas (AILog) e a **nota de robustez** das Duas IAs.

## 4. Iteração recomendada (roteiro da auditoria)

1. **Baseline** com o pipeline atual.
2. **Reranker** (O-1, já implementado) → ligue `RAG_RERANK_ENABLED` e compare.
3. **BM25/FTS** (A-3) → mantenha `RAG_FTS_ENABLED=false` até existir baseline
   jurídico real; depois ative de forma controlada e compare.
4. **Embedding** (O-2) → migration 096 + reindex + compare recall.
5. **HyDE** (O-6) → `RAG_HYDE_ENABLED=true` → compare recall.
6. **FIRAC / extended thinking** (O-3) → compare groundedness/alucinação.

Uma variável por vez, sempre medindo.

## 5. CI (regressão)

Dois níveis, já embarcados:

- **Genérico (quando o gold set real existir)** — adicione um job que roda o
  gold set curado pelo escritório e barra queda:

  ```bash
  python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --min-recall 0.7
  ```

- **Jurídico versionado (JÁ pronto, sem esperar curadoria)** — o gold set
  `gold_set_retrieval_juridico.jsonl` (seção 8) roda contra fontes REAIS já
  semeáveis e tem piso de regressão em teste automatizado
  (`tests/test_rag_avaliacao_precisao_dblevel.py`, `RUN_DB_TESTS=1`). Manual:

  ```bash
  python -m app.eval.retrieval_juridico_eval --k 5 --min-hit 0.30 --min-mrr 0.12
  ```

> Ferramentas externas complementares: **RAGAS** / **DeepEval** (faithfulness,
> context precision/recall), **promptfoo** (comparar prompts/modelos), e os
> benchmarks PT-BR **OAB-Bench** / **Magis-Bench** / **LegalBench-BR** para
> calibrar o teto de qualidade.

## 6. Eval de TRAJETÓRIA do agente (loop de tool-use)

O módulo agêntico (`app/services/ai/agent/loop.py`) **decide → chama ferramenta →
lê o resultado → decide de novo**. O que importa não é só a resposta final, mas a
**trajetória**. Este harness roda o agente REAL com o **LLM mockado** (roteiro de
tool-use por cenário — sem rede, LLM, banco ou Redis) e mede 4 coisas:

| Métrica | O que mede | De onde vem |
|---|---|---|
| escolha de ferramenta | chamou a tool certa para a intenção? | `passos[].ferramentas` vs `ferramenta_esperada` |
| fundamentação/fonte | a resposta que afirma tese cita fonte? | detector local `_tem_fonte` (o gate real de citações roda no loop) |
| HITL / modo leitura | write-tool pausa (não executa sem aprovação); em `apenas_leitura` é bloqueada | `status`/`REGISTRY.executar`/evento `ferramenta_bloqueada` |
| orçamento | respeita `max_steps`/tokens/custo; encerra no teto com aviso | `passos` vs `max_steps` + alertas |

Como o LLM é mockado (espelha o `loop_env` de `tests/test_agente_ia.py`): cada
cenário do gold set traz `turnos`, o roteiro de respostas de tool-use que
substitui `ai_gateway.chat_agentico`; as demais bordas do loop (ownership,
entidades, AILog, gate de citações, store HITL, `REGISTRY.executar`) são fakes em
memória. O loop `rodar_agente` é exercitado ponta a ponta.

```bash
# Roda o gold set embarcado (offline — NÃO precisa de DATABASE_URL)
python -m app.eval.agent_trajectory

# Gate de regressão para CI
python -m app.eval.agent_trajectory --min-tool 1.0 --max-violacoes-hitl 0

# Baseline para diff
python -m app.eval.agent_trajectory --out traj.json
```

Gold set: `agent_scenarios.jsonl` (uma linha = um cenário FICTÍCIO, sem PII).
Campos: `intencao`, `mensagem`, `ferramenta_esperada`, `espera_fonte`,
`hitl` (`nenhum|pausa|escrita_aprovada|bloqueia_leitura`), `orcamento` (`ok|estoura`),
`apenas_leitura`, `aprovar_escrita`, `orcamento_override`, `tool_result`, `turnos`.
Cresça-o cobrindo as intenções reais do escritório. Teste offline determinístico:
`tests/test_eval_agent_trajectory.py`.

## 7. Gold set de PEÇAS (pipeline de geração + auto-crítica)

Scaffold pronto para o escritório preencher:

- **Template comentado**: `gold_set_pecas.template.json` — todos os campos de um
  caso (`id`, `area`, `ficticio`, `fatos`, `pedidos`, `tipo_peca_esperado`,
  `teses_esperadas`, `jurisprudencia_esperada`, `criterios`, `notes`).
- **Exemplos FICTÍCIOS**: `gold_set_pecas.example.jsonl` — 3 casos 100% sintéticos
  (`ficticio: true`), com jurisprudência **placeholder** (`SUMULA-FICTICIA-XXX`).
  Servem só para demonstrar o formato — **nunca** copie os placeholders.

### Curadoria

1. Copie o formato dos exemplos para `gold_set_pecas.jsonl`.
2. Pseudonimize nomes, documentos, endereços e valores identificáveis.
3. Liste apenas jurisprudência real conferida na fonte oficial.
4. Cresça para 50–150 casos pseudonimizados.
5. Marque `ficticio: false` nos casos reais.

### Como rodar

```bash
python -m app.eval.run_eval --smoke
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6
```

O CI (`.github/workflows/ci.yml`, job `eval-smoke`) roda `--smoke` +
`agent_trajectory` em modo não bloqueante; torna-se gate bloqueante quando o gold
set real existir e o baseline estiver estabelecido.

## 8. Gold set jurídico de RETRIEVAL (versionado, pronto para CI)

Enquanto o gold set das seções 1–2 (50–150 casos reais pseudonimizados) é
curado pelo escritório, este pacote embarca um gold set **versionado e já
utilizável** focado só em RETRIEVAL:

- **Arquivo**: `gold_set_retrieval_juridico.jsonl` (19 itens).
- **Harness**: `retrieval_juridico_eval.py` — reusa o loader/normalização do
  `run_eval` e a semeadura determinística de `ingerir_sumulas_seed`.
- **Métricas**: Hit@k e MRR sobre os itens **pontuados**.

### Anti-invenção: só ALVO de retrieval, nada de opinião

Cada item é `{consulta, chave/título/categoria esperados no retrieval}` — a
"resposta esperada" é **qual documento deve ser recuperado**, jamais uma tese
inventada. Toda referência é REAL e sua proveniência está no próprio item
(campo `proveniencia`):

| Fonte (`fonte_seed`) | Itens | Proveniência | Alvo casado por |
|---|---|---|---|
| `sumulas_seed` | 16 súmulas STJ/TST/STF, todas `situacao=ativa` | `SUMULAS_SEED` (`app/services/sumulas_ingestion.py`), verbetes reconferidos em 2026-07-18 contra STJ/TST/STF | título exato `Súmula … nº N` + `chave_origem` `sumula:<trib>:<n>` |
| `planalto_catalogo` | 3 diplomas (CDC, CLT, CC) | `planalto.CATALOGO` (`app/services/ingestors/planalto.py`), slug/URL oficiais | título do diploma + `chave_origem` `planalto:<slug>` |

Os alvos (título/chave/categoria) são **derivados das constantes de seed** —
não digitados à mão — então nunca divergem do que os seeders gravam. O teste
offline `tests/test_gold_set_retrieval_juridico.py` (roda no CI normal, sem
banco) revalida essa consistência e **falha** se alguém marcar uma súmula como
superada/cancelada ou renomear um título sob o gold set.

### Gate de presença (por que a lei "some" no CI)

Súmulas são semeadas offline/determinístico; a lei seca do planalto é ingerida
por download de `planalto.gov.br` (bloqueado no CI/dev). Itens cujo alvo **não
está semeado e vigente** viram **SKIP** — nunca MISS —, para o piso medir
qualidade de retrieval, não seed faltando. Contra um banco de produção (planalto
semeado) os 3 itens de lei também pontuam.

### Como rodar

```bash
# Requer Postgres+pgvector com migrations aplicadas.
export RUN_DB_TESTS=1                      # habilita os testes db-level
export DATABASE_URL=postgresql+asyncpg://... # banco a avaliar

# CLI (semeie as súmulas antes, se o banco estiver vazio):
python -m app.eval.retrieval_juridico_eval --k 5
python -m app.eval.retrieval_juridico_eval --k 5 --min-hit 0.30 --min-mrr 0.12  # gate
python -m app.eval.retrieval_juridico_eval --incluir-ausentes                   # não pula lei
python -m app.eval.retrieval_juridico_eval --out baseline.json                  # p/ diff

# Na VPS, dentro do container (súmulas já semeadas no boot):
docker exec -it ejc_backend python -m app.eval.retrieval_juridico_eval --k 5

# Regressão automatizada (semeia súmulas e afere o piso sozinho):
RUN_DB_TESTS=1 pytest tests/test_rag_avaliacao_precisao_dblevel.py -q
```

Sem `RUN_DB_TESTS`/Postgres os testes db-level **pulam** (skip), por design; o
teste de integridade offline e o `--smoke` continuam rodando.

### Como interpretar / piso de regressão

- **Hit@5** — fração de consultas em que o documento certo aparece no top-5.
- **MRR** — média de 1/posição do alvo (penaliza rank pior mesmo acertando).
- **Piso**: `Hit@5 ≥ 30%` e `MRR ≥ 0.12` — o MESMO piso conservador já validado
  para o gabarito de súmulas (baseline textual observado ≈ 47,6% / 0,202 com
  embeddings desligados). Fica ABAIXO do baseline de propósito: o objetivo é
  pegar QUEDA REAL de qualidade (novo filtro/chunker/query/modelo), não flutuação
  de rank por 1–2 posições. Suba o piso conforme o baseline subir (embeddings
  ligados, reranker, FTS).
