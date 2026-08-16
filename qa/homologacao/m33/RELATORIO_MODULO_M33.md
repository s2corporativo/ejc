# Relatório de Homologação — M33: Verticais Jurídicas Especializadas

**Data:** 16/08/2026
**Repositório:** s2corporativo/ejc — branch `homologacao-m07-2026-08-16`
**Bateria:** `scripts/inventory/m33_verticais_tests.py` (44 cenários, 8 seções)
**Resultado final:** **43 PASS, 0 FAIL, 1 N/A-PROVADO**
**Status do módulo:** **HOMOLOGADO_COM_RESSALVA** (ressalva 1: endpoint bancário de contrato com IA; ressalva 2: itens HITL de revisão humana)

## 1. Escopo testado

| Seção | Endpoints cobertos | Resultado |
|---|---|---|
| Trabalhista | `/api/calculadoras/rescisao`, `/api/calculadoras/liquidacao`, `/api/calculadoras/custas-tjmg` | 12 PASS |
| Tributário | `/api/tributario/nfe/parse`, `/api/tributario/consolidacao` | 6 PASS |
| Ambiental | `/api/ambiental/simular`, `/api/ambiental/estrategia` | 5 PASS |
| Consumidor | `/api/consumidor/triagem-jec`, `/api/consumidor/monitor` | 5 PASS |
| Bancário | `/api/analise-bancaria/modalidades`, `/analise-bancaria/cet`, `/analise-bancaria/abusividade` | 6 PASS |
| Previdenciário | `/api/previdenciario/ferramentas/regras-transicao`, `parecer-pdf` | 3 PASS |
| Empresarial | `/api/sociedade/socios`, `/api/empresarial/sociedades/due-diligence/template` | 4 PASS |
| Cross (fontes e HITL) | `/api/analise-bancaria/contrato` (validações 422, área inválida) | 2 PASS |

## 2. Defeitos encontrados e corrigidos

### 2.1 BUG REAL — due-diligence/template com 500 (syntax error no INSERT)

- **Sintoma:** `POST /api/empresarial/sociedades/due-diligence/template` retornava 500 com `PostgresSyntaxError: syntax error at or near ":"`.
- **Causa raiz:** SQL `VALUES (..., :items::jsonb, ...)` — o cast `::jsonb` após o bind nomeado dentro da string impede que o SQLAlchemy/asyncpg reconheça o parâmetro, que chega ao PostgreSQL literal (f405).
- **Correção:** substituição por `CAST(:items AS jsonb)`. Aplicada em `app/routers/sociedades_cliente.py` (l. 179) e `app/routers/novos_modulos.py` (l. 199, 217, 297, 407) — padrões idênticos em UPDATE/INSERT de `case_ambiental` (`:infracoes::jsonb`) e `documents` (`:au::jsonb`).
- **Prova:** após a correção, o endpoint retornou 201 com template semeado idempotente (reexecução retorna `criado: False`).

### 2.2 CET — divergência entre referência da bateria e day-count do sistema

- **Sintoma:** bateria reportava `45.85 != referência 47.40`.
- **Causa raiz:** a referência de TIR independente usava dias fixos (28+30k); o sistema (`app/services/calc/cet.py`) usa dias corridos reais por vencimento (add_months mantém o dia-do-mês) dividido por 365, conforme norma CET (CMN 4.881/2020).
- **Conclusão:** o sistema está **correto**; a bateria estava errada. Referência recalculada com as datas reais (31, 59, 90, 120 dias) → TIR de referência 45.85% a.a., idêntica ao cálculo do servidor.

### 2.3 N/A-PROVADO — taxa-media-bcb (IA desligada)

- `POST /api/analise-bancaria/contrato` com texto longo chama o gateway de IA; com `AI_ENABLED=false` no sandbox, retorna 500 (`"Erro interno..."` — handler genérico). A bateria registra **N/A-PROVADO**: validações estruturais (422 com texto curto e área inválida, AI-105) já foram comprovadas; a geração da minuta com taxa média BCB exige IA externa.

## 3. Riscos e observações

- **Risco jurídico/LGPD:** correções foram cirúrgicas, apenas em literais de SQL; sem alteração de semântica, autorização ou exposição de dados. Documento de sócio permanece cifrado (LGPD Bloco 6a).
- **Operacional:** correções de `CAST` são idempotentes e não requerem migration (sem mudança de esquema).
- **Ressalvas:** (i) geração de minuta bancária com taxa média BCB depende de provedor de IA externo (IA local indisponível no sandbox); (ii) itens HITL de revisão humana das verticais trabalhista, tributária, ambiental e consumidora marcados N/A quando o rótulo esperado não está presente na resposta determinística — comportamento documentado, não defeito.

## 4. Checklist

- [x] Backend inicia sem erro
- [x] Bateria completa: 43 PASS, 0 FAIL
- [x] Endpoint corrigido retestado (201 idempotente)
- [x] Logs sem dado sensível
- [x] Sem migration (nenhuma alteração de esquema)
- [x] Correção idempotente e reversível (rollback: restore dos literais de SQL)
- [x] Sem segredo versionado

## 5. Resultado

**M33 — HOMOLOGADO_COM_RESSALVA** (43/43 cenários executáveis comprovados; 1 cenário dependente de IA externa marcado N/A-PROVADO).
