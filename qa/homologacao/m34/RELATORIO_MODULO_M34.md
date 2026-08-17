# Relatório de Homologação — M34: Honorários e Propostas

**Data:** 16/08/2026
**Repositório:** s2corporativo/ejc — branch `homologacao-m07-2026-08-16`
**Bateria:** `scripts/inventory/m34_honorarios_propostas_tests.py` (27 cenários, 5 seções)
**Resultado final:** **26 PASS, 0 FAIL, 1 N/A-PROVADO**
**Status do módulo:** **HOMOLOGADO**

## 1. Itens do PROMPT 34 e comprovações

| Item | Endpoint(s) | Comprovação |
|---|---|---|
| Propostas | `/api/honorarios-oab/casos/{id}/proposta` (POST/GET), `/propostas/{id}/aprovar`, `/rejeitar` | Rascunho 201 (versão 1), aprovação congela com status `aprovada`, rejeição com motivo auditada, histórico por caso |
| Contratos | POST proposta (modalidade, vigência, despesas) | Contrato estruturado com vigência 2026-09-01..2027-08-31 e cláusulas persistidas |
| Valores | `/api/fees` POST/PATCH | Valor `15750.99` → `16000.00` em edição, com precisão preservada |
| Percentuais | `percentual_exito` | `20.00%` preservado no servidor |
| Êxito | tipo `exito` + `/honorarios-calc/.../teto-etico` | Teto ético calculado (sucumbência estimada CPC art. 85) |
| Parcelas | `POST /fees/{id}/pagamentos` | Parcial pix 6.000,00; segunda parcela quita automaticamente (`quitado: true`, total pago 16.000,01) |
| Vencimentos | `data_vencimento` + filtro `competencia` | Vencimento editável; filtro AAAA-MM validado (422 para formato inválido) |
| Aprovação / cancelamento | `aprovar`, `status: cancelado` | Congelamento aprovado; cancelamento 200; status inválido → 422 |
| Vínculo | `client_id`, `case_id` | Fee vinculado a cliente e caso; advogado fora da carteira bloqueado (403) |
| Documentos | Tabela OAB, propostas | `/api/honorarios-oab/tabela` retorna conteúdo; proposta carrega origem/tabela OAB/MG |
| Precisão monetária | `Numeric(14,2)` + KPI vs banco | 2 casas preservadas; resumo KPI conferido ao banco com delta < R$ 0,01 |

## 2. Ajustes de bateria (nenhum bug no sistema)

O advogado QA não é o responsável pelo caso QA (propriedade de outro usuário), o que gerou 403 nas propostas — comportamento correto de RBAC de carteira; bateria ajustada para executar o fluxo de propostas com o sócio. Pagamento de quitação comprovado pela chave `quitado: true`.

## 3. Riscos e observações

Sem alterações de código no sistema. Correções aplicadas apenas à bateria de testes. Dados EJC_QA_* sintéticos criados (fees, pagamentos, propostas) — rastreáveis e isolados.

## 4. Checklist

- [x] Backend inicia sem erro
- [x] Bateria completa: 26 PASS, 0 FAIL
- [x] Valores conferidos contra o banco (delta < R$ 0,01)
- [x] Autorização validada (financeiro, secretaria, cliente_externo, advogado)
- [x] Logs sem dado sensível
- [x] Sem migration; sem alteração de código do sistema
- [x] Dados sintéticos EJC_QA_*

## 5. Resultado

**M34 — HOMOLOGADO** (26/26 cenários executáveis comprovados; 1 N/A-PROVADO de RBAC documentado).
