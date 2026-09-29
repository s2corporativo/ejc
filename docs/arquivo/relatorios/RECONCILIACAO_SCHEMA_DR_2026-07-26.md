# Reconciliação de schema para DR — prova de GAP vazio (2026-07-26)

## Objetivo

As migrations **040–043** foram aplicadas direto no container de produção e
nunca versionadas; `backend/alembic/versions/044_recover_head.py` é um stub
`pass` que apenas religa o grafo Alembic `039 -> 044`. Risco declarado (P0):
`alembic upgrade head` em **banco limpo** (disaster recovery / staging) não
reconstruiria o schema completo, quebrando com `UndefinedTable`/`UndefinedColumn`.

Esta auditoria determinou, **de forma determinística e sem acesso ao banco de
produção**, se ainda existe GAP entre o que a cadeia de migrations cria e o que
o código espera — e concluiu que **o GAP é VAZIO**: a `053_reconcile_schema.py`
somada às migrations 045–120 já compensa integralmente o conteúdo das
migrations perdidas. **Nenhuma migration nova (121) foi necessária.**

## Método (reproduzível)

Análise 100% estática, executada sobre o commit `origin/main` (head Alembic
`120_chunk_pagina`, único — confirmado com `python -m alembic heads`):

1. **Conjunto A** — tudo que a cadeia completa de migrations CRIA:
   - parse AST de **todas** as revisões em ordem topológica (base → head, via
     `ScriptDirectory.walk_revisions()`), analisando **somente `upgrade()`**
     (o `downgrade()` contém os drops reversos e não pode contaminar o conjunto);
   - capturas: `op.create_table` (+ colunas `sa.Column`), `op.add_column`,
     `op.drop_table`, `op.drop_column`, `op.rename_table`,
     `op.alter_column(new_column_name=...)` e, dentro de `op.execute`, regex
     sobre SQL bruto: `CREATE TABLE [IF NOT EXISTS]` (com parse de colunas do
     DDL, após remoção de comentários `--`), `DROP TABLE`, `ALTER TABLE ...
     ADD/DROP COLUMN`, `RENAME TO`, `CREATE [OR REPLACE] VIEW`;
   - drops/renames aplicados **em ordem**, para que A reflita o estado final.
2. **Conjunto B** — o que o código espera:
   - (a) `Base.metadata` após `import app.models` (mesmo mecanismo do
     `alembic/env.py`): **97 tabelas** com todas as colunas;
   - (b) tabelas raw-SQL referenciadas em `backend/app/` (regex
     `FROM|JOIN|INSERT INTO|UPDATE|DELETE FROM` sobre strings SQL em AST);
   - (c) tabelas **auto-bootstrap** (criam-se em runtime com
     `CREATE TABLE IF NOT EXISTS` dentro do próprio service) — fora do escopo
     de migrations.
3. **GAP = B ∖ A ∖ auto-bootstrap**, em nível de tabela E de coluna.

Resultado bruto: A = **131 tabelas** criadas pela cadeia; B(a) = **97 tabelas**
de models.

## Resultado

### GAP de tabelas dos models: **VAZIO**

Todas as 97 tabelas de `Base.metadata` possuem `create` na cadeia de migrations.

### GAP de colunas dos models: **VAZIO**

Toda coluna de todo model é criada por `op.create_table`/`op.add_column`/
`ALTER TABLE ADD COLUMN` da cadeia (consideradas as remoções, ex.
`112_client_pii_drop_plaintext`). Único candidato inicial —
`tabela_oab_honorarios.vigencia_fim` — era artefato do parser (comentário SQL
`--` dentro do DDL da 062); a coluna **é criada** pela
`062_redesign_tables.py` (linha 108).

### GAP de tabelas raw-SQL (sem model ORM): **VAZIO**

Todas as tabelas 100% SQL cru consultadas pelo código são criadas pela cadeia —
a maioria pela `050_novos_modulos.py` e pela `053_reconcile_schema.py`
(`agenda_eventos`, `areas`, `kanban_columns`, `client_pending_items`,
`domain_events`, `office_contracts`, `office_expenses`, `partner_withdrawals`),
além das históricas (`portal_mensagens` 035, `memoria_institucional` 034,
`score_juridico` 031, `indice_risco_historico` 032, `case_etiquetas` 037,
`case_ambiental`/`document_access_log`/`due_diligence_templates`/
`inadimplencia_alerts`/`modelos_documentos`/`peca_codigo_contador`/
`pricing_rules`/`teses_vitoriosas` 050). A view `vw_atividades` é criada na 053
e recriada (enriquecida) na `100_vw_atividades_enriquecida.py`.

### Auto-bootstrap (fora do escopo — NÃO precisam de migration)

Criam-se sozinhas em runtime via `CREATE TABLE IF NOT EXISTS` no service:

| Tabela | Onde se auto-cria |
|---|---|
| `backup_drive_state` | `app/services/backup_service.py` |
| `google_drive_sync_state` | `app/services/google_drive_service.py` |
| `indices_bcb_cache` | `app/services/indices_service.py` |
| `indices_bcb_cache_meta` | `app/services/indices_service.py` |
| `infosimples_uso` | `app/services/infosimples_service.py` |
| `pncp_cache` | `app/services/pncp_service.py` |
| `radar_legislativo_visto` | `app/services/radar_legislativo.py` |
| `transparencia_cache` | `app/services/transparencia_service.py` |

