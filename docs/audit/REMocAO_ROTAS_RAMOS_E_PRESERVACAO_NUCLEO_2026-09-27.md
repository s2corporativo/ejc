# Remoção lógica das rotas de ramos e preservação do núcleo de inteligência

**Data:** 27/09/2026  
**Escopo:** EJC — simplificação da superfície de Áreas de Atuação

## Resultado

- O frontend deixou de registrar `ramos` e `ramo-detalhe` no `moduleRegistry`.
- `/ramos`, `/areas-de-atuacao` e `/ramos/:slug` redirecionam para `/inteligencia?tab=conhecimento`.
- A aba contextual do caso deixou de expor calculadoras e workspaces de ramos.
- As análises estratégicas, análise de contratos com IA e IA defensiva do caso permanecem disponíveis.
- O backend não monta mais as **82 rotas** pertencentes aos sub-routers `ramos_*`.
- Os arquivos dos sub-routers foram preservados para rollback e para testes unitários das regras.
- A montagem pode ser reativada explicitamente com `EJC_ENABLE_RAMOS_ROUTES=true`; o padrão é desativado.
- A telemetria deixou de monitorar os três aliases de ramos removidos.
- Foi criado o snapshot `backend/tests/snapshots/openapi_rotas_ramos_removidas.json`; o baseline histórico não foi sobrescrito.

## Evidências

| Verificação | Resultado |
|---|---:|
| Rotas no snapshot de remoção | 82 |
| Rotas removidas ainda publicadas | 0 |
| Testes backend direcionados | 214 passed |
| Testes frontend direcionados | 40 passed |
| `npm run lint` | OK |
| `npm run build` | OK |
| `git diff --check` | OK |

## Núcleo preservado

A remoção não altera os contratos do núcleo de inteligência. Permanecem no registry e no caso:

- Inteligência Jurídica;
- Entrada e triagem inteligente;
- análise estratégica contextual;
- análise e comparação de contratos com IA;
- IA defensiva do caso;
- governança, fontes, teses e demais fluxos centrais.

## Limitações e risco residual

1. A remoção é **lógica e reversível**, não uma exclusão física dos módulos neste ciclo.
2. Os testes unitários que chamam diretamente funções dos módulos de ramos continuam úteis para preservar regras e permitir eventual rollback; eles não significam que as rotas estejam públicas.
3. A publicação efetiva exige revisão humana, revisão do ambiente de deploy e validação do OpenAPI produzido no ambiente alvo.
4. Qualquer peça ou saída jurídica gerada por IA permanece sujeita a revisão humana antes de uso ou protocolo.

## Validação E2E de redirects

Executado contra o build servido localmente em Chromium headless, com sessão fictícia e APIs interceptadas somente no teste:

| Origem | Destino validado | Resultado |
|---|---|---|
| `/ramos` | `/inteligencia?tab=conhecimento` | OK |
| `/areas-de-atuacao?foco=civel#topo` | `/inteligencia?tab=conhecimento&foco=civel#topo` | OK |
| `/ramos/civil?origem=legado#ancora` | `/inteligencia?tab=conhecimento&origem=legado#ancora` | OK |

Os três fluxos apresentaram corpo não vazio e **zero page errors**. A suíte oficial `tests/navegacao-registry.mjs` não foi executada porque exige credenciais E2E externas; o teste acima valida especificamente o contrato de redirect solicitado, sem acessar produção.
