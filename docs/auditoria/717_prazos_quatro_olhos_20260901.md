# #717 — Prazos auditáveis e dupla validação

## Escopo desta branch

Esta implementação cobre somente o recorte **Prazos auditáveis + Dupla validação** da issue #717.
Os subescopos de integridade documental e pesquisa global permanecem independentes e não são declarados resolvidos por este PR.

## Invariantes

- prioridade `critica` nasce `confirmado=false`;
- prazo crítico registra `calculado_por`;
- prazo processual crítico exige `termo_inicial` e `regime_calculo` explícitos;
- o conferente de prazo crítico deve ser diferente do calculista;
- o endpoint canônico `/deadlines/{id}/confirmar` aplica a regra, sem rota paralela de bypass;
- ownership/RBAC é verificado antes da conferência;
- alteração material invalida a conferência anterior, troca o calculista para o autor da mudança e preserva histórico;
- nova conferência gera trilha de auditoria;
- reabertura de conferência adiciona notificação interna genérica na mesma transação, sem teor processual, parte, cliente ou número de processo;
- `data_intimacao` legado não é rebatizado silenciosamente como `termo_inicial`.

## Prova persistida

`calculo_metadata` registra, quando conhecidos:

- versão da prova e do motor;
- origem do cálculo;
- ciência, publicação, termo inicial, base usada pelo cálculo e termo final;
- regime e tribunal;
- quantidade de dias, dobro e exceção penal;
- regra jurídica;
- estado do calendário;
- exceções observadas no intervalo;
- SHA-256 das exceções de calendário;
- calculista e instante;
- histórico de recálculo/alteração;
- última conferência.

O snapshot não inclui `case_id`, número do processo, cliente, partes nem teor documental.

## Migration

Nenhuma migration adicional: utiliza exclusivamente as colunas aditivas introduzidas pela migration `156_prazos_auditaveis_regime` da #968.

## Rollback

Revert funcional deste PR, preservando as colunas da migration 156 e os snapshots já persistidos. Não executar downgrade físico para remover prova de cálculo/conferência já produzida.

## Gates

- CI Woodpecker verde no HEAD exato;
- #1343, #1344 e #1345 integrados na ordem;
- testes de RBAC/IDOR e quatro olhos;
- homologação H06 da #381/#1209;
- nenhuma publicação em produção antes da paridade de SHA e health checks.
