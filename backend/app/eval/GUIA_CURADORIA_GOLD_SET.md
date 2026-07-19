# Guia de curadoria do gold set

O gold set é a régua de qualidade do EJC. Casos reais devem ser pseudonimizados
e toda fonte jurídica deve ser conferida.

## Comece pequeno

1. Escolha duas ou três áreas de maior volume.
2. Escreva cinco a sete perguntas reais por área.
3. Monte 15–20 casos para o primeiro baseline.
4. Amplie progressivamente até 50–150 casos.

## Checklist LGPD

- [ ] nomes substituídos por marcadores;
- [ ] CPF, CNPJ e RG removidos;
- [ ] número de processo removido quando identificar o caso;
- [ ] endereço, e-mail e telefone removidos;
- [ ] valores identificáveis arredondados ou marcados.

## Checklist antialucinação

- [ ] toda referência foi conferida em fonte oficial;
- [ ] referências duvidosas foram excluídas;
- [ ] nenhum placeholder fictício aparece em caso real.

## Comandos

```bash
python -m app.eval.run_eval --smoke
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6
python -m app.eval.compare_providers \
  --gold app/eval/gold_set.jsonl \
  --providers anthropic,maritaca \
  --k 6 --judge --out comparacao.json
```

Fallbacks são excluídos das métricas principais do provider solicitado.
FTS, reranker, embedding e HyDE devem ser alterados e medidos uma variável por vez.
