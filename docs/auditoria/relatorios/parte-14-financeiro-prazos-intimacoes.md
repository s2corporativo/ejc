# Parte 14 — Financeiro e Prazos/Intimações (auditoria de código-fonte)

**Data:** 2026-08-10
**Método:** leitura do código-fonte no repositório (`main` em `4d5d4f1`). Diferente das partes 1–12,
que foram feitas por fora (HTTPS contra produção, sem código), esta parte lê o código.
Nenhum ambiente foi executado e nenhuma chamada foi feita a produção — os achados são de
leitura estática, e onde isso limita a conclusão está dito no próprio achado.

**Cobertura desta parte:** consolidado financeiro, despesas do escritório, honorários (`fees`),
calculadoras de honorários, motor de cálculo de prazos, módulo de Prazos e captura DJEN/intimações.

**NÃO coberto** (ver "Lacunas" ao final): NFS-e, contratos do escritório, gestão societária,
estimador de honorários OAB, assinaturas eletrônicas, Portal do Cliente, notificações,
configurações, lixeira, central de diagnóstico, checklists e produtividade.

---

## Sumário dos achados

| ID | Sev | Título |
|---|---|---|
| PRZ-01 | P0 | Termo inicial do prazo DJEN ignora o art. 224 §2 do CPC — vencimento 1 dia útil adiantado |
| PRZ-02 | P0 | Recesso do art. 220 não é aplicado em nenhum caminho real de criação de prazo |
| PRZ-03 | P1 | Data de disponibilização inválida vira `date.today()` silenciosamente |
| PRZ-04 | P2 | Prazo padrão de 15 dias quando o tipo não é reconhecido |
| FIN-01 | P1 | Consolidado ignora `fee_payments` — pagamento parcial não entra no "recebido no mês" |
| FIN-02 | P1 | Não existe motor de recorrência: despesa recorrente nunca se materializa no mês seguinte |
| FIN-03 | P1 | `/despesas/resumo` mistura totais de todas as competências com totais do mês |
| FIN-04 | P1 | `competencia` sem validação de formato — despesa some do consolidado |
| FIN-05 | P2 | Honorário cancelado ainda aceita pagamento e pode voltar a "pago" |
| FIN-06 | P2 | Despesa com `tipo='custas_despesas'` e descrição "sucumb" é contada duas vezes |
| FIN-07 | P2 | POST/PATCH de despesa sem schema Pydantic e sem trilha de auditoria |

---

## Prazos e intimações

### PRZ-01 (P0) — Termo inicial do prazo gerado por intimação DJEN ignora o art. 224 §2

**Evidência:** `backend/app/routers/intimacoes.py:378` e `:396-400`

```python
base = comunicacao.data_disponibilizacao      # linha 378
...
data_prazo = prazo_dias_uteis(base, payload.dias, tribunal=comunicacao.tribunal)
```

O mesmo em `_calcular_sugestao`, `backend/app/routers/intimacoes.py` (`data_sugerida =
prazo_dias_uteis(base, dias, tribunal=c.tribunal)`), com `base = c.data_disponibilizacao`.

E `prazo_dias_uteis` conta a partir do dia **seguinte** ao `data_inicio`
(`backend/app/services/deadline_calculator.py`, "Exclui o dia do início").

**O que a lei diz.** CPC art. 224 §2: considera-se data da **publicação** o primeiro dia útil
seguinte ao da **disponibilização** no DJe. CPC art. 224 §3: a contagem começa no primeiro dia
útil seguinte ao da **publicação**. São dois saltos, não um: o primeiro dia contado é o
**segundo** dia útil após a disponibilização.

**O que o código faz.** Um salto. Trata a disponibilização como se fosse a publicação.

**Impacto.** Todo prazo criado a partir de intimação DJEN vence **um dia útil antes** do prazo
legal. A direção do erro é conservadora para o protocolo (peticionar antes não perde prazo), mas
o dado gravado está errado e o sistema é a fonte de verdade da equipe: um prazo aparecerá como
`vencido` um dia útil antes de realmente vencer, e o advogado que confiar nisso pode concluir
que perdeu um prazo que ainda estava aberto. Em prazo de 5 dias o erro é 20% da contagem.

