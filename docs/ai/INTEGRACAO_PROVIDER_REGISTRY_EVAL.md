# Provider Registry e avaliação comparativa

Esta entrega reaplica as partes válidas do antigo PR #317 sobre a `main` após o
hardening do PR #322.

## Decisões

- O `ProviderRegistry` é a fonte única de provedores suportados, externos e
  elegíveis.
- O adapter de runtime conecta gateway, policy, adversarial e skills sem remover
  o resolver fail-closed.
- O comparador vive em `app.eval.compare_providers`, de forma aditiva.
- Fallbacks são registrados, mas excluídos das métricas do provider solicitado.
- `RAG_FTS_ENABLED` permanece no default atual, desligado, até existir gold set
  jurídico real e baseline mensurado.

## Execução

```bash
python -m app.eval.compare_providers \
  --gold app/eval/gold_set.jsonl \
  --providers anthropic,maritaca \
  --k 6 --judge --out comparacao.json
```

## Gate

Não integrar sem CI verde, smoke dos gold sets e trajetória do agente.
