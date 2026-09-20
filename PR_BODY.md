> PR: Reconstrução Visual Canônica do EJC (dashboard 1:1 + design system system-wide)

## Título
Reconstrução Visual Canônica — dashboard 1:1 com a referência DPT e identidade aplicada a todo o sistema

## Descrição
Implementa fielmente o mockup aprovado pelo Titular ("EJC DePaula Teixeira Adv", 18/09/2026) no dashboard (Início) e estende a identidade esmeralda & ouro aos 10 domínios internos, sem alterar contratos de API, RBAC ou rotas.

### Commits desta PR (branch feat/canonical-design-system)
1. `fd4e4de2d` feat(dashboard): Entrada Única em pílula branca canônica e acabamentos 1:1 da referência DPT
2. `f840d09d3` feat(ui): menu canônico com os 11 domínios da referência e item ativo em ouro translúcido
3. `1f02b21b6` test(design): contratos atualizados à referência DPT e fixtures ancoradas em São Paulo
4. `684f8eec9` feat(dashboard): coluna lateral em painel único contínuo (referência 1:1)
5. `b70f90d11` test(homologacao): varredura visual dos 10 domínios canônicos em 2 viewports

### Mudanças principais
- Coluna lateral do dashboard agora é UM painel contínuo (manifesto Themis + calendário + Minha rotina) + card de citação separado — réplica exata da referência.
- Menu lateral com os 11 domínios canônicos e item ativo em ouro translúcido.
- Entrada Única com pílula branca, anexo e botão circular dourado.
- `tests/homologacao-modulos.mjs`: homologação visual automática dos 10 domínios × 2 viewports (overflow, shell canônico, screenshots).

### Gates executados (sem bypass)
- tsc --noEmit ✓ | eslint (0 erros) ✓ | vitest 818/818 ✓ | test:premium-responsive (7 viewports) ✓ | build ✓
- Homologação visual: dashboard 1:1 vs referência (desktop/tablet/mobile) + 10 módulos × 2 viewports sem overflow.

### Riscos
- Baixo: mudanças apenas de apresentação/testes; nenhum contrato, rota ou RBAC alterado.
