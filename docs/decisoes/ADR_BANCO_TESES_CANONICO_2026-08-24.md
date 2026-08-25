# ADR — Banco Nacional de Teses Jurídicas: fonte canônica

**Status:** Decidido  
**Data da decisão original:** 24/08/2026  
**Reconciliação com a `main`:** 25/08/2026

## Contexto

Uma implementação paralela tentou criar um novo universo de teses (`teses_juridicas`, taxonomias, precedentes e estruturas próprias) apesar de o EJC já possuir o Banco de Teses institucional em `teses` + `tese_caso_links`.

Essa duplicação repetia um problema histórico já corrigido pela migration 114, que consolidou `teses_juridicas_v4` de volta na estrutura canônica.

O domínio atual já é consumido por Jurimetria, Súmulas, matcher tese↔caso, impacto regulatório, Matriz de Teses, aprendizado de encerramento e frontend. Trocar a fonte de verdade exigiria reescrever módulos funcionais e criaria risco jurídico e operacional sem benefício.

## Decisão

1. **A única fonte de verdade é `teses` + `tese_caso_links`.**
2. Não criar `legal_theses`, `teses_juridicas`, `teses_v2`, `teses_v4` ou outra tabela/router que concorra como banco principal.
3. Extensões do domínio devem ser aditivas: novas colunas ou tabelas satélite vinculadas à `teses` canônica.
4. O enum e os contratos atuais usados por Súmulas/Jurimetria não podem ser alterados por conveniência de uma implementação nova.
5. Evidência jurídica, contratese/distinguishing, validação, radar e embeddings devem se conectar ao Banco existente, nunca substituí-lo.
6. Importação automática nunca promove uma tese diretamente a estado juridicamente confiável; promoção exige fonte rastreável e revisão humana nos pontos previstos pela governança.
7. Toda nova migration parte do head real da `main` e precisa constar em `MIGRATION_RESERVATIONS.md`.

## Situação da série antiga

Os PRs #1264, #1267, #1269 e #1275 nasceram empilhados quando o head era 147/148. Enquanto estavam abertos, a `main` avançou para 149, 150, 151 e 152. Portanto essa série não pode mais ser integrada como foi escrita.

A migration `148_banco_teses_juridicas` nunca integrou a `main` e está **aposentada**. Qualquer extensão ainda desejada deve ser reconstruída a partir de `152_thesis_candidate_tese_banco`, usando o próximo prefixo válido e aplicando somente o delta que ainda não exista na `main`.

## Consequências

- nenhuma terceira fonte de verdade;
- nenhum fork Alembic para salvar branch antiga;
- requisitos úteis dos PRs históricos podem ser reaproveitados, mas somente por reimplementação sobre a `main` atual;
- o ledger passa a ter teste automático que compara o head documentado com o head real do Alembic;
- tabelas v4 preservadas apenas por compatibilidade histórica continuam sem receber novas gravações e só podem ser removidas em operação separada com telemetria, backup e rollback.
