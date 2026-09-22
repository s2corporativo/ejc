# Wave 4 — pós-limpeza e otimização de performance

## Objetivo

A Wave 4 consolida superfícies que permaneceram funcionais após a limpeza estrutural, preservando contratos de produto e reduzindo chamadas duplicadas, custo de bundle e manutenção de integrações. A execução será incremental, com uma fonte canônica por domínio, contratos estáticos e testes de regressão antes de qualquer remoção.

## Escopo priorizado

| Item | Foco | Decisão inicial | Critério de saída |
| --- | --- | --- | --- |
| FE-07 | Streaming HTTP | Preservar `lib/stream.ts`; não fundir com Axios enquanto os quatro consumidores exigirem `fetch` incremental | Parser SSE e consumidores cobertos; nenhuma duplicação funcional introduzida |
| FE-08 | Taxonomia `/areas` | Executar primeiro: centralizar GET `/areas` em `lib/areas.ts`, com cache de sessão e fallback | RamosHub e RaioXProcesso sem fetch próprio; contratos e build verdes |
| FE-10 | APIs DPT360 | Consolidar somente após mapear exports e consumidores | Uma fachada sem quebra de imports |
| FE-11 | APIs de IA | Migrar chamadas `/ai/*` para `services/ai.ts` apenas com equivalência de payload e resposta | Contratos de tabs, peças e feedback verdes |
| FE-12/14/15 | Limpeza estrutural | Fazer após FE-08, com prova de rotas/consumidores e rollback | Nenhuma rota ou workspace órfão |
| UI-01/02 | CSS legado e redirects | Postergar para wave própria de telemetria e prova visual | Zero consumidores e cobertura de navegação/viewport |

## Execução inicial — FE-08

`useAreas()` já era o serviço canônico e mantinha cache de módulo com fallback estático. `RamosHub` e `RaioXProcesso` ainda executavam seus próprios `GET /areas`, criando chamadas duplicadas e caches locais divergentes. Os dois consumidores agora usam `useAreas()`: o hub aplica sua mesclagem visual sobre a resposta canônica e o Raio-X consome a mesma lista sem manter catálogo próprio.

Foi adicionado o contrato `areas.consolidation.contract.test.ts`, que verifica a existência do único fetch no hook, a preservação do fallback/cache e a ausência de fetch duplicado nos consumidores.

## Execução — FE-07

O runtime `lib/stream.ts` foi preservado como a única camada de `fetch` cru para respostas SSE POST. Foram adicionados testes para o `Bearer`, credenciais de cookie, renovação única após HTTP 401, logout quando o refresh falha e os quatro consumidores reais: `AgenteIA`, `PecaGeneratorModal`, `AnaliseExtratos` e `BancarioForense`. Não foi feita uma migração artificial para Axios, pois ela perderia o corpo incremental do stream.

## Execução — FE-10

Os tipos e chamadas de Radar e Relatório Executivo foram incorporados à fachada `pages/dpt360/api.ts`. `DptRadar` e `DptReports` agora importam exclusivamente dessa fachada; os módulos paralelos `radarApi.ts` e `reportApi.ts` foram removidos após a migração dos testes. O contrato `dptApi.consolidation.contract.test.ts` impede a reintrodução dos módulos HTTP duplicados.

## Execução — FE-11

As operações de sugestão de honorários, análise de caso, análise/comparação de contratos, aplicação HITL e feedback foram adicionadas a `services/ai.ts`. `TabResumo`, `TabFerramentas` e `ContextualAIAssistant` deixaram de montar endpoints `/ai/*` diretamente e passaram a usar funções tipadas da fachada. O contrato `ai.consolidation.contract.test.ts` verifica a existência dessas operações e bloqueia o retorno de chamadas raw nos consumidores migrados.

## Validação prevista

A etapa FE-08 deve passar pelo contrato específico, pelos testes de áreas/RamosHub, TypeScript, build Vite e suíte frontend completa. A próxima etapa recomendada é FE-10, após inventariar exports e consumidores de `dpt360/api.ts`, `radarApi.ts` e `reportApi.ts`. FE-07 permanece uma decisão de preservação, não uma exclusão automática.
