# Avaliação do RAG / IA jurídica (harness O-4)

Ciclo **eval-driven**: meça o baseline **antes** de mudar qualquer coisa
(reranker, embedding, prompt, threshold), depois itere medindo cada passo.
Sem régua, toda melhoria é aposta.

> Três gold sets, mesma filosofia:
> - **RAG** (`run_eval.py`, este documento): mede o *retrieval* e a resposta.
> - **Trajetória do agente** (`agent_trajectory.py`, seção 6): mede as *decisões*
>   do loop de tool-use. É OFFLINE — o LLM é mockado, sem rede/banco/Redis.
> - **Peças** (`gold_set_pecas.jsonl`, seção 7): casos curados para avaliar o
>   pipeline de geração de peças.

## 1. Monte o gold set

> **Curadoria passo a passo:**
> [`GUIA_CURADORIA_GOLD_SET.md`](GUIA_CURADORIA_GOLD_SET.md),
> [`gold_set.template.json`](gold_set.template.json) e
> [`gold_set_pecas.template.json`](gold_set_pecas.template.json).

Copie `gold_set.example.jsonl` para `gold_set.jsonl` e cresça para **50–150 casos
reais** pseudonimizados, cobrindo as áreas de atuação. Cada linha é um JSON:

```json
{"id": "trab-001", "area": "trabalhista",
 "query": "prazo prescricional para verbas rescisórias",
 "expected_titulos": ["CLT art. 11", "Súmula 308 TST"],
 "expected_categorias": ["legislacao", "sumula_tst"],
 "expected_citacoes": ["Súmula 308 do TST"],
 "notes": "referência humana"}
```

## 2. Rode

```bash
# Só retrieval
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6

# Completo: IA + citações + groundedness
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --full --judge

# Baseline
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --out baseline.json

# Comparação entre provedores sobre a mesma query e o mesmo contexto RAG
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 \
    --full --judge --providers anthropic,maritaca --out comparacao.json
```

No modo `--providers`, cada provedor recebe o mesmo contexto. Quando o gateway
responde por fallback, a execução é registrada separadamente e **não entra nas
métricas principais do provedor solicitado**. Isso evita atribuir ao Sabiá uma
resposta efetivamente produzida pelo Groq, por exemplo.

## 3. Métricas

| Métrica | O que mede | De onde vem |
|---|---|---|
| `hit@k`, `precision@k`, `recall@k`, `MRR` | o retrieval trouxe as fontes certas? | `buscar_contexto_rag` vs `expected_titulos` |
| taxa de citações não confirmadas | alucinação de jurisprudência | `citation_check` |
| groundedness | a resposta se apoia no contexto? | LLM-as-judge |
| comparação por provedor | qualidade, custo e latência | `--providers` |

## 4. Iteração recomendada

1. **Baseline** com o pipeline atual.
2. **Reranker** → ligue e compare.
3. **BM25/FTS** → mantenha `RAG_FTS_ENABLED=false` até existir baseline real;
   ative de forma controlada e compare.
4. **Embedding** → reindexe e compare recall.
5. **HyDE** → compare recall e precisão.
6. **FIRAC / extended thinking** → compare groundedness e alucinação.

Uma variável por vez, sempre medindo.

## 5. CI

```bash
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --min-recall 0.7
```

## 6. Eval de trajetória do agente

O harness `agent_trajectory.py` mede escolha de ferramenta, fundamentação,
respeito ao HITL e orçamento, sem rede, LLM, banco ou Redis.

```bash
python -m app.eval.agent_trajectory
python -m app.eval.agent_trajectory --min-tool 1.0 --max-violacoes-hitl 0
python -m app.eval.agent_trajectory --out traj.json
```

Gold set: `agent_scenarios.jsonl`.

## 7. Gold set de peças

- Template: `gold_set_pecas.template.json`.
- Exemplos fictícios: `gold_set_pecas.example.jsonl`.
- Casos reais devem ser pseudonimizados e usar somente jurisprudência conferida.

```bash
python -m app.eval.run_eval --smoke
```

O CI executa smoke e trajetória. O gate de qualidade deve se tornar bloqueante
quando o escritório concluir o primeiro gold set real e estabelecer o baseline.
