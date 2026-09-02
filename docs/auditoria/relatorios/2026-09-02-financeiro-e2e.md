# Auditoria E2E — Financeiro/Fiscal — 02/09/2026

## Escopo

Auditoria e hardening do domínio financeiro do EJC sobre branch dedicada `audit/financeiro-e2e-20260902`, sem deploy de produção e sem migration concorrente.

Domínios cobertos: honorários, pagamentos, cobrança/inadimplência, despesas do escritório, despesas extras manuais, consolidado financeiro, contratos, sociedade/cap table, retiradas, PIX, Portal Financeiro e estimador.

## Correções implementadas sem migration

### Honorários e pagamentos
- saldo e KPIs derivados de `fee_payments`, não do valor original do fee;
- recebimento do mês reconhecido pela data real do pagamento;
- bloqueio de pagamento acima do saldo, pagamento em fee cancelado/quitado e redução do valor abaixo do já recebido;
- honorário percentual sem base monetária não é artificialmente quitado;
- formas de pagamento controladas: `pix`, `transferencia`, `dinheiro`, `cartao`, `boleto`, `outro`;
- subledger `GET /fees/{fee_id}/pagamentos` com total recebido e saldo;
- `comprovante_doc_id` aceito no pagamento somente quando o fee pertence a caso e o documento passa pela política canônica de acesso/compatibilidade;
- tela de Honorários ganhou histórico de pagamentos.

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
- campo fantasma `meta_produtividade` removido do contrato de mutação até existir persistência real.

### PIX/LGPD
- payload PIX validado com Decimal e `extra=forbid`;
- geração não registra chave PIX no AuditLog nem a devolve no payload;
- configuração de chave PIX deixou de usar `localStorage`; fica apenas em `sessionStorage` durante a sessão do navegador.

### Consolidado / demonstrativo
- `GET /financeiro/consolidado` separa saldo a receber e caixa efetivamente recebido;
- `GET /financeiro/demonstrativo` separa competência operacional e fluxo de caixa;
- demonstrativo é explicitamente `gerencial_nao_contabil` e não se apresenta como DRE fiscal/contábil.

### Estimador
- fallback sem fonte não é apresentado como Tabela OAB/MG;
- fonte oficial localizada em 02/09/2026: página institucional da OAB/MG + Tabela de Honorários Advocatícios 2023 homologada em 15/12/2023;
- a tabela prevê reajuste anual por IPCA; nenhum valor 2026 foi inventado/carregado sem série oficial e memória de cálculo.

## Itens que exigem schema/migration e permanecem deliberadamente bloqueados

A migration `156_case_despesas_processuais` está reservada pelo PR #1333, ainda draft/aberto. Pela governança Alembic do EJC, esta branch **não cria 157 em paralelo**.

Após integração/reconciliação da 156, reservar o próximo head linear e implementar em uma migration financeira coesa, com Postgres real, upgrade/downgrade e rollback:

1. `office_expense_templates` + execução idempotente por `template_id + competencia`;
2. estorno imutável de `FeePayment`, com vínculo ao pagamento original, motivo, autor, timestamp e proteção contra duplo estorno;
3. base econômica realizada de honorário de êxito/misto, sem inferir pelo valor da causa;
4. fechamento mensal (`aberta -> conferencia -> fechada`) e ajustes pós-fechamento por lançamentos compensatórios;
5. conciliação bancária persistente OFX/CSV, com estados `nao_identificado`, `conciliado`, `divergente` e vínculo ao lançamento financeiro;
6. metadados/versionamento da tabela OAB/MG e, se adotado reajuste por IPCA, memória de cálculo com fonte IBGE e vigência.

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
- PIX e BR Code.

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
- [ ] Revisão do PR concluída

## Rollback

A branch não contém migration. Rollback é reversão dos commits/PR. Nenhuma transformação ou exclusão de dados de produção foi executada.