Nota (revisão do PR #485): `pncp_cache` foi adicionada nesta lista após o
review — o scan inicial rodou sobre uma árvore de trabalho em que outro branch
havia removido `pncp_service.py` temporariamente. No teste de paridade a lista
de auto-bootstrap é DESCOBERTA dinamicamente (varredura AST de `backend/app` +
`seeds` por `CREATE TABLE IF NOT EXISTS`, incluindo evolução runtime via
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, ex. `backup_drive_state.offsite_ok`),
justamente para não depender de allowlist congelada.

### Falsos positivos descartados na varredura raw-SQL

`alembic_version` (tabela do próprio Alembic) e `created_at`/`current_date`/
`data_conclusao`/`data_encerramento`/`data_pagamento` (colunas capturadas pelo
regex em `EXTRACT(EPOCH FROM <coluna>)` — não são tabelas).

## Refinamentos após o review do PR #485

O teste de paridade foi endurecido em cinco pontos (apontamentos do Codex):

1. **Descoberta dinâmica de tabelas raw-SQL**: além do inventário mínimo
   explícito, o teste varre por AST todas as strings SQL de `backend/app`
   (`FROM`/`JOIN`/`INSERT INTO`/`UPDATE ... SET`/`DELETE FROM`) e exige que
   TODA tabela referenciada esteja classificada (migration, model,
   auto-bootstrap ou falso positivo documentado). Allowlist congelada deixou
   de ser o mecanismo de cobertura.
2. **Semântica Postgres no parser**: `CREATE TABLE IF NOT EXISTS` repetido é
   tratado como no-op (primeira definição vence; coluna nova só via
   `ADD COLUMN` explícito) — espelha o comportamento real num upgrade limpo
   (caso 017 vs 052, tabelas de workflow).
3. **Metadata do app completo**: o coletor importa `app.main` (não só
   `app.models`), registrando models definidos em routers
   (`dataroom_salas`, `teses_juridicas_v4` — criadas pela 067; a 114
   consolida dados sem dropá-las). Mesmo racional do `test_schema_sync`.
4. **Paridade parcial de colunas raw-SQL**: colunas nomeadas em
   `INSERT INTO tabela (col, ...)` são extraídas deterministicamente e
   conferidas contra a definição criada pela cadeia (ou o DDL runtime, para
   auto-bootstrap).
5. **Prova em banco realmente vazio**: o teste DB-gated provisiona um banco
   novo (`CREATE DATABASE ejc_dr_parity_check`), roda `alembic upgrade head`
   nele (a própria cadeia cria `vector`/`pg_trgm` — 001/009), valida via
   inspector e dropa o banco — independente do estado do banco do CI, que já
   chega migrado no passo anterior ao pytest.

O GAP permaneceu **vazio** após todos os refinamentos.

## Limitações conhecidas

- **Colunas de tabelas raw-SQL em SELECT/WHERE**: a paridade de coluna para
  tabelas sem model cobre apenas o caminho de escrita (`INSERT INTO t (...)`),
  que é parseável de forma determinística. Extrair colunas de
  SELECT/WHERE/expressões arbitrárias exigiria um parser SQL completo, com
  alto custo e risco de falso positivo; o risco residual de `UndefinedColumn`
  nessas leituras é mitigado por (a) a superfície raw-SQL ser legada e
  congelada (guardas da Etapa 6 no `alembic/env.py`), (b) os testes
  `*_dblevel.py` exercitarem essas consultas contra Postgres real no CI, e
  (c) o teste DB-gated validar a existência das tabelas após upgrade em banco
  vazio.
- **SQL montado dinamicamente** (nomes de tabela em f-strings/variáveis) não é
  capturado pelo scanner — não há ocorrência conhecida no código atual.

## Decisão

- **Nenhuma migration `121_reconciliacao_dr` foi criada** — não há o que
  reconciliar; criar uma migration vazia/no-op só poluiria o grafo. O head
  permanece `120_chunk_pagina`.
- A prova vira **guarda permanente de regressão**:
  `backend/tests/test_schema_dr_parity.py` reexecuta esta mesma análise
  estática a cada CI (sem banco) e, com `RUN_DB_TESTS=1` (job `db-validation`
  do CI, Postgres+pgvector limpo), valida ao vivo que `alembic upgrade head`
  deixa todas as tabelas/views esperadas existindo. Se um model ou tabela
  raw-SQL nova nascer sem migration (o exato modo de falha das 040–043
  perdidas), o teste quebra **antes** do merge.

## Como validar

```bash
cd backend
python3 -m alembic heads                       # -> 120_chunk_pagina (único)
python3 -m pytest tests/test_alembic_single_head.py tests/test_schema_dr_parity.py -q
# com Postgres+pgvector de pé e migrations aplicáveis:
RUN_DB_TESTS=1 python3 -m pytest tests/test_schema_dr_parity.py -q
```

## Rollback

Sem mudança de schema (nenhuma migration criada). Reverter = remover o teste e
este documento; `alembic downgrade` não é afetado.

## Restrições respeitadas

- Nenhuma migration existente alterada; nenhum model tocado.
- Pendências das Etapas 6B/6C respeitadas: nenhum objeto marcado em espera foi
  recriado ou dropado (6C manteve todas as colunas vivas; nada a recriar).
