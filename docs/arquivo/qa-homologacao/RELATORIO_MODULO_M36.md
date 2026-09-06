# Relatório de Homologação — M36: Timesheet e Produtividade

**Data:** 16/08/2026
**Repositório:** s2corporativo/ejc — branch `homologacao-m07-2026-08-16`
**Bateria:** `scripts/inventory/m36_timesheet_tests.py` (23 cenários, 4 seções)
**Resultado final:** **23 PASS, 0 FAIL, 0 N/A-PROVADO**
**Status do módulo:** **HOMOLOGADO**

## 1. Itens do PROMPT 36 e comprovações

| Item | Endpoint(s) | Comprovação |
|---|---|---|
| Lançamentos | `POST /api/timesheet/` | 90min faturável + 45min não faturável, vinculados ao caso |
| Duração | `minutos` 1–1440 | Zero → 422; 1441 → 422; cálculo correto: 2.25h totais |
| Início/fim | — | **Escopo divergente documentado:** o modelo armazena `data + minutos` por lançamento, sem intervalo início/fim por registro. Não é defeito; é uma escolha de modelagem (não existe `total_duration`) |
| Advogado | `verificar_acesso_caso` | Advogado fora da carteira → 403 em lançamento e edição |
| Cliente | — | `cliente_externo` bloqueado no timesheet do processo (403/404) |
| Processo | `GET /api/timesheet/casos/{id}` | Relatório por caso: 2 lançamentos, total 2.25h, a faturar 1.50h |
| Faturável | `faturavel` | Lançamento não faturável excluído das horas a faturar; após faturamento, nova tentativa → 422 |
| Faturamento | `POST /caso/{id}/faturar` | 1.50h × R$ 250,00 = R$ 375,00 → Fee `por_hora` gerado (`fee_id`, `lancamentos: 1`) |
| Relatórios | `/casos/{id}` | Duração total e horas a faturar corretas vs. banco |
| Produtividade | `/api/analytics/produtividade?periodo=` | 7d/30d/90d/365d: por_advogado (horas, horas faturáveis, %, lançamentos, casos), por_area e trend diário |
| Edição/exclusão | `DELETE /{id}` | Exclusão 200; advogado fora da carteira bloqueado |
| Permissões | `_req_fat`, `_req_gestao` | Estagiário bloqueado no faturamento; advogado e cliente_externo bloqueados na produtividade (sócio+) |

## 2. Observações

Sem bugs encontrados; nenhum código do sistema foi alterado neste módulo. Ajustes foram aplicados somente à bateria (papéis de teste executam o fluxo com o sócio, pois o advogado QA não é o responsável pelo caso QA — comportamento correto de carteira, comprovado nos testes de 403).

## 3. Checklist

- [x] Backend inicia sem erro
- [x] Bateria completa: 23 PASS, 0 FAIL
- [x] Faturamento integrado: timesheet → Fee `por_hora` (R$ 375,00 exato)
- [x] Produtividade com 4 janelas e dados reais gerados
- [x] Autorização validada (estagiário, advogado, socio, cliente_externo)
- [x] Sem alteração de código do sistema; sem migração

## 4. Resultado

**M36 — HOMOLOGADO** (23/23 cenários comprovados; divergência de escopo início/fim documentada como modelagem, não defeito).
