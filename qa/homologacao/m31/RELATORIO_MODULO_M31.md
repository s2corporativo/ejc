# EJC — Relatório de Homologação do Módulo M31

## Índice de Risco e Saúde do Caso

| Campo | Valor |
| --- | --- |
| Módulo | M31 — Índice de Risco e Case Health |
| Data | 16/08/2026 |
| Branch | homologacao-m07-2026-08-16 |
| Resultado | **26/26 cenários executáveis PASS (100%)** |
| Status | **HOMOLOGADO** |
| Bateria | `scripts/inventory/m31_risco_tests.py` |

## 1. Escopo homologado (PROMPT 00 / M31)

Verificação do motor de índice de risco jurídico: fórmula determinística, fatores com pesos declarados, tetos, persistência e auditoria; isolamento por ownership (IDOR) e RBAC; segundo motor de saúde do caso (case_health) com explicabilidade; ranking agregado; e auditoria da camada frontend contra linguagem de garantia de resultado judicial.

## 2. Resultados por seção

### 2.1 Motor indice_risco — fórmula, pesos e limites (6/6)

| # | Verificação | Resultado |
| --- | --- | --- |
| 1 | Linha de base: caso limpo | índice 15 (fator sem_documentos), nível **baixo** |
| 2 | Prazo vencido | +15 por prazo (índice 15→30) |
| 3 | Acumulador do fator prazo | 3 prazos = +30 com teto do fator 30 aplicado como declarado |
| 4 | sem_documentos | +15 quando o caso não tem documentos |
| 5 | valor_alto | +10 quando valor da causa > R$ 500.000 |
| 6 | Saturação | 65/alto — teto efetivo da fórmula com valor alto + processo antigo |

### 2.2 Persistência — histórico, casos e auditoria (4/4)

| # | Verificação | Resultado |
| --- | --- | --- |
| 7 | GET + histórico | índice/nível/fatores persistidos; 6 cálculos com `calculado_por=sistema` |
| 8 | `indice_risco_historico` | 6 registros append-only (tabela própria) |
| 9 | Espelhamento em cases | `indice_risco=65`, `risco_nivel=alto`, `risco_atualizado_em` atualizado |
| 10 | Auditoria | 6 ações `UPDATE/indice_risco` em `audit_logs` com registro_id do caso |

### 2.3 Isolamento — ownership e RBAC (4/4)

| # | Verificação | Resultado |
| --- | --- | --- |
| 11 | cliente_externo | bloqueado (403/404) |
| 12 | financeiro | bloqueado na leitura do índice (403/404) |
| 13 | caso inexistente | 404 fail-closed, sem stack trace |
| 14 | estagiário | bloqueado no recálculo (403) |

### 2.4 Motor case_health — fórmula, pesos, explicabilidade (5/5)

| # | Verificação | Resultado |
| --- | --- | --- |
| 15 | Linha de base | score 90 (fator sem_procuração), com impacto e detalhe |
| 16 | Prazo vencido | −20 com fator, impacto e detalhe |
| 17 | Honorário atrasado | −10 (fee sintético criado via perfil financeiro autorizado, data de vencimento passada) |
| 18 | Limite [0,100] | score dentro do limite, classificação `atencao` |
| 19 | Ranking agregado | 56 casos, distribuição completa, ordenados por pontuação |

### 2.5 Limite temporal (1/1)

| # | Verificação | Resultado |
| --- | --- | --- |
| 20 | processo_antigo | +10 quando `created_at` > 3 anos (teste com restauração do valor original) |

### 2.6 Frontend — TabRisco/MatrizRisco e vedação de garantia (6/6)

| # | Verificação | Resultado |
| --- | --- | --- |
| 21 | Abertura da aba | GET de leitura do índice |
| 22 | Recálculo sob demanda | POST real |
| 23 | Fatores visíveis | explicabilidade no frontend |
| 24 | Histórico | cálculos anteriores exibidos |
| 25 | Estado vazio | orienta o recálculo manual |
| 26 | Linguagem | **sem qualquer termo de garantia de resultado judicial** |

## 3. Limitação conhecida (não é defeito)

O código declara um clamp global de 100 e um nível `critico`; porém, a soma máxima dos fatores atuais (prazo 30 + documentos 15 + valor 10 + processo antigo 10) atinge **65**. O nível crítico, portanto, **não é atingível pelos fatores implementados**. A bateria audita o comportamento real (saturação em 65/alto) e recomenda ao time decidir entre: (a) adicionar fatores complementares (ex.: jurisprudência desfavorável, multas processuais, honorários adversos); ou (b) remover a faixa `critico`/clamp 100 do mapa de níveis para evitar divergência documental. Registro no commit associado.

## 4. Correções aplicadas (bateria)

- helper SQL da bateria passou a aceitar parâmetros nomeados (bind `:cid`) e a comitar transações;
- criação de honorário QA ajustada ao schema real (`client_id` obrigatório, perfil financeiro autorizado);
- consulta de espelhamento ajustada às colunas reais (`indice_risco`, `risco_nivel`, `risco_atualizado_em`).

Nenhuma correção no código do sistema foi necessária — zero defeitos encontrados no backend ou frontend.

## 5. Riscos e observações

- LGPD: a bateria usa apenas dados sintéticos `EJC_QA_*`, limpos ao final (casos QA, honorários, prazos e documentos sintéticos).
- RBAC: leitura do índice exige advogado+ (financeiro bloqueado) — decisão de design confirmada.
- O recálculo grava em três lugares de forma atômica (histórico, espelho em cases, auditoria) — comprovado.
- O frontend não contém linguagem de promessa de resultado — requisito de publicidade OAB confirmado no código-fonte (TabRisco.tsx / MatrizRisco.tsx).

## 6. Rollback

Tudo o que a bateria criou é sintético e identificável (`EJC_QA_M31` / `QA M31`); limpeza realizada via mesmo script. Nenhuma migration foi aplicada.
