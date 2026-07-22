# Guia de curadoria do gold set

O gold set é a régua de qualidade do EJC. Casos reais devem ser pseudonimizados
e toda fonte jurídica deve ser conferida.

> **Já existe um gold set de RETRIEVAL pronto e versionado**:
> `gold_set_retrieval_juridico.jsonl` (19 itens sobre fontes REAIS já semeáveis —
> 16 súmulas do `SUMULAS_SEED` + 3 diplomas do `planalto.CATALOGO`). Use-o como
> MODELO de formato e como régua imediata (Hit@k/MRR com piso de regressão —
> ver README seção 8). Ele avalia SÓ retrieval; o gold set completo desta guia
> (com resposta/citações/groundedness) continua sendo o alvo de curadoria.

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
- [ ] nenhum placeholder fictício aparece em caso real;
- [ ] no gold set de retrieval, a "resposta esperada" é o ALVO DE RETRIEVAL
      (quais docs/chaves/categorias devem ser recuperados) — nunca uma ementa
      ou opinião jurídica inventada;
- [ ] só entram referências que EXISTEM na base semeada (`SUMULAS_SEED` /
      `planalto.CATALOGO`); na dúvida, o item fica de fora.

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
