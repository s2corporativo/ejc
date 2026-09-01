# #968 — reconstrução auditável de Prazos/DJEN

## Invariantes jurídicos

1. `data_disponibilizacao`, `data_publicacao`, `termo_inicial` e `data_prazo` são marcos distintos.
2. Nenhum marco ausente é inferido a partir de outro.
3. Regime processual é explícito: `civel`, `trabalhista` ou `penal`.
4. Movimento DataJud não é fonte suficiente para materializar vencimento.
5. Comunicação DJEN só materializa `Deadline` depois de revisão humana da fonte oficial.
6. Legado não recebe backfill de publicação/termo inicial.
7. A trilha mínima de cálculo/revisão fica persistida em `calculo_metadata` e nos atores de cálculo/conferência.

## Migration

- revisão: `156_prazos_auditaveis_regime`
- base: `155_indices_listagem_espinha`
- somente colunas nullable/aditivas
- sem `UPDATE`, `DELETE`, `DROP` no upgrade
- downgrade remove somente as colunas introduzidas pela 156

## Fluxo DJEN

A Central exibe a disponibilização capturada como fato da fonte e exige que o operador informe separadamente publicação, termo inicial, regime e vencimento. O aceite exige confirmação explícita de conferência da fonte oficial e valida cronologia mínima.

## Gates

- Alembic head único = 156 nesta branch
- prova estática de ausência de backfill
- teste opcional PostgreSQL real 155 → 156 → 155
- testes backend do contrato DJEN
- Vitest da Central de Atividades
- lint/build frontend
- nenhuma publicação em produção antes de #1209/H06 da #381

## Rollback

Reverter o PR e executar downgrade da 156 somente quando houver decisão operacional explícita e backup, caso a migration já tenha sido aplicada em ambiente de homologação. Produção não faz parte deste PR.
