# Núcleo operacional do caso — próxima ação e saúde

## Objetivo

Este núcleo responde, com dados auditáveis:

- o que precisa ser feito;
- por quem;
- até quando;
- com origem em qual registro;
- qual impedimento existe;
- qual é o estado operacional atual.

Ele não substitui o workflow jurídico do `LegalCaseOrchestrator`. O estado
operacional é derivado da próxima ação e do status canônico do caso.

## Modelo de dados

A migration `113_case_next_action` é aditiva e reversível.

- `case_next_actions`: histórico das ações; índice parcial garante no máximo
  uma ação atual por caso.
- `case_next_action_waivers`: exceções temporárias, justificadas e auditadas.
- Não existe backfill sintético. Casos legados aparecem como pendência.
- A linha do tempo usa `CaseMovimento`, já canônico no EJC.

Cada ação guarda responsável, data esperada, urgência, bloqueio, origem, autoria,
conclusão e eventual substituição. A origem não manual é validada no mesmo caso.

## Estados operacionais

| Estado | Regra determinística |
|---|---|
| Onboarding | caso em triagem e sem ação |
| Planejamento | caso aberto sem ação, com ou sem exceção vigente |
| Em andamento | ação atual não urgente |
| Aguardando cliente | ação bloqueada pelo cliente |
| Aguardando terceiro | ação bloqueada por terceiro/tribunal ou caso suspenso |
| Providência urgente | urgência crítica ou vencimento em até três dias |
| Negociação | status jurídico de acordo |
| Encerrado | status jurídico encerrado ou arquivado |

Esses estados não representam chance de êxito.

## API e permissões

- `GET /cases/{id}/proxima-acao`
- `PUT /cases/{id}/proxima-acao`
- `POST /cases/{id}/proxima-acao/concluir`
- `POST /cases/{id}/proxima-acao/dispensar`
- `GET /dashboard/pendencias-operacionais`

Leitura e escrita reutilizam o gate canônico de ownership do caso. Só equipe
jurídica autorizada pode alterar. Sócios e administração podem atribuir a
usuários internos ativos; clientes externos nunca podem ser responsáveis.

## Implantação gradual

1. Aplicar a migration com `CASE_NEXT_ACTION_ENFORCEMENT=false`.
2. Validar criação, substituição, conclusão, dispensa, timeline e dashboard.
3. Reconciliar casos legados sem responsável ou próxima ação.
4. Executar piloto com um conjunto controlado de casos.
5. Medir pendências por sete dias e corrigir falsos positivos.
6. Ativar `CASE_NEXT_ACTION_ENFORCEMENT=true`.
7. Confirmar que encerramento/arquivamento exige:
   - ação atual concluída;
   - prazos pendentes/vencidos resolvidos;
   - prazos extraídos confirmados ou cancelados;
   - tarefas abertas concluídas.

Com enforcement ativo, alterações diretas para estado terminal são bloqueadas;
devem passar pelos fluxos canônicos de encerramento ou arquivamento.

## Rollback

Rollback imediato e sem perda de dados:

1. definir `CASE_NEXT_ACTION_ENFORCEMENT=false`;
2. reiniciar apenas pelo procedimento seguro de deploy;
3. validar que operações antigas voltaram a ser não bloqueantes.

As tabelas podem permanecer instaladas em modo observação. O downgrade da
migration só deve ocorrer se nenhum consumidor depender dos registros e depois
de exportar o histórico, pois remover as tabelas elimina dados operacionais.

## Critérios de aceite

- um caso possui no máximo uma ação atual;
- concluir e substituir é uma única transação;
- dispensa tem motivo, validade máxima de 90 dias e autoria;
- toda mutação cria audit log e evento na timeline;
- origem não manual pertence ao mesmo caso;
- saúde operacional não é apresentada como probabilidade jurídica;
- dashboard respeita RBAC e ownership;
- casos legados não são preenchidos com dados inventados.
