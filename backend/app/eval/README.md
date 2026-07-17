# Avaliação do RAG / IA jurídica (harness O-4)

Ciclo **eval-driven**: meça o baseline **antes** de mudar qualquer coisa
(reranker, embedding, prompt, threshold), depois itere medindo cada passo.
Sem régua, toda melhoria é aposta.

## 1. Monte o gold set

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
```

## 3. Métricas

| Métrica | O que mede | De onde vem |
|---|---|---|
| `hit@k`, `precision@k`, `recall@k`, `MRR` | o retrieval trouxe as fontes certas? | `buscar_contexto_rag` vs `expected_titulos` |
| taxa de citações não confirmadas | alucinação de jurisprudência | gate `citation_check` (`--full`) |
| groundedness | a resposta se apoia no contexto? | LLM-as-judge Haiku (`--judge`) |

Métricas de baseline **imediato** que já existem sem gold set: a taxa de citações
não confirmadas (AILog) e a **nota de robustez** das Duas IAs.

## 4. Iteração recomendada (roteiro da auditoria)

1. **Baseline** com o pipeline atual.
2. **Reranker** (O-1, já implementado) → ligue `RAG_RERANK_ENABLED` e compare.
3. **BM25/FTS** (A-3) → migration 095 + `RAG_FTS_ENABLED=true` → compare.
4. **Embedding** (O-2) → migration 096 + reindex + compare recall.
5. **HyDE** (O-6) → `RAG_HYDE_ENABLED=true` → compare recall.
6. **FIRAC / extended thinking** (O-3) → compare groundedness/alucinação.

Uma variável por vez, sempre medindo.

## 5. CI (regressão)

Adicione ao pipeline um job que roda o gold set e barra queda:

```bash
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --min-recall 0.7
```

> Ferramentas externas complementares: **RAGAS** / **DeepEval** (faithfulness,
> context precision/recall), **promptfoo** (comparar prompts/modelos), e os
> benchmarks PT-BR **OAB-Bench** / **Magis-Bench** / **LegalBench-BR** para
> calibrar o teto de qualidade.