**Atenuante honesto:** a sugestão vem com aviso explícito ("confirme o tipo, o termo inicial e o
prazo na publicação original") e o desenho é de conferência humana. O defeito é do valor
default, não da ausência de governança.

**Correção sugerida.** Introduzir a etapa de publicação: `publicacao = proximo_dia_util(disponibilizacao)`
e contar a partir dela. Cobrir com teste de regressão incluindo caso em que a disponibilização
cai em véspera de feriado/fim de semana.

---

### PRZ-02 (P0) — O recesso do art. 220 não é aplicado nos dois caminhos que o advogado usa para criar prazo

**Evidência:** a função tem o parâmetro e a documentação diz quando usá-lo —
`backend/app/services/deadline_calculator.py`:

```python
def prazo_dias_uteis(data_inicio, dias, tribunal=None, em_dobro=False, aplicar_recesso=False):
    """...
    aplicar_recesso=True aplica a suspensão INTEGRAL do recesso do CPC art. 220
    (20/12 a 20/01, inclusive; ...) à contagem — usar em PRAZOS PROCESSUAIS.
    O default False mantém o comportamento histórico ... (recesso parcial
    20/12–06/01 via RECESSO_FORENSE quando forense=True)."""
```

Quem passa `aplicar_recesso=True`:
- `backend/app/services/motor_peca_service.py:379` e `:772` — e o `:772` é
  **`confirmar_e_criar_prazo` (`:667`), que TAMBÉM persiste um `Deadline`** (`:840`), após
  confirmação humana do termo inicial. É a implementação de referência correta, no mesmo repositório.
- `backend/app/services/evento_processual.py:107`
- `backend/app/routers/ramos.py:1614` (comparativo com/sem, deliberado)

Quem **não** passa — isto é, usa o default `False`:
- `backend/app/routers/deadlines.py:200` — `POST /deadlines`, que **persiste** o prazo;
- `backend/app/routers/intimacoes.py:396` (aceitar prazo da intimação), que também **persiste**;
- `backend/app/routers/deadlines.py:73` — `POST /deadlines/calcular`, que **não persiste**, mas
  exibe ao advogado uma projeção divergente da régua usada pelo motor de peças.

**Impacto.** Dos três caminhos que persistem prazo, dois — a criação manual e o aceite de
intimação, que são os que o advogado usa no dia a dia — suspendem apenas 20/12–06/01, enquanto o
art. 220 suspende até 20/01. O terceiro (motor de peças) faz certo. Todo prazo processual cuja contagem
atravessa 07/01–20/01 é calculado com dias úteis a mais do que a lei admite, e vence antes do
devido. Pior que o erro: **a mesma pergunta tem duas respostas no mesmo sistema** — o motor de
peças e o agente de IA respondem por uma régua, a tela de Prazos por outra. Um prazo conferido
nos dois lugares vai divergir, e não há nada na interface que explique por quê.

**Correção sugerida.** `aplicar_recesso=True` nos três caminhos, quando `tipo == "processual"`
(preservando `False` para decadencial/administrativo corrido, como a docstring exige). Teste de
regressão com contagem cruzando 07/01 comparando os dois caminhos.

---

### PRZ-03 (P1) — Data de disponibilização inválida vira "hoje" silenciosamente

**Evidência:** `backend/app/services/djen_service.py:278-297`

```python
def _parse_data_disp(raw: str | None) -> date:
    valor = (raw or "").strip()
    if not valor:
        return date.today()
    ...
    logger.warning("DJEN: data de disponibilização inválida; usando hoje")
    return date.today()
```

**Impacto.** A data de disponibilização é o termo inicial de todo o cálculo (PRZ-01). Se o DJEN
devolver o campo vazio ou num formato não previsto, o sistema grava **hoje** como termo inicial e
segue como se fosse dado bom. Um atraso de captura de três dias vira um prazo três dias mais
longo do que o real — e desta vez o erro é na direção perigosa: prazo mais folgado que o legal.
O `logger.warning` não chega a ninguém que decida.

**Correção sugerida.** Não inventar data. Gravar `data_disponibilizacao = NULL` e deixar a
intimação cair no caminho já existente de "sem data de disponibilização — informe o termo inicial
manualmente" (`intimacoes.py:388`), que já está implementado e é o comportamento correto.

---

### PRZ-04 (P2) — Prazo padrão de 15 dias quando o tipo não é reconhecido

**Evidência:** `backend/app/routers/intimacoes.py`, `_calcular_sugestao`: `if not casou:
tipo_detectado = "não identificado"; dias = 15; fundamentacao = None`.

O aviso é adequado ("prazo padrão de 15 dias úteis apresentado apenas como referência") e
`fundamentacao` fica `None`, o que é honesto. O risco residual é de interface: um número
plausível ao lado de números fundamentados tende a ser aceito. Vale conferir se a tela distingue
visualmente sugestão fundamentada de chute — não auditei o frontend deste módulo.

---

### O que está bom em Prazos (registro deliberado)

O motor de cálculo é a peça mais madura que li nesta auditoria. Feriados móveis por algoritmo de
Gauss, feriados municipais/estaduais carregados do banco e recarregados pelo scheduler,
suspensões por tribunal em tabela própria, prazo em dobro com os artigos certos (180/183/186/229,
inclusive a ressalva do §2º sobre autos eletrônicos), e — o mais raro — **limites declarados no
próprio código** ("suspensões processuais por TRIBUNAL ... NÃO estão cobertas aqui").

A conversão intimação→prazo (`intimacoes.py:423`) é transacional, grava `origem="djen"`, vincula
de volta (`comunicacao.prazo_deadline_id`) e é idempotente (retorna o prazo existente em vez de
duplicar). O serviço DJEN tem contagem estruturada de resultado (`recebidas`, `novas`,
`duplicadas`, `ignoradas`) e resumo codificado para heartbeat — ou seja, **a crítica da Parte 11
("monitoramento afere execução, não resultado") já foi endereçada no código**. Não pude verificar
se produção está capturando, porque não acessei produção.

---

## Financeiro

### FIN-01 (P1) — O consolidado ignora `fee_payments`

**Evidência:** `backend/app/routers/financeiro_consolidado.py:61-90` consulta apenas
`FROM fees` e `FROM office_expenses`. Nenhuma consulta a `fee_payments` no arquivo.

Mas pagamentos parciais existem e são gravados: `backend/app/routers/fees.py:230-283`
(`POST /fees/{id}/pagamentos`) grava em `FeePayment` e só muda `fees.status` para `pago` quando a
soma alcança o valor contratado.

**Impacto.** Um honorário de R$ 10.000 com R$ 7.000 já pagos aparece no consolidado como
R$ 0 recebidos e R$ 10.000 a receber. O dinheiro está no caixa e não está no relatório. E quando
quitar, os R$ 10.000 inteiros entram na competência do **último** pagamento, distorcendo dois
meses de uma vez. Para um escritório que cobra em parcelas — o caso normal — o "recebido no mês"
é simplesmente incorreto.

**Correção sugerida.** `recebido_mes` deve somar `fee_payments.valor` por
`date_trunc('month', data_pagamento)`, e `a_receber` deve ser `fees.valor - SUM(pagamentos)`.

---

### FIN-02 (P1) — O gerador de recorrentes multiplica despesas a cada execução

**Evidência:** `office_expenses` tem as colunas `recorrente` e `recorrencia`, gravadas em
`backend/app/routers/despesas.py:178-200` e filtráveis em `GET /despesas?recorrente=true`
(`despesas.py:73,90-92`).

No **backend** não há job: os únicos arquivos que tocam `office_expenses` no código de execução
(`backend/app`) são `routers/despesas.py`, `routers/relatorio.py` e
`routers/financeiro_consolidado.py` — nenhuma tarefa Celery, nenhum scheduler.

**Mas a geração existe, no frontend.** `frontend/src/pages/DespesasRecorrentes.tsx:70-96`
implementa `gerarProximoMes()`, que percorre as despesas com `recorrente=true` e faz um `POST
/despesas` por linha para a competência escolhida — e **grava cada cópia também com
`recorrente: true`**:

```tsx
for (const d of recorrentes) {
  await api.post("/despesas", { ...d, recorrente: true, competencia: targetComp });
}
```

**Impacto — crescimento exponencial, não ausência.** Como a cópia nasce marcada como recorrente,
ela entra no conjunto que a **próxima** geração vai clonar: 10 despesas fixas viram 20 no mês
seguinte, 40 no outro. E não há deduplicação por `(descricao, competencia)`: clicar duas vezes em
"Gerar lançamentos" para a mesma competência duplica tudo de novo, sem aviso.

O efeito no consolidado é o oposto do que se esperaria de um módulo "que não gera nada". As cópias
nascem com `status: "pendente"`, e o `caixa_periodo` só subtrai despesa com `status='pago'`
(`financeiro_consolidado.py`) — então o impacto imediato é **inflar as despesas lançadas e o
`a_pagar`**, não reduzir o caixa. O caixa só é atingido quando alguém quitar as duplicatas. O erro
se agrava a cada mês em que o botão for usado.

**Correção sugerida.** Separar *modelo* de *lançamento*: a despesa recorrente é o modelo
(`recorrente=true`) e as cópias geradas nascem com `recorrente=false` e `origem_id` apontando para
o modelo, com índice único `(origem_id, competencia)` fechando a idempotência no banco. A geração
deve migrar para o backend, onde a unicidade é aplicável. Teste de regressão obrigatório: gerar
duas vezes a mesma competência e conferir que a segunda é no-op.

**Nota de retificação:** a primeira redação deste achado afirmava que a recorrência era "só um
rótulo, sem motor". Estava errado — o motor existe no frontend, e o defeito é o oposto do
descrito. O erro veio de procurar apenas no backend. Apontado na revisão do PR #1060.

---

### FIN-03 (P1) — `/despesas/resumo` mistura competências

**Evidência:** `backend/app/routers/despesas.py:33-51`

```python
comp_filter = "AND competencia = :competencia" if competencia else ""
result = await db.execute(text(f"""
    SELECT
        COALESCE(SUM(CASE WHEN tipo = 'fixo'     AND deleted_at IS NULL THEN valor END), 0) AS total_fixo,
        COALESCE(SUM(CASE WHEN tipo = 'variavel' AND deleted_at IS NULL THEN valor END), 0) AS total_variavel,
        COALESCE(SUM(CASE WHEN status = 'pago'     AND deleted_at IS NULL {comp_filter} THEN valor END), 0) AS total_pago_mes,
        COALESCE(SUM(CASE WHEN status = 'pendente' AND deleted_at IS NULL {comp_filter} THEN valor END), 0) AS total_pendente_mes,
```

`total_fixo` e `total_variavel` **não recebem** o `comp_filter`; `total_pago_mes` e
`total_pendente_mes` recebem. O `por_categoria` logo abaixo (`despesas.py:44-51`) também ignora a
competência.

**Impacto.** No mesmo card, dois números do mês convivem com dois números de toda a história.
Quanto mais o sistema for usado, mais absurda fica a comparação. E o mesmo conceito
("despesas por categoria") responde diferente aqui e no consolidado, que **filtra** por
competência (`financeiro_consolidado.py:105`) — é a classe "painéis divergem entre si" já
identificada na auditoria externa, agora localizada no código.

**Correção sugerida.** Aplicar `comp_filter` aos quatro agregados e ao `por_categoria`, ou
renomear os campos para dizer o que são (`total_fixo_geral`). Preferível a primeira.

---

### FIN-04 (P1) — `competencia` sem validação de formato

**Evidência:** `backend/app/routers/despesas.py:168-201` — o POST recebe `body: dict = Body(...)`
e valida a presença de três campos, mas nenhum formato: `"competencia": body.get("competencia")`.
O PATCH (`despesas.py:220-224`) tem `competencia` na allowlist, também sem validação.

Do outro lado, o consolidado casa a competência por igualdade de string
(`WHERE ... competencia = :comp`, `financeiro_consolidado.py:100`) com o valor gerado como
`f"{t.year}-{t.month:02d}"` (`financeiro_consolidado.py:54`), isto é, `"2026-08"`.

**Impacto.** Uma despesa gravada com `"2026-8"`, `"08/2026"` ou vazio nunca mais aparece no
consolidado. Não dá erro, não avisa: o dinheiro simplesmente sai do relatório. O consolidado tem
`pattern=r"^\d{4}-\d{2}$"` no Query da entrada (`financeiro_consolidado.py:46`) — a validação
existe na leitura e falta justamente na escrita.

**Correção sugerida.** Schema Pydantic para o corpo com `competencia: str = Field(pattern=r"^\d{4}-\d{2}$")`,
e migration de saneamento para as linhas já gravadas fora do padrão (verificar antes se existem).

---

### FIN-05 (P2) — Honorário cancelado aceita pagamento e volta a "pago"

**Evidência:** `backend/app/routers/fees.py:238-242` — a busca filtra apenas `deleted_at`:

```python
select(Fee).where(Fee.id == fee_id, Fee.deleted_at.is_(None))
```

e adiante (`fees.py:264-268`) `fee.status = FeeStatus.pago` sem conferir o status anterior.

**Impacto.** Um honorário `cancelado` pode receber pagamento e ser revivido como `pago`, entrando
no `recebido_mes` do consolidado. Também não há teto: nada impede registrar pagamento acima do
valor contratado.

**Correção sugerida.** Recusar pagamento em honorário `cancelado` (409) e avisar (ou recusar)
quando a soma exceder o valor contratado.

---

### FIN-06 (P2) — Dupla contagem de "custas" com "sucumbência"

**Evidência:** `backend/app/routers/financeiro_consolidado.py:76-80`

```sql
... FILTER (WHERE status='pago' AND ... AND (CAST(tipo AS text) = '{_SUCUMB}' OR descricao ILIKE '%sucumb%')) AS rec_sucumbencia,
... FILTER (WHERE status='pago' AND ... AND tipo='custas_despesas')                                          AS rec_custas,
```

O filtro de sucumbência casa por descrição **independente do tipo**; o de custas casa por tipo
sem excluir a descrição. Um lançamento `tipo='custas_despesas'` cuja descrição mencione
"sucumbência" entra nos dois. A soma das quatro categorias passa a ser maior que
`recebido_mes`. Simétrico no bloco `previsto`.

**Correção sugerida.** Classificar por `tipo` e usar a descrição só como fallback para linhas
legadas sem o label do enum — não como critério paralelo.

---

### FIN-07 (P2) — Despesas sem schema e sem trilha de auditoria

**Evidência:** `despesas.py:168` (`body: dict = Body(...)`) e `despesas.py:206`. `valor` entra
como `body.get("valor", 0)` sem tipo nem sinal; `status` e `tipo` são texto livre sem domínio.
Nenhuma chamada a `criar_audit_log` em todo o arquivo — enquanto `fees.py` registra auditoria em
criação, alteração, pagamento e cancelamento (`fees.py:177,215,270,304`).

**Impacto.** Valor negativo, string, ou `status` fora do vocabulário passam direto. E alteração de
despesa do escritório não deixa rastro de quem mudou o quê — assimetria difícil de justificar num
módulo financeiro. Detalhe menor no mesmo arquivo: `updates["updated_at"] = "NOW()"`
(`despesas.py:228`) é um bind param que a query não usa (o SQL já tem `updated_at = NOW()` literal).

---

### O que está bom em Financeiro (registro deliberado)

Matemática monetária correta: `Numeric(14,2)` no model (`backend/app/models/fee.py`), `Decimal`
com `ROUND_HALF_UP` no consolidado (`financeiro_consolidado.py:23-29`), e a decisão consciente de
não converter para `float` antes da fronteira de serialização — comentada no código, o que é raro.

RBAC financeiro é least-privilege de verdade e o código explica a escolha:
`financeiro_consolidado.py:41-43` usa conjunto explícito **em vez de** `require_roles`, com o
comentário "NÃO require_roles, que pelo fallback hierárquico deixaria advogado passar". Mesmo
padrão em `despesas.py:13-21` e `fees.py:26-39`.

`fees.py` é transacional e auditado: pagamento faz `db.add` + `flush` + recálculo + audit log e um
único `commit` (`fees.py:246-279`).

`honorarios_calc.py` faz gate de ownership contra IDOR (`verificar_acesso_caso`), cita os artigos
(CPC art. 85 §2º) e implementa alerta de teto ético sobre o proveito econômico. Observação: o teto
é apenas informativo — nada impede cadastrar honorário acima dele, e o resultado não é persistido
no caso.

---

## Lacunas desta auditoria

As frentes paralelas despachadas foram todas interrompidas por limite de sessão da API antes de
produzir resultado. Ficaram **fora do escopo desta Parte 14** os seis grupos abaixo — todos
cobertos depois, nas Partes 15 a 20 do mesmo PR, e nada deve ser presumido sobre eles:

- **NFS-e** (`backend/app/routers/nfse.py`, 842 linhas) — a pergunta central em aberto é se emite
  nota de verdade ou só grava registro local. O `main.py:416` a descreve como "GATED, homologação".
- **Contratos do escritório** (`office_contracts.py`) e **gestão societária / retiradas**
  (`partner_withdrawals.py`, `sociedades_cliente.py`) — cap table, pró-labore, quem pode lançar.
- **Estimador de honorários OAB** (`honorarios_oab.py`, 456 linhas — usa IA/RAG sobre a tabela da OAB).
- **Assinaturas eletrônicas** — natureza da assinatura e valor probatório (MP 2.200-2/2001).
- **Portal do Cliente** — isolamento por cliente (IDOR) e, em especial, se a métrica de "chance de
  êxito" vaza para o cliente (Provimento OAB nº 205/2021, art. 6º — vedação a promessa de resultado).
- **Notificações, Configurações, Lixeira, Central de Diagnóstico, Checklists, Produtividade.**

Uma correção de rumo em relação à auditoria externa: o **prefixo `/v1/` duplicado não existe mais**
no código. Todos os routers financeiros declaram prefixo simples (`/despesas`, `/fees`,
`/office-contracts`, `/partner-withdrawals`) e `grep -rn 'prefix="/v1'` em `backend/app` não
retorna nada. O achado das Partes 8, 9 e 11 está resolvido no repositório.
