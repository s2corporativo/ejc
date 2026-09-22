# Migração de contratos e rotas de IA

## Contrato canônico

O contrato canônico de inteligência jurídica é `case_intelligence.v1`. A Entrada Única (`/entrada/analisar`) e o processamento documental (`/entrada-universal/processar`) retornam esse envelope no campo `inteligencia_juridica`. Os campos legados continuam presentes durante a migração.

Cada resposta canônica também recebe:

- `X-Contract-Version: case_intelligence.v1`;
- `X-Contract-Adapter: case_intelligence.v1` para portas canônicas;
- `contract_version` no corpo quando a resposta é persistida.

## Adaptadores legados

`/ai/analisar-caso` e `/ai/resumir-documento` continuam funcionando, mas são adaptadores para consumidores antigos. Eles retornam `X-Contract-Adapter: legacy-adapter`, `Deprecation: true` e um link para esta documentação. O corpo permanece compatível e também carrega `contract_version`.

A depreciação não significa remoção imediata. A remoção somente pode ocorrer após telemetria sem chamadas, migração dos consumidores, comunicação e uma janela de rollback.

## Matriz de migração

| Porta | Papel atual | Destino | Estado |
|---|---|---|---|
| `/entrada/analisar` | Entrada de relato, arquivos e dossiê de caso | Contrato canônico | Canônica |
| `/entrada-universal/processar` | OCR, classificação e análise documental | Contrato canônico | Canônica |
| `/ai/analisar-caso` | Compatibilidade de análise textual | Adaptador para o núcleo | Depreciada |
| `/ai/resumir-documento` | Compatibilidade de resumo | Adaptador para o núcleo | Depreciada |
| `/ia/analisar` | Porta por capacidade | Envelope canônico de IA | Canônica para capacidades |

## Regras de remoção

Uma rota depreciada não deve ser removida somente por busca estática. Antes da remoção, confirme: zero chamadas na telemetria por pelo menos um ciclo operacional; nenhum consumidor frontend; nenhum job, webhook ou integração; testes migrados; documentação atualizada; rollback disponível; e revisão técnica registrada.

Não remover nem renomear snapshots antigos. A evolução do caso é append-only e os snapshots anteriores permanecem como evidência histórica. Reprocessamento deve criar uma nova versão e exigir aprovação humana.

## Teste de contrato mínimo

A homologação deve cobrir relato, PDF digital, PDF com OCR, DOCX, lote, contradições, documento com tentativa de prompt injection, caso multidisciplinar e documento novo em caso existente. Cada resultado deve manter partes, fatos, área, questões, provas, lacunas, fontes, confiança, honorários como referência e revisão humana obrigatória.

## Rollback

O rollback de código deve usar o mecanismo de deploy seguro existente, sempre com SHA integrado à `main`, backup pré-deploy, classificação de migrations e health-check. Não executar deploy manual a partir de branch ou SHA não integrado.
