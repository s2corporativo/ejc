# Auditoria E2E — Financeiro/Fiscal — 02/09/2026

## Escopo

Auditoria, estabilização, consolidação funcional e hardening do domínio financeiro do EJC sobre a branch `audit/financeiro-e2e-20260902`, sem deploy de produção e sem migration concorrente.

Domínios cobertos: honorários, pagamentos, cobrança/inadimplência, despesas do escritório, despesas extras manuais, consolidado financeiro, contratos, sociedade/cap table, retiradas, PIX, Portal Financeiro, estimador, jobs financeiros e pré-fechamento mensal.

## Arquitetura operacional consolidada

A superfície do Financeiro foi reduzida ao fluxo diário:

- **Visão geral** — caixa, recebíveis, contas a pagar, fila de atenção e pré-fechamento;
- **Recebimentos** — honorários, pagamentos parciais, saldo, cobrança e histórico;
- **Despesas** — fixas, variáveis e extras no cadastro canônico;
- **Mais** — NFS-e e contratos do escritório.

A gestão societária deixou de fazer parte do fluxo financeiro diário e passou a módulo próprio, restrito a `superadmin`, `admin` e `socio`. A precificação/estimador de honorários foi movida para Inteligência Jurídica e o backend exige perfil jurídico compatível. Deep-links legados permanecem apenas por compatibilidade.

## Fontes de verdade

| Conceito | Fonte canônica | Critério |
|---|---|---|
| Valor contratado | `fees.valor` | valor original/contratado, não caixa |
| Pagamentos recebidos | `fee_payments.valor` | subledger imutável de recebimentos |
| Entrada de caixa | `fee_payments.data_pagamento` | mês efetivo do recebimento |
| Saldo a receber | `max(fees.valor - sum(fee_payments.valor), 0)` | residual |
| Despesa por competência | `office_expenses.competencia` | obrigação gerencial do mês |
| Saída de caixa | `office_expenses.pago_em` | mês efetivo do pagamento |
| Comprovante de recebimento | `fee_payments.comprovante_doc_id` | documento compatível com o caso |
| Auditoria | `audit_logs` | eventos críticos financeiros/societários |

O Financeiro não usa `updated_at` ou status isolado como prova de caixa.

## Correções implementadas sem migration

### Honorários e pagamentos
- saldo e KPIs derivados de `fee_payments`, não do valor original do fee;
- recebimento do mês reconhecido pela data real do pagamento;
- bloqueio de pagamento acima do saldo, pagamento em fee cancelado/quitado e redução do valor abaixo do já recebido;
- honorário percentual sem base monetária não é artificialmente quitado;
- formas de pagamento controladas: `pix`, `transferencia`, `dinheiro`, `cartao`, `boleto`, `outro`;
- subledger `GET /fees/{fee_id}/pagamentos` com total recebido e saldo;
- `comprovante_doc_id` aceito no pagamento somente quando o fee pertence a caso e o documento passa pela política canônica de acesso/compatibilidade;
- tela de Honorários ganhou histórico de pagamentos e sugestão do saldo residual na próxima baixa.

### Despesas
- schemas Pydantic estritos, valores positivos, status/tipo/competência controlados;
- auditoria de criação/edição/remoção e soft delete;
- coerência backend `status=pago` ↔ `pago_em`;
- nova ação explícita **Despesa extra**, reutilizando `office_expenses` como lançamento variável, não recorrente e sem tabela paralela;
- geração recorrente antiga permanece fail-closed enquanto não houver template/idempotência persistida.

### Cobrança e Portal
- régua de cobrança e inadimplência usam saldo residual;
- alertas zerados/resolvidos deixam de permanecer abertos;
- Portal Financeiro mostra contratado, recebido parcial e saldo, sem tratar percentual sem base como valor monetário conhecido.

