# Design System EJC

Documento canônico do idioma visual do EJC. Substitui e consolida
`docs/FRONTEND_DESIGN_SYSTEM.md` e `frontend/LEGAL_TECH_PREMIUM.md`, que
descreviam camadas divergentes entre si e já não correspondiam ao produto.

## Fonte única de verdade

| Assunto                                            | Arquivo                                                          |
| -------------------------------------------------- | ---------------------------------------------------------------- |
| Tokens da marca, base Tailwind e utilitários       | `frontend/src/index.css`                                         |
| Tokens de cor/tipografia/espaçamento do Tailwind   | `frontend/tailwind.config.js`                                    |
| Componentes React oficiais                         | `frontend/src/components/UI.tsx`                                 |
| Shell (topbar, sidebar, área de trabalho)          | `frontend/src/styles/app-shell.css`                              |
| Acabamento global (cards, inputs, tabelas, badges) | `frontend/src/styles/site-system.css`                            |
| Idioma de referência das páginas                   | `frontend/src/styles/ejc-reference-2026.css` e `-systemwide.css` |
| Polimento do workspace Financeiro                  | `frontend/src/styles/workspace-executive.css`                    |
| Tema (claro/escuro/sistema)                        | `frontend/src/stores/theme.ts`                                   |

Não criar paleta local nem um segundo mecanismo de tema dentro de páginas.

## Ordem das camadas

A ordem de importação está declarada e comentada em `frontend/src/main.tsx`.
É a única ordem válida: `fonts → index → app-shell → site-system →
ejc-reference-2026 → ejc-reference-systemwide → workspace-executive`.

**Regra de evolução — a mais importante deste documento.** Não criar uma nova
"camada final" para corrigir aparência. Foi assim que o sistema acumulou onze
folhas sobrepostas, 313 declarações `!important` e 2.9 mil linhas de CSS que
nenhum elemento alcançava. Ajuste se faz na camada que já é dona do elemento,
ou nos tokens. Camada nova exige justificativa no PR.

## Direção visual

Idioma **flat e compacto**: superfícies brancas com borda de 1px visível,
raio 10–12px, sombras mínimas, tipografia densa e hierarquia por contraste
e espaçamento — não por decoração.

- Sem gradientes decorativos, véus, glassmorphism ou sombras chamativas.
- Destaques por cor chapada da paleta (marrom/bronze/ouro da casa).
- Sidebar clara no tema claro, escura no tema escuro.
- Números de tabelas e KPIs em `tabular-nums`.

## Semântica de cor

`primary` marca e ações principais · `success` concluído/regular/recebido ·
`warn` pendência ou proximidade de prazo · `danger` vencimento, bloqueio ou
ação destrutiva · `ai` recursos de inteligência artificial · `slate`
informação neutra.

Cor nunca é o único portador de significado: sempre acompanhada de texto,
ícone ou rótulo.

## Componentes oficiais

`frontend/src/components/UI.tsx` já fornece `Button`, `Card`, `SectionCard`,
`Badge`, `StatusBadge`, `RiskBadge`, `PriorityBadge`, `Input`, `Select`,
`Textarea`, `SearchBar`, `PageHeader`, `StatCard`, `Table` (+`THead`, `TR`,
`TH`, `TD`), `Tooltip`, `Modal`, `ConfirmModal`, `Drawer`, `Alert`,
`EmptyState`, `ErrorState`, `Spinner`, `SkeletonTable`, `IANotice`,
`AISurface`, `ConfidenceBadge`, `SourceCitation` e `VisualLawDocument`.

Tela nova não recria botão, card, badge ou input com classes soltas quando já
existe componente oficial equivalente.

## Estrutura obrigatória de página

`PageHeader` com título/descrição/ações · filtros em `FilterBar` · conteúdo em
`SectionCard`/`Card` · estado de carregamento · estado vazio com `EmptyState` ·
erro controlado · confirmação para ação destrutiva · responsividade ·
autorização correspondente no backend.

## Responsividade — media query vs. container query

Media query enxerga a **viewport**; não sabe que um cartão ficou estreito
porque o grid trocou de colunas. Quando o conteúdo depende da largura do
próprio contêiner (fluxos em etapas, grids internos, tabelas embutidas), use
**container query**: `.ejc-reference-card` já declara
`container-type: inline-size`.

Grids não devem impor largura mínima rígida abaixo de 1280px — a sidebar fixa
consome ~250px. Prefira `minmax(0, Nfr)` a `minmax(360px, Nfr)`.

## Regras jurídicas e LGPD

- Não exibir CPF, CNPJ, telefone, e-mail ou dado processual sensível em cards
  gerais sem necessidade operacional.
- Indicadores financeiros respeitam o mesmo conjunto de roles das rotas.
- Resultado de IA sempre indica que exige conferência de fontes e revisão
  humana.
- Exclusão, envio, assinatura, compartilhamento e alteração processual
  relevante exigem confirmação e auditoria.
- O frontend complementa a autorização; nunca substitui o RBAC do backend.

## Portões de verificação

```bash
cd frontend
npm run lint                 # tsc --noEmit
npm test                     # vitest
npm run build
npm run audit:css            # relatório de CSS inalcançável
npm run audit:css:verificar  # falha se houver regressão acima do teto
npm run test:shell-responsive  # Chromium real, 7 viewports + reduced-motion
```

`npm run audit:css:verificar` compara com `frontend/scripts/css-orfao-teto.json`.
Ao remover CSS órfão, baixe o teto no mesmo PR; ele nunca sobe sem
justificativa registrada.

## Critérios de aceite

- [ ] Frontend compila sem erro
- [ ] Rotas preservadas
- [ ] Autorização validada
- [ ] Temas claro, escuro e sistema funcionais e persistidos
- [ ] Loading, erro e estado vazio tratados
- [ ] Sem exposição adicional de dados pessoais
- [ ] Sem alteração de contrato de API
- [ ] Responsividade validada (7 viewports, sem overflow e sem corte)
- [ ] Auditoria de CSS órfão dentro do teto
- [ ] Rollback possível por commit ou pull request
