# #1342 — Agenda v2: preparação temporal antes da migration

## Diagnóstico confirmado

A agenda atual usa a tabela `agenda_eventos` 100% por SQL cru. Ela foi criada na migration 053 com `data_evento DATE` e `hora VARCHAR(10)`. O conflito atual compara apenas mesmo responsável + mesma data + mesma string de hora. O scheduler possui regra específica para `tipo='audiencia'` em D-3, D-1 e D0.

Não existe model ORM canônico de `agenda_eventos`; esta evolução não deve criar um model paralelo só para acomodar a feature.

## Restrição de governança Alembic

A branch-base contém a migration 156 ainda em PR. O próprio `MIGRATION_RESERVATIONS.md` determina que branches empilhadas não reservem uma sequência futura antes de o head anterior integrar a `main`. Portanto **esta branch não cria nem reserva a migration 157**.

A migration de ativação só deve ser criada depois que `156_prazos_auditaveis_regime` for o head efetivo da `main` e os guards confirmarem head único.

## Implementado nesta preparação

`backend/app/services/agenda_interval_service.py` concentra, sem banco:

- timezone IANA validado;
- intervalo canônico `inicio/fim`;
- evento de dia inteiro como intervalo semiaberto;
- sobreposição real de intervalos em UTC;
- adapter conservador para legado com hora;
- ausência de hora legada não recebe horário inventado;
- lembretes configuráveis em minutos;
- preservação dos defaults de audiência D-3/D-1/D0;
- recorrência diária, semanal e mensal;
- quantidade ou data limite obrigatória;
- limite rígido anti-expansão infinita;
- exceção de ocorrência;
- recorrência mensal com dia-âncora, evitando deriva 31/01 → 28/02 → 28/03.

## Migration de ativação — somente após 156 integrar

A implementação final deverá preferir operações aditivas e manter os campos legados durante transição. Proposta sujeita a confirmação do head real:

### `agenda_eventos`
- `inicio_em TIMESTAMPTZ NULL`
- `fim_em TIMESTAMPTZ NULL`
- `timezone VARCHAR(64) NULL`
- `dia_inteiro BOOLEAN NULL`
- `serie_id VARCHAR(36) NULL`
- `ocorrencia_indice INTEGER NULL`
- `lembretes_minutos JSONB NULL`
- `lembretes_enviados JSONB NULL`

Nenhum backfill pode inventar `fim_em` para eventos legados. `data_evento/hora` permanecem durante compatibilidade.

### Série/recorrência

Antes da migration final, confirmar se o melhor desenho é tabela normalizada de série ou regra JSONB no primeiro evento. Requisitos mínimos:
- idempotência por série + índice de ocorrência;
- edição de ocorrência única sem reescrever a série silenciosamente;
- exclusão/soft-delete de ocorrência sem apagar a série;
- alteração de série auditável;
- limite de materialização por janela.

## Segurança/LGPD

- conflito de agenda alheia continua censurado;
- nenhuma expansão de série amplia ownership;
- lembrete não deve revelar título/local de agenda alheia;
- logs de série devem usar IDs e parâmetros temporais, sem descrição/cliente/partes;
- criação/transferência para terceiro continua restrita à gestão.

## Gates de ativação

1. migration 156 integrada e `alembic heads` único;
2. reservar próximo prefixo no ledger;
3. migration aditiva + downgrade testado;
4. router usa intervalo real quando os novos campos existirem e mantém leitura legada;
5. scheduler migra de regra exclusiva de audiência para offsets persistidos, preservando defaults;
6. frontend oferece início/fim/dia inteiro/timezone/recorrência/lembretes;
7. UX distingue editar esta ocorrência x série;
8. testes RBAC/IDOR, overlap, timezone, recorrência, dedup e upgrade/downgrade;
9. sem produção antes dos gates do stack P0/P1/#968/#717.