### Sociedade
- cap table ativo não pode exceder 100%, com serialização transacional;
- retiradas têm segregação de funções e trilha de auditoria;
- criação de retirada exige que o beneficiário esteja em `socios` com `ativo=true`;
- campo fantasma `meta_produtividade` removido do contrato de mutação até existir persistência real;
- módulo societário segregado da navegação financeira operacional.

### PIX/LGPD
- payload PIX validado com Decimal e `extra=forbid`;
- geração não registra chave PIX no AuditLog nem a devolve no payload;
- configuração de chave PIX deixou de usar `localStorage`; fica apenas em `sessionStorage` durante a sessão do navegador.

### Consolidado / demonstrativo
- `GET /financeiro/consolidado` separa saldo a receber e caixa efetivamente recebido;
- `GET /financeiro/demonstrativo` separa competência operacional e fluxo de caixa;
- saída de caixa usa `office_expenses.pago_em`, e não a competência do lançamento;
- demonstrativo é explicitamente `gerencial_nao_contabil` e não se apresenta como DRE fiscal/contábil.

### Fila operacional
- `GET /financeiro/atencao` reúne somente itens que exigem ação: honorários vencidos, despesas vencidas/próximas, pagamentos sem comprovante, percentuais sem base e contratos a vencer;
- resposta agregada não inclui nome de cliente, caso ou descrição sensível.

### Scheduler financeiro
Foi criada a extensão isolada `app/services/scheduler_financeiro.py`, instalada no boot via `event_subscribers`, sem reescrever o scheduler central.

- Morning Brief passa a somar **saldo residual vencido**, e não `fees.valor` bruto;
- honorários percentuais sem base são contados separadamente, sem gerar valor monetário fictício;
- transição automática `pendente -> atrasado` só ocorre quando ainda existe obrigação aberta;
- cada mudança automática grava `audit_logs` na mesma transação da alteração de status;
- auditoria automática não grava nome de cliente, valor ou descrição de caso.

## Fechamento inteligente

Foi implementado `GET /financeiro/fechamento-inteligente?competencia=YYYY-MM` como **pré-fechamento read-only**.

Ele não congela o mês e não grava estado de fechamento porque a persistência imutável depende de migration própria. O objetivo atual é funcionar como gate de integridade antes da decisão humana.

### Status

- `pronto` — nenhuma categoria de bloqueio ou revisão encontrada;
- `revisao` — não há inconsistência estrutural, mas existem pendências que exigem conferência consciente;
- `bloqueado` — foi encontrada inconsistência que deve ser corrigida antes do fechamento.

### Bloqueios

- pagamento total acima do valor monetário contratado;
- fee marcado `pago` ainda com saldo;
- despesa marcada `pago` sem `pago_em`;
- honorário percentual da competência sem base monetária estruturada.

### Itens de revisão

- contas a receber ainda abertas até o fim da competência;
- despesas da competência ainda pendentes;
- recebimentos do mês sem comprovante documental.

### Score de integridade

O score é explicável e não depende do volume de lançamentos:

- inicia em 100;
- cada **categoria de bloqueio presente** reduz 25 pontos;
- cada **categoria de revisão presente** reduz 7 pontos;
- quantidade de linhas aparece no detalhe, mas não multiplica a penalidade.

O dashboard mostra status, score e atalhos para corrigir cada item. Mesmo com score 100, a interface informa que é necessária conferência humana final e que o fechamento imutável ainda não foi habilitado.

## Estimador

- fallback sem fonte não é apresentado como Tabela OAB/MG;
- fonte oficial localizada em 02/09/2026: página institucional da OAB/MG + Tabela de Honorários Advocatícios 2023 homologada em 15/12/2023;
- a tabela prevê reajuste anual por IPCA; nenhum valor 2026 foi inventado/carregado sem série oficial e memória de cálculo.

## Itens que exigem schema/migration e permanecem deliberadamente bloqueados

A migration `156_case_despesas_processuais` está reservada pelo PR #1333, ainda draft/aberto. Pela governança Alembic do EJC, esta branch **não cria 157 em paralelo**.

