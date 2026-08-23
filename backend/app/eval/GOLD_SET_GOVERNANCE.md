# Governança do Gold Set Jurídico — P0.2/P0.3

## Regra de verdade

O EJC não considera exemplos sintéticos, fixtures técnicas ou casos gerados por IA como evidência de qualidade jurídica. Só conta como **gold jurídico real** o caso pseudonimizado, efetivamente avaliável, curado por advogado identificado, com fonte oficial, versão da fonte e vigência conferidas. A revisão por segunda identidade é **desejável e opcional** — a exigência de duas identidades distintas foi removida por decisão do titular em 23/08/2026, porque o escritório opera com um único jurista e a regra tornava o gate impossível de satisfazer em vez de elevar a qualidade. Registre `curadoria.revisor` sempre que houver segundo par de olhos.

O estado atual do repositório permanece explicitamente **não certificado** enquanto não existir `gold_set.jsonl`/equivalente humano-curado que passe em `python -m app.eval.gold_governance`.

## Evidência mínima por caso

Cada caso real deve declarar:

- `ficticio: false`;
- `area`;
- `cenario: normal | fronteira | excecao`;
- payload avaliável:
  - RAG: `query` e `expected_titulos` não vazio; ou
  - peças: `fatos`, `tipo_peca_esperado`, `teses_esperadas` e `criterios` não vazios;
- `curadoria.curador`;
- `curadoria.revisor`, opcional — registre quando houver segundo revisor;
- `curadoria.revisado_em` (`YYYY-MM-DD`);
- `curadoria.vigencia_conferida_em` (`YYYY-MM-DD`) não posterior à revisão;
- ao menos uma entrada em `curadoria.fontes_oficiais` com título, URL HTTPS oficial e data de consulta não posterior à revisão;
- para cada fonte, `identificador_versao` ou `hash_sha256`, permitindo reconstruir qual versão jurídica foi efetivamente revisada;
- conteúdo pseudonimizado, sem CPF/CNPJ/e-mail/telefone ou outros identificadores detectáveis em **qualquer campo versionado**;
- nenhuma jurisprudência placeholder/fictícia em `expected_citacoes` ou `jurisprudencia_esperada`;
- `id` único em todo o conjunto auditado, inclusive quando o corpus estiver repartido em vários arquivos.

O validador é deliberadamente offline: ele valida a **trilha de curadoria**, não tenta substituir o advogado por uma consulta de rede no CI. Se o sanitizer de PII estiver indisponível, o gate falha fechado.

## Cobertura de cenários

Quantidade por área, sozinha, não demonstra amplitude jurídica. Um corpus composto apenas por casos comuns pode produzir uma média alta e esconder falhas justamente nas bordas mais arriscadas. Por isso todo caso real é classificado em:

- `normal`: aplicação ordinária da regra;
- `fronteira`: fatos, competência, prazo, prova ou enquadramento próximos do limite relevante;
- `excecao`: hipótese em que uma exceção legal/jurisprudencial pode afastar a regra geral.

O gate amplo deve exigir amostra mínima também por classe de cenário. Essa classificação é evidência de cobertura, não autorização para a IA inferir automaticamente que uma exceção existe.

## Níveis de maturidade

1. **Smoke técnico** — exemplos/sintéticos; prova apenas formato e funcionamento do harness.
2. **Piloto humano** — mínimo 20 casos reais, pelo menos duas áreas; serve para obter baseline inicial.
3. **Gate jurídico inicial** — mínimo 50 casos reais e amostra mínima por área crítica definida pelo escritório.
4. **Gate jurídico amplo** — alvo de 100+ casos reais, com pelo menos 10 por área crítica e cobertura explícita de cenários normais, de fronteira e de exceção antes de usar média agregada como indicador institucional.

## Comandos

Validação de proveniência já bloqueante na suíte backend:

```bash
python -m pytest tests/test_gold_governance.py -q
```

Auditoria explícita do acervo real:

```bash
python -m app.eval.gold_governance
```

Gate de prontidão para 100 casos, 10 por área crítica e amplitude mínima de cenários:

```bash
python -m app.eval.gold_governance \
  --require-real \
  --min-total 100 \
  --areas penal,trabalhista,consumidor,tributario,ambiental \
  --min-casos-area 10 \
  --cenarios normal,fronteira,excecao \
  --min-casos-cenario 5
```

Depois que o corpus de avaliação estiver disponível no ambiente controlado, rode o benchmark real:

```bash
python -m app.eval.run_eval \
  --gold app/eval/gold_set.jsonl \
  --k 6 \
  --areas-obrigatorias penal,trabalhista,consumidor,tributario,ambiental \
  --min-recall 0.85 \
  --min-recall-area 0.80
```

A execução `--full --judge` deve ser feita no ambiente controlado com providers habilitados e orçamento definido; fallbacks devem permanecer identificados separadamente.

## Critérios P0 de falha

Independentemente da média de recall, o benchmark não deve ser interpretado como aprovado se houver:

- legislação revogada/suspensa apresentada como direito vigente;
- jurisprudência inventada tratada como confirmada;
- fonte fictícia/placeholder em caso real;
- PII real no gold set versionado;
- fonte oficial sem referência suficiente para reconstruir a versão revisada;
- consulta da fonte ou conferência de vigência posterior à data declarada de revisão;
- caso sem conteúdo/expectativa objetivamente avaliável;
- ID duplicado contando evidência mais de uma vez;
- área crítica sem amostra suficiente;
- corpus sem casos de fronteira/exceção no gate que exige amplitude;
- erro de avaliação escondido da média.

## Limitação atual

Sem um gold set humano-curado, o código pode provar somente **governança e funcionamento técnico do harness**. Não é tecnicamente nem juridicamente correto declarar a IA do EJC “aprovada” ou “10/10” a partir dos arquivos `*.example.*`.
