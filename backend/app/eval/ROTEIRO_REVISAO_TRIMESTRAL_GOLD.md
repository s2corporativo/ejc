# Roteiro de Revisão Trimestral do Gold Set Jurídico — EJC

**Documento de governança | Versão 1.0 | 2026-08-20**

**Curador:** Manus IA — assistente técnico sob supervisão | **Revisor:** Dr. Clovis José Soares (OAB/MG)

---

## 1. Finalidade

Este roteiro padroniza a revisão trimestral do gold set jurídico humano-curado do EJC (`backend/app/eval/gold_set*.jsonl`), garantindo que o corpus de certificação permaneça fiel à legislação vigente, à jurisprudência atual e aos critérios do gate de governança do Release Gate (`ejc-release-gate.yml`).

## 2. Periodicidade e gatilhos

| Gatilho | Prazo | Escopo |
|---|---|---|
| Revisão ordinária | A cada 90 dias (calendário: 20 nov/2026, 18 fev/2027, 19 mai/2027, 17 ago/2027...) | Todos os gold sets |
| Alteração legislativa relevante (nova lei, emenda, revogação) | Em até 15 dias da publicação | Casos que citam a norma alterada |
| Cancelamento/edição de súmula ou tese (STF/STJ) | Em até 15 dias | Casos que citam a súmula/tese |
| Mudança no gate do Release Gate | Na mesma sessão do CI | Casos e validações |

## 3. Procedimento de execução (sequência obrigatória)

**Passo 1 — Detecção de vigência desatualizada.**
Para cada caso, comparar `curadoria.vigencia_conferida_em` com a data atual. Casos com vigência conferida há mais de 120 dias entram na fila de re-consulta. Ajustar a tolerância no comando:

```bash
# filtro de casos desatualizados (script auxiliar — comparar campo vigencia_conferida_em)
python3 -c "
import json, datetime
limite = datetime.date.today() - datetime.timedelta(days=120)
for nome in ['gold_set_civel','gold_set_consumidor','gold_set_penal','gold_set_trabalhista','gold_set_tributario','gold_set_empresarial','gold_set_administrativo']:
    arq = f'app/eval/{nome}.jsonl'
    velhos = [c['id'] for l in open(arq) if l.strip()
              and datetime.date.fromisoformat(json.loads(l)['curadoria']['vigencia_conferida_em']) < limite]
    if velhos: print(nome, len(velhos), velhos)
"
```

**Passo 2 — Re-consulta das fontes oficiais.**
Para cada caso na fila, reconsultar a URL de cada fonte em `curadoria.fontes_oficiais` e verificar: (i) a norma permanece vigente na versão indicada em `identificador_versao`; (ii) o texto do artigo citado não foi alterado. Atualizar `vigencia_conferida_em` e, se houver alteração de conteúdo, atualizar `identificador_versao` ou `hash_sha256` e ajustar `expected_citacoes`/`notes`.

**Passo 3 — Verificação jurisprudencial.**
Consultar as bases oficiais (scon.stj.jus.br, portal.stf.jus.br) para confirmar que súmulas e teses citadas não foram canceladas, editadas ou superadas por repetitivo posterior. Súmulas canceladas exigem substituição do caso ou ajuste da `notes`.

**Passo 4 — Validação formal.**
Executar os comandos oficiais do gate a partir de `backend/`:

```bash
python -m app.eval.gold_governance --require-real \
  --min-total 105 \
  --areas consumidor,trabalhista,civel,penal,tributario,empresarial,administrativo \
  --min-casos-area 15 \
  --cenarios normal,fronteira,excecao \
  --min-casos-cenario 5

python -m app.eval.run_eval --smoke \
  --areas-obrigatorias consumidor,trabalhista,civel,penal,tributario,empresarial,administrativo \
  --min-casos-area 15

ruff check app/eval
```

**Passo 5 — Registro da revisão.**
Atualizar este documento com a data da revisão, os casos alterados e o resultado da validação. Qualquer alteração de caso deve ser submetida por **PR separado** (branch `fix/gold-revisao-trimestral-YYYY-MM`), com corpo DoD do Release Gate, curadoria re-assinada e nova `vigencia_conferida_em`.

## 4. Checklist da revisão trimestral

- [ ] Vigência de todas as leis citadas confirmada no Planalto
- [ ] Súmulas e teses conferidas (nenhuma cancelada/alterada)
- [ ] URLs das fontes respondem (HTTP 200) e permanecem em domínio oficial
- [ ] `gold_governance --require-real` retorna `casos presentes cumprem a proveniência mínima`
- [ ] `run_eval --smoke` retorna `SMOKE OK`
- [ ] `ruff check app/eval` sem erros
- [ ] PR de revisão aberto e merged (se houver alterações)
- [ ] Data desta revisão registrada na tabela abaixo

## 5. Histórico de revisões

| Revisão | Data | Executor | Alterações | Resultado |
|---|---|---|---|---|
| 1ª (constituição) | 2026-08-20 | Manus IA sob supervisão do Dr. Clovis | Curadoria inicial: 122 casos materiais (7 áreas) + 20 entradas adversariais | Gate verde |

## 6. Observações de governança

O gold set adversarial (`gold_set_adversarial.jsonl`) é benchmark agêntico de segurança e **não conta** como cobertura material do gate (é excluído pelo critério `intencao`/`query` do `gold_governance.py`). Sua revisão trimestral segue os mesmos passos 1 e 3, verificando que os comportamentos esperados permanecem corretos frente a mudanças normativas citadas nos payloads.

A curadoria de cada caso permanece sob o modelo de dupla verificação: curador técnico (Manus IA) e revisor humano (Dr. Clovis José Soares, OAB/MG). Nenhuma revisão é concluída sem a assinatura do revisor no campo `curadoria.revisado_em`.