Após integração/reconciliação da 156, reservar o próximo head linear e implementar em uma migration financeira coesa, com Postgres real, upgrade/downgrade e rollback:

1. `office_expense_templates` + execução idempotente por `template_id + competencia`;
2. estorno imutável de `FeePayment`, com vínculo ao pagamento original, motivo, autor, timestamp e proteção contra duplo estorno;
3. base econômica realizada de honorário de êxito/misto, sem inferir pelo valor da causa;
4. fechamento mensal persistente (`aberta -> conferencia -> fechada`) com snapshot, hash/versão, autor, timestamps e reabertura auditada;
5. ajustes pós-fechamento exclusivamente por lançamentos compensatórios/estorno, nunca edição silenciosa do histórico fechado;
6. conciliação bancária persistente OFX/CSV, com estados `nao_identificado`, `conciliado`, `divergente` e vínculo ao lançamento financeiro;
7. metadados/versionamento da tabela OAB/MG e, se adotado reajuste por IPCA, memória de cálculo com fonte IBGE e vigência.

## Contrato recomendado para o fechamento persistente futuro

Quando a migration linear estiver disponível, o fechamento deve armazenar no mínimo:

- competência única;
- status `aberta`, `conferencia`, `fechada`, `reaberta`;
- snapshot de entradas/saídas/saldos por competência e caixa;
- score e lista de exceções aceitas no momento do fechamento;
- usuário que conferiu e usuário que fechou, quando aplicável;
- `fechado_em`, `reaberto_em` e motivo de reabertura;
- hash/versionamento do snapshot;
- vínculo de ajustes/estornos posteriores sem sobrescrever números históricos.

RBAC recomendado: `financeiro` prepara/concilia; `admin/socio/superadmin` fecha ou reabre. A mesma pessoa não deve aprovar uma exceção relevante criada por ela quando houver alternativa operacional.

## Itens não alterados sem decisão de negócio/jurídica

- rateio de êxito 50% titular / 50% escritório permanece como regra atual; não foi presumida nova participação;
- honorário `valor + percentual` continua registrado como composição contratual, mas a base do percentual precisa ser informada antes de quitação/rateio;
- nenhum percentual societário real foi inferido de usuário, cargo ou papel.

## Testes adicionados

`backend/tests/test_financeiro_integridade_20260902.py` cobre, entre outros:
- valor negativo/extra field em Fee;
- pagamento > 0 e forma controlada;
- despesa positiva/status/competência;
- normalização da baixa de despesa;
- contrato com vigência/valor inválidos;
- retirada inválida;
- PIX e BR Code;
- classificação `pronto/revisao/bloqueado` do fechamento inteligente;
- score por categoria, sem penalizar volume;
- instalação isolada dos callbacks financeiros do scheduler;
- fila de atenção sem PII.

## Gates antes de merge

- [ ] Backend inicia sem erro
- [ ] Testes financeiros focados verdes
- [ ] Suíte backend afetada verde
- [ ] Frontend typecheck verde
- [ ] Frontend Vitest verde
- [ ] Frontend build verde
- [ ] RBAC negativo validado
- [ ] Logs sem dados sensíveis
- [ ] Main/head reconciliados
- [ ] Alembic permanece single-head e sem migration desta branch
- [ ] Revisão/CI do SHA final concluída

## Estado de encerramento técnico

A frente sem migration está **funcionalmente consolidada na branch**, mas não deve ser considerada publicada enquanto o PR não passar pelos gates do SHA final e não for integrado à `main`.

O fechamento inteligente atual é um gate gerencial real e executável, mas não é o fechamento contábil nem o lock imutável do período. A persistência definitiva fica bloqueada pela sequência Alembic e não deve ser simulada em campo genérico, `observacoes` ou AuditLog.

## Rollback

A branch não contém migration. Rollback é reversão dos commits/PR. Nenhuma transformação ou exclusão de dados de produção foi executada.