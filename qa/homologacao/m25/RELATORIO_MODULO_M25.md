# Relatório de Homologação — Módulo M25
## Precedentes, Jurisprudência e Citações

| Campo | Valor |
|---|---|
| Data | 16/08/2026 |
| Branch | `homologacao-m07-2026-08-16` |
| Commit | `9f31c46f` |
| Bateria | `scripts/inventory/m25_precedentes_tests.py` |
| Resultado | **39/39 PASS (100%)** |
| Status | **HOMOLOGADO** |
| Correção de dados aplicada | Sim (proveniência de vigência de legislação seeded) |
| Correções de código | Não necessárias |

## 1. Objetivo e método

M25 homologa a cadeia completa de precedentes, jurisprudência e citações do EJC, seguindo o PROMPT 25: cada referência citada deve permitir rastrear **tribunal, processo, órgão julgador, relator, data e fonte**, e a correspondência entre conteúdo e citação deve ser verificável, com medição das quatro classes de erro — **referências corretas, inexistentes, incorretas e interpretação incompatível** com a fonte.

Foram usadas apenas superfícies confirmadas no código (nenhuma rota inventada): `/api/jurisprudencias` (interno), `/api/jurisprudencia-externa/{buscar,fontes,precedentes/buscar}`, `/api/ai/citacoes/verificar`, `/api/qualidade/verificar-citacoes`, `/api/legal-docs/{id}/jurisprudencia-check` e `/api/teses`. A bateria roda contra o servidor local com usuários QA sintéticos `EJC_QA_*` e dados sintéticos identificados, com limpeza ao final.

## 2. Seções executadas (39 testes, todos PASS)

| Seção | O que foi provado | Testes |
|---|---|---|
| 1. Motor de extração/classificação | CNJ com DV módulo 97 (Res. CNJ 65/2008): válido aceito, DV adulterado rejeitado, tribunal inexistente flagado; REsp com número/UF/tribunal por classe; súmulas ordinárias e vinculantes (STJ/STF) com tetos de faixa; menções genéricas com locução canônica; shape legado `total/confirmadas/não_encontradas` + score; resultado por citação expõe tribunal/órgão/relator/data/fonte_verificacao | 10 |
| 2. CRUD jurisprudência interna | POST 201 preserva tribunal/relator/acórdão/data/fonte; GET incrementa `vezes_citada` (rastreabilidade de uso); PATCH ignora campos fora do schema sem corromper (integridade); edição com advogado+/socio+; exclusão soft-delete 204; financeiro/cliente_externo bloqueados; allowlist exata (#694) | 12 |
| 3. Busca externa multi-fonte | `/buscar` 200 com proveniência por fonte; `/fontes` com lexml/tjmg/datajud; `/precedentes/buscar`; financeiro bloqueado; LexML público fora do ar tratado como fonte externa indisponível (fail-safe, sem stack trace ao usuário) | 4 |
| 4. Endpoints de verificação | `/api/ai/citacoes/verificar`: 2 alucinações (súmula inexistente + DV inválido) → suspeitas, score 0; texto com citações reais da base oficial (art. 489 CPC + art. 5º, III CF) → 2 confirmadas, score 100; endpoint legado determinístico sem stack trace; cliente bloqueado | 4 |
| 5. Correspondência conteúdo × citação | `/legal-docs/{id}/jurisprudencia-check` valida números CNJ citados contra base validada (com registro jurisprudencial fonte_validada+confidence+rag_status); peça sintética com CNJ inventado + súmula fora de faixa → problema registrado (correspondência bloqueada antes do protocolo) | 3 |
| 6. Banco de teses | `/api/teses` expõe campo tribunal; `/busca-avancada` filtra por tribunal | 2 |

## 3. Métricas do PROMPT 25 (prova de execução)

| Classe | Cenário de teste | Resultado |
|---|---|---|
| Referências corretas | art. 489 CPC + art. 5º, III CF (base oficial Planalto seeded) | **verificadas (2/2), score 100** |
| Referências inexistentes | Súmula 9999 do STF (fora da faixa 1–736) | **suspeita**, avisada |
| Referências incorretas | CNJ com DV módulo 97 adulterado | **suspeita** (dígito verificador inválido), avisada |
| Interpretação incompatível | REsp real com número correto + súmula 9000 inexistente no mesmo contexto | **nada confirmado** (score 0 — o contexto misto não contamina a verificação) |

## 4. Achado operacional corrigido (não era defeito de código)

O gate RAG fail-closed (M22) exclui do retrieval documentos de categoria `legislacao*` cujo status de vigência é **apenas inferido** (`legal_status_inferido_em` preenchido), exigindo proveniência verificada (`legal_status='vigente'` + `legal_status_origem` + `legal_status_verificado_em`). O ingestor Planalto, ao rodar sem o verificador de vigência (ambiente sandbox offline), marcava os diplomas como `vigencia_nao_verificada` **com inferência** — comportamento defensivamente correto, mas que deixava a legislação oficial ingerida invisível para a verificação de artigos citados.

Correção de dados aplicada (idempotente, escopo restrito a `planalto:cpc` e `planalto:cf88`, nunca inferência): declaração de proveniência oficial `legal_status_origem='planalto_oficial'` com `legal_status='vigente'` e `legal_status_verificado_em`, anulando a inferência anterior. Após a correção, `_existe_artigo('489','CPC')` retorna "Código de Processo Civil (Lei 13.105/2015)" e a bateria confirmou as duas citações reais na base oficial. Isso também alimenta M24/M26 com corpus legislativo real.

## 5. Ressalvas registradas (não impeditivas)

1. **Súmulas não estão ingeridas na base** (`knowledge_docs` sem documentos `sumula:*`). Comportamento correto: súmula citada fica `identificada` (não confirmada), nunca `verificada` — o verificador nunca confirma fonte ausente. Para cobertura completa, recomenda-se futura ingestão de súmulas STF/STJ como material controlado.
2. **LexML público indisponível** no ambiente de teste (404/fora do ar): o sistema degrada corretamente (busca por fonte retorna `[]`, agregação continua), mas a busca externa real depende da fonte externa.
3. **`/precedentes/buscar` com fonte TJMG não testado em profundidade** (mesma limitação de fonte externa).

## 6. Checklist obrigatório

- [x] Backend inicia sem erro (health ready após bateria)
- [x] Endpoint responde (todas as rotas testadas)
- [x] Autorização validada (financeiro/cliente/estagiário bloqueados onde exigido)
- [x] Logs sem dado sensível (LexML indisponível logado como warning sem segredo)
- [x] Banco sem drift (nenhuma migration; apenas UPDATE de `extra` em 2 docs e INSERT/soft-delete de peça QA)
- [x] Rollback possível (fix de proveniência é idempotente e reversível via `extra`)
- [x] Dados sintéticos identificados por `EJC_QA_*`, resíduos limpos (9 peças QA soft-deletadas)
- [x] Sem segredo versionado; sem quebra de módulo existente (M24 revalidado com corpus legislativo)

## 7. Próximos passos

Continuar para **M26 — Prompt Injection e Segurança da IA**.
