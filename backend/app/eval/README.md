# Avaliação do RAG / IA jurídica (harness O-4)

Ciclo **eval-driven**: meça o baseline **antes** de mudar qualquer coisa
(reranker, embedding, prompt, threshold), depois itere medindo cada passo.
Sem régua, toda melhoria é aposta.

> Três gold sets, mesma filosofia:
> - **RAG** (`run_eval.py`, este documento): mede o *retrieval* e a resposta.
> - **Trajetória do agente** (`agent_trajectory.py`): mede as decisões do loop.
> - **Peças** (`gold_set_pecas.jsonl`): avalia o pipeline de peças.

## 1. Monte o gold set

> **Curadoria passo a passo:**
> [`GUIA_CURADORIA_GOLD_SET.md`](GUIA_CURADORIA_GOLD_SET.md),
> [`gold_set.template.json`](gold_set.template.json) e
> [`gold_set_pecas.template.json`](gold_set_pecas.template.json).

Copie `gold_set.example.jsonl` para `gold_set.jsonl` e cresça para **50–150 casos
reais** pseudonimizados, cobrindo as áreas de atuação.

## 2. Rode

```bash
# Só retrieval
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6

# Completo: IA + citações + groundedness
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --full --judge

# Baseline
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --out baseline.json

# Comparação entre provedores sobre a mesma query e o mesmo contexto RAG
python -m app.eval.compare_providers \
  --gold app/eval/gold_set.jsonl \
  --providers anthropic,maritaca \
  --k 6 --judge --out comparacao.json
```

O comparador é aditivo e não modifica o `run_eval.py`. Quando o gateway responde
por fallback, a execução é registrada separadamente e **não entra nas métricas
principais do provedor solicitado**.

## 3. Métricas

| Métrica | O que mede |
|---|---|
| `hit@k`, `precision@k`, `recall@k`, `MRR` | qualidade do retrieval |
| citações não confirmadas | possível alucinação jurídica |
| groundedness | apoio da resposta no contexto |
| custo e latência | eficiência do provider |

## 4. Iteração recomendada

1. Baseline com o pipeline atual.
2. Reranker: ligue e compare.
3. BM25/FTS: mantenha `RAG_FTS_ENABLED=false` até existir baseline real.
4. Embedding: reindexe e compare recall.
5. HyDE: compare recall e precisão.
6. FIRAC/extended thinking: compare groundedness e alucinação.

## 5. CI

```bash
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --min-recall 0.7
python -m app.eval.run_eval --smoke
python -m app.eval.agent_trajectory --min-tool 1.0 --max-violacoes-hitl 0
```

O gate de qualidade deve se tornar bloqueante quando o escritório concluir o
primeiro gold set real e estabelecer o baseline.
