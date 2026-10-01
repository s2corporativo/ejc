# Aprendizado jurídico supervisionado do EJC

## Objetivo

Transformar o uso real do escritório em melhoria mensurável da IA sem tratar
saída de modelo, vitória processual ou correção isolada como verdade jurídica.

Fluxo canônico:

```
IA produz
→ advogado corrige
→ revisor independente aprova
→ correção entra na memória supervisionada
→ benchmark mede
→ roteamento pode usar desempenho certificado
→ holdout confirma generalização
```

Fonte oficial vigente, fatos do caso, sigilo e HITL continuam prevalecendo.

## 1. Banco de correções humanas

`POST /api/ia-learning/corrections` recebe a versão corrigida de um `AILog`,
motivo, tipo/severidade do erro, dificuldade e fontes conferidas. O texto é
pseudonimizado na barreira ORM e nasce `approved=false`.

`POST /api/ia-learning/{id}/review` exige nova ação humana. Correção só fica
`benchmark_eligible=true` quando o revisor é diferente do autor da correção.

## 2. Aprendizado por resultado do processo

`case_intel.aprendizado_encerramento` continua produzindo memória institucional
e tese em rascunho. Adicionalmente cria um evento `outcome` não aprovado. O
resultado do caso é evidência histórica, não prova de causalidade nem autorização
para reutilizar automaticamente a estratégia.

`POST /api/ia-learning/outcomes/backfill` reaplica o processo idempotente aos
casos já encerrados/arquivados.

## 3. Gold set incremental

`python -m app.eval.certification_progress` mede quatro marcos:

- 15 casos: baseline inicial;
- 30 casos: validação;
- 50 casos: robustez;
- 75 casos: certificação interna.

Caso sintético/candidato nunca conta. O gate de `gold_governance` continua
exigindo curadoria humana, pseudonimização, fonte oficial e vigência.

## 4–7. Casos-armadilha, falhas críticas, dificuldade e habilidades

`adaptive_bench.py` mede 100 pontos:

- fatos 10;
- issue spotting 15;
- enquadramento jurídico 15;
- fontes 15;
- prova/lacunas 10;
- estratégia 10;
- contraditório 10;
- riscos processuais 5;
- incerteza 5;
- conclusão 5.

Segmenta por `normal|complexo|fronteira|excepcional` e mede `trap_recall`.
Citação inexistente/incorreta, afirmação proibida ou fato inventado são falhas
críticas: a nota bruta permanece auditável, mas a nota de certificação do caso
vira zero.

Teste sintético do mecanismo:

```bash
python -m app.eval.adaptive_bench --simulate
```

O arquivo `gold_set_adaptive.synthetic.jsonl` existe apenas para provar o
harness; não mede qualidade jurídica real.

## 8. Roteamento por desempenho

`provider_quality_artifact.py` consolida métricas por área/tarefa/provider.
`provider_quality_policy.py` só recomenda um provider quando:

- `AI_ADAPTIVE_ROUTING_ENABLED=true`;
- artefato declara `certified=true`;
- holdout foi efetivamente avaliado;
- amostra alcança `AI_ADAPTIVE_ROUTING_MIN_CASES`;
- houve zero falha crítica;
- provider já é elegível pela policy normal.

A recomendação não contorna LGPD, sigilo, kill-switch ou provider explícito do
usuário. O default de produção permanece desligado até haver evidência real.

## 9. Banco de erros

`GET /api/ia-learning/errors` expõe apenas eventos humanos aprovados com
`error_type`. O orquestrador injeta no máximo algumas correções aprovadas como
**alerta metodológico**, explicitando que elas não são fonte jurídica.

## 10. Conhecimento temporal

Todo `upsert_documento` passa a registrar `source`, `jurisdiction`,
`last_ingested_at`, `last_verified_at` e `superseded_by`. Legislação sem
prova de vigência recebe `vigencia_nao_verificada`, nunca `vigente` por
presunção. Quando nasce nova versão, a anterior aponta explicitamente qual
documento a substituiu.

O gate RAG existente continua bloqueando legislação não verificada para
fundamentação de direito atual.

## 11. EJC versus modelo isolado

`architecture_comparison.py` compara relatórios emparelhados dos mesmos casos,
publica média do delta, vitórias/empates/derrotas e intervalo de confiança de 95%
por bootstrap.

```bash
python -m app.eval.architecture_comparison --simulate
```

A simulação testa apenas a estatística e vem marcada como não-evidência. A
medição real deve usar exatamente o mesmo corpus e modelo nas duas condições.

## 12. Holdout secreto

Casos finais ficam fora do Git em volume privado. `holdout_guard.py` recusa
como holdout secreto arquivo rastreado pelo Git e registra somente contagem e
SHA-256.

```bash
python -m app.eval.holdout_guard /volume/privado/holdout.jsonl
```

O holdout não pode orientar alterações de prompt, RAG, threshold ou provider.

## Dataset para eventual fine-tuning

`export_supervised_dataset.py` exporta exclusivamente correções aprovadas por
revisor independente. O comando **não treina modelo** e não promove versão.

Fine-tuning deve permanecer fora do pipeline automático até existir volume
suficiente de correções humanas de alta qualidade e até o holdout demonstrar
ganho real sobre a arquitetura RAG/orquestrada.

## Gates mínimos antes de habilitar routing adaptativo

1. Gold set humano sem erros de governança.
2. Baseline ≥15 casos e cobertura mínima definida por área.
3. Zero citação crítica no corpus de certificação.
4. Holdout secreto congelado e hash registrado.
5. Comparação provider/modelo na mesma amostra.
6. Artefato de qualidade certificado.
7. Revisão humana final do release.
