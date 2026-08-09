# Governança do Gold Set Jurídico — P0.2/P0.3

## Regra de verdade

O EJC não considera exemplos sintéticos, fixtures técnicas ou casos gerados por IA como evidência de qualidade jurídica. Só conta como **gold jurídico real** o caso pseudonimizado, curado por advogado e revisado por identidade independente, com fonte oficial e vigência conferidas.

O estado atual do repositório permanece explicitamente **não certificado** enquanto não existir `gold_set.jsonl`/equivalente humano-curado que passe em `python -m app.eval.gold_governance`.

## Evidência mínima por caso

Cada caso real deve declarar:

- `ficticio: false`;
- `area`;
- `curadoria.curador`;
- `curadoria.revisor`, diferente do curador;
- `curadoria.revisado_em` (`YYYY-MM-DD`);
- `curadoria.vigencia_conferida_em` (`YYYY-MM-DD`);
- ao menos uma entrada em `curadoria.fontes_oficiais` com título, URL HTTPS oficial e data de consulta;
- conteúdo pseudonimizado, sem CPF/CNPJ/e-mail/telefone ou outros identificadores detectáveis;
- nenhuma jurisprudência placeholder/fictícia em `expected_citacoes`.

O validador é deliberadamente offline: ele valida a **trilha de curadoria**, não tenta substituir o advogado por uma consulta de rede no CI.

## Níveis de maturidade

1. **Smoke técnico** — exemplos/sintéticos; prova apenas formato e funcionamento do harness.
2. **Piloto humano** — mínimo 20 casos reais, pelo menos duas áreas; serve para obter baseline inicial.
3. **Gate jurídico inicial** — mínimo 50 casos reais e amostra mínima por área crítica definida pelo escritório.
4. **Gate jurídico amplo** — alvo de 100+ casos reais, com pelo menos 10 por área crítica antes de usar média agregada como indicador institucional.

## Comandos

Validação de proveniência já bloqueante na suíte backend:

```bash
python -m pytest tests/test_gold_governance.py -q
```

Auditoria explícita do acervo real:

```bash
python -m app.eval.gold_governance
```

Gate de prontidão para 100 casos e 10 por área crítica:

```bash
python -m app.eval.gold_governance \
  --require-real \
  --min-total 100 \
  --areas penal,trabalhista,consumidor,tributario,ambiental \
  --min-casos-area 10
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
- área crítica sem amostra suficiente;
- erro de avaliação escondido da média.

## Limitação atual

Sem um gold set humano-curado, o código pode provar somente **governança e funcionamento técnico do harness**. Não é tecnicamente nem juridicamente correto declarar a IA do EJC “aprovada” ou “10/10” a partir dos arquivos `*.example.*`.
