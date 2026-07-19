# Guia de curadoria do gold set — De Paula Teixeira Advogados

O **gold set** é a régua que transforma percepção em medição objetiva. Somente o
escritório pode produzir o conjunto real, sempre pseudonimizado e com fontes
jurídicas conferidas.

## O que produzir

| Arquivo | Avalia |
|---|---|
| `gold_set.jsonl` | recuperação RAG e respostas |
| `gold_set_pecas.jsonl` | geração e revisão de peças |

Cada linha é um JSON completo. Meta progressiva: 50–150 casos por conjunto,
proporcionais ao volume real das áreas.

## Comece pequeno

1. Escolha duas ou três áreas de maior volume.
2. Escreva de cinco a sete perguntas jurídicas reais por área.
3. Preencha 15–20 casos para o primeiro baseline.
4. Amplie uma área por vez.

## Campos essenciais do RAG

- `id`: identificador único e estável;
- `area`: área jurídica;
- `query`: pergunta pseudonimizada;
- `expected_titulos`: documentos que deveriam ser recuperados;
- `expected_citacoes`: referências reais conferidas em fonte oficial.

## Campos essenciais de peças

- `fatos`: narrativa pseudonimizada;
- `tipo_peca_esperado`;
- `teses_esperadas`;
- `jurisprudencia_esperada`: apenas referências reais;
- `criterios`: critérios objetivos de aceitação;
- `ficticio`: `false` nos casos reais pseudonimizados.

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

## Validar formato

```bash
python -m app.eval.run_eval --smoke
```

## Medir

```bash
# Retrieval
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6

# Resposta completa
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --full --judge

# Comparação controlada de provedores
python -m app.eval.compare_providers \
  --gold app/eval/gold_set.jsonl \
  --providers anthropic,maritaca \
  --k 6 --judge --out comparacao.json

# Baseline
python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --out baseline.json
```

Fallbacks ficam fora das métricas principais do provedor solicitado.

## Armazenamento

O gold set real contém experiência interna do escritório. Mantenha-o no ambiente
controlado, mesmo pseudonimizado. Templates e exemplos versionados são somente
scaffolds e não devem ser usados como fonte jurídica.

## Fluxo recomendado

1. estabeleça o baseline;
2. compare provedores;
3. altere uma variável por vez;
4. meça FTS, reranker, embedding e HyDE separadamente;
5. aumente continuamente o conjunto curado.
