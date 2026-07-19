# Avaliação do RAG / IA jurídica

Meça o baseline antes de alterar reranker, embedding, prompt, FTS ou threshold.

## Gold set

Consulte `GUIA_CURADORIA_GOLD_SET.md` e `gold_set.template.json`. Casos reais
devem ser pseudonimizados e usar somente fontes jurídicas conferidas.

## Comandos

```bash
# Retrieval
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6

# Resposta completa
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --full --judge

# Comparação de providers, sem alterar o roteamento de produção
python -m app.eval.compare_providers \
  --gold app/eval/gold_set.jsonl \
  --providers anthropic,maritaca \
  --k 6 --judge --out comparacao.json

# Smoke e trajetória
python -m app.eval.run_eval --smoke
python -m app.eval.agent_trajectory --min-tool 1.0 --max-violacoes-hitl 0
```

Fallbacks são registrados, mas excluídos das métricas principais do provider
solicitado. `RAG_FTS_ENABLED` deve permanecer desligado até existir baseline
jurídico real; ative uma variável por vez e compare precisão, recall, MRR,
groundedness, citações, custo e latência.
