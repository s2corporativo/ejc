# Relatório de Homologação — M35: Financeiro

**Data:** 16/08/2026
**Repositório:** s2corporativo/ejc — branch `homologacao-m07-2026-08-16`
**Bateria:** `scripts/inventory/m35_financeiro_tests.py` (18 cenários, 5 seções)
**Resultado final:** **18 PASS, 0 FAIL, 0 N/A-PROVADO**
**Status do módulo:** **HOMOLOGADO**

## 1. Bug real encontrado e corrigido

| Item | Evidência | Causa raiz | Correção |
|---|---|---|---|
| `PATCH /api/despesas/{id}` → 500 | DataError asyncpg `'str' object has no attribute 'toordinal'` ao marcar despesa como paga | `update_despesa` passava string ISO para coluna `date` sem conversão (o POST usava `NULLIF(...)::date` no SQL; o PATCH não) | `app/routers/despesas.py`: conversão para `date.fromisoformat()` + validação 422 de formato + string vazia → `None` |

## 2. Itens comprovados

| Item | Comprovação |
|---|---|
| Receitas | Honorários criados e persistidos; `Numeric(14,2)` preservada |
| Despesas | POST 201 (recorrente mensal), edição de pagamento, categoria vazia/valor zero → 422 |
| Contas / centro de custos | `pago_em` registrado em 2026-08-15 vincula pagamento à competência |
| Pagamentos | Parcela paga via `status=pago` + `pago_em` |
| Recorrências | `recorrente=true`, `recorrencia=mensal` persistidos |
| Honorários | Já homologados em M34; reutilizados na inadimplência |
| Inadimplência | Honorário com vencimento passado criado; pendente total R$ 36.501,50 no banco |
| Relatórios | Mensal (pendentes 9 vs 9 no banco, delta zero), consolidado (caixa -901,50, margem), cliente (extrato unificado) |
| Totais | Relatório mensal ≈ banco com delta zero (qtd e R$) |
| Filtros | Competência, categoria, status, recorrente — todos respondem 200 |
| Permissões | Estagiário bloqueado em `/despesas` e consolidado; advogado bloqueado no relatório mensal |
| Auditoria | `/api/audit` (admin/socio) registra lançamentos financeiros (entidade `despesas`/`fees`) |

## 3. Riscos e observações

LGPD: o relatório financeiro por cliente expõe `cpf_cnpj` via `documento_plain` (decifração controlada, migration 112 — não existe coluna em claro). Comportamento documentado e esperado (perfil advogado/financeiro com acesso à carteira). Dados sintéticos `EJC_QA_*` criados (despesas, honorário de inadimplência).

## 4. Checklist

- [x] Backend inicia sem erro
- [x] Bateria completa: 18 PASS, 0 FAIL
- [x] Relatório conferido contra o banco (delta zero)
- [x] Bug corrigido com reteste 18/18
- [x] Autorização validada (estagiário, advogado, financeiro)
- [x] Sem dado sensível em log; sem segredo versionado

## 5. Resultado

**M35 — HOMOLOGADO** (18/18 cenários comprovados; bug de atualização de despesa corrigido e retestado).
