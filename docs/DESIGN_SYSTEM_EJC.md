# Design System EJC — identidade canônica DPT

## Autoridade visual

A identidade canônica do EJC (28/09/2026) é **base neutra + acento único +
ouro de marca**:

- **Papel neutro** `#F6F7F9`, superfícies brancas, tinta grafite `#101828`.
- **Ação:** UM azul `#1D4ED8` (botões, foco, item ativo, links). Sem gradiente
  no acento e sem família de cores: o que é ação não disputa com o resto.
- **Marca:** ouro DPT `#8F7117`, igual ao dos PDFs Visual Law, reservado a
  logo, filete de seção, destaque editorial e ao rótulo de marca. Nunca é a
  cor do botão de ação.
- **IA:** violeta `#7C3AED`, exclusivo de superfícies de inteligência.
- **Estado:** sucesso, atenção, perigo e informação são semânticos e nunca
  comunicam sozinhos (sempre com ícone ou rótulo).
- **Títulos serifados** (Playfair Display) para o display editorial; interface
  em Inter; dados processuais e monetários em algarismos tabulares.

A imagem de referência define o **idioma visual**. O código vigente define a
**autoridade funcional**. Nenhuma alteração visual pode substituir dados reais,
rotas, RBAC, contratos de API ou fluxos jurídicos por elementos cenográficos.

## Fonte única de verdade

| Assunto                                             | Fonte canônica                                     |
| --------------------------------------------------- | -------------------------------------------------- |
| Tokens semânticos de cor, raio, sombra e tipografia | `frontend/src/styles/ejc-tokens.css`               |
| Mapeamento Tailwind dos tokens                      | `frontend/tailwind.config.js`                      |
| Primitivos React reutilizáveis                      | `frontend/src/components/UI.tsx`                   |
| AppShell                                            | `frontend/src/components/LayoutReference.tsx`      |
| Dashboard/Início                                    | `frontend/src/pages/DashboardUltra.tsx`            |
| Composição premium do Dashboard                     | `frontend/src/styles/ejc-dashboard-premium.css`    |
| Acabamento global de páginas antigas e novas        | `frontend/src/styles/ejc-reference-systemwide.css` |
| Auditoria de CSS                                    | `frontend/scripts/auditar-css.mjs`                 |
| Governança das camadas globais                      | `frontend/scripts/css-governance.json`             |

Os tokens `--ejc-*` devem ser preferidos em toda evolução visual. Não criar
paleta local quando já existir token semântico equivalente.

## Paleta

Regra de uso, sem exceção:

| Papel | Token | Onde pode aparecer |
|-------|-------|---------------------|
| Ação | `--ejc-primary` | botões, foco, item ativo, links, abas |
| Marca | `--ejc-gold` | logo, filete de seção, rótulo de marca |
| IA | `--ejc-ai` | superfícies de inteligência, badge de fonte |
| Estado | `--ejc-success/warning/danger/info` | prazos, riscos, validação |
| Superfície/tinta | `--ejc-background/surface/…`, `--ejc-text/…` | papel, cards, texto |

O ouro NUNCA é a cor de ação e o azul NUNCA é a cor de marca. O tema escuro
troca só os literais: acento claro (`#5B8DEF`) para texto e ícones, tom sólido
da família (`--ejc-primary-solid`) no botão primário, ouro claro (`#D9B45C`)
na marca.

Os valores concretos vivem em `ejc-tokens.css`; este documento não duplica
HEX para evitar divergência.

## Tipografia

- **Display/títulos:** Playfair Display auto-hospedada, com fallback serifado.
- **Interface:** Inter/sans-serif.
- **Dados numéricos:** usar algarismos tabulares quando a leitura comparativa
  for relevante.

## Regra de evolução mais importante

**Não criar uma nova "camada final" de CSS para corrigir aparência.**

O EJC acumulou gerações visuais históricas. A consolidação deve ocorrer de forma
incremental e comprovada:

1. alterar o componente ou a camada que já é dona do elemento;
2. preferir tokens e primitivos canônicos;
3. remover CSS antigo somente após evidência de que não possui consumidores;
4. nunca criar uma terceira paleta (a atual é neutro + acento + ouro);
5. nunca fazer big-bang rewrite apenas para saneamento visual.

O gate `npm run audit:css:verificar` impede aumento das camadas globais do
`main.tsx`, garante que `ejc-tokens.css` continue sendo a última camada do
cascade e bloqueia cabeçalho de comentário com barra invertida + "n", que
engole o restante do arquivo (foi assim que o tema de 28/09 ficou inerte). O relatório de regras potencialmente órfãs é conservador e deve ser
usado como evidência para PRs de remoção, não como autorização automática para
deletar CSS.

## Componentes oficiais

`frontend/src/components/UI.tsx` contém os primitivos canônicos, incluindo:

- Button, IconButton
- Card, Panel, MetricCard, PageContainer
- Input, SearchInput, Select, Textarea, Combobox, DatePicker
- Badge e StatusBadge
- Tabs, Breadcrumb, FilterBar, Stepper, Timeline
- Table, DataGrid, Pagination
- Modal, Dialog/ConfirmModal, Drawer, ActionMenu, Tooltip, Toast
- EmptyState, ErrorState, Skeleton
- FileUploader
- Calendar

Telas novas não devem recriar esses componentes com combinações locais de
classes quando já existir equivalente canônico.

## Dashboard canônico

O Início deve manter:

- saudação dinâmica;
- Entrada Única como superfície protagonista;
- indicadores operacionais alimentados por dados reais;
- Agenda e Prazos;
- Casos em destaque priorizados por risco, prazo e próxima providência;
- calendário integrado que filtra o conteúdo do próprio dashboard;
- Minha Rotina Hoje baseada em tarefas acionáveis no dia;
- atalhos funcionais;
- degradação honesta para indisponibilidade de dados, sem zero falso.

## Migração das telas internas

A aplicação global do design segue migração incremental por domínio:

1. Clientes
2. Casos/Processos
3. Agenda/Prazos
4. Documentos
5. Peças
6. Conhecimento Jurídico/Banco de Teses
7. Financeiro
8. Relatórios/Radar
9. Configurações e superfícies administrativas

Ao migrar uma tela, substituir gradualmente componentes locais pelos primitivos
canônicos e reduzir CSS específico quando houver prova de não uso.

## Acessibilidade e responsividade

Referência mínima: WCAG AA.

Obrigatório:

- foco visível;
- navegação por teclado;
- labels e nomes acessíveis;
- contraste suficiente;
- `prefers-reduced-motion`;
- sidebar em drawer no mobile;
- ausência de overflow horizontal nas larguras homologadas.

## Portões

```bash
cd frontend
npm run lint
npm run audit:css
npm run audit:css:verificar
npm test
npm run build
npm run test:premium-responsive   # quando Chromium/Playwright estiver disponível
```

No CI oficial, a governança CSS roda antes da suíte de frontend.

## Critérios de aceite

- [ ] identidade neutro + acento único + ouro de marca preservada;
- [ ] nenhuma nova camada global de CSS criada sem decisão explícita;
- [ ] tokens canônicos continuam por último no cascade;
- [ ] dados do dashboard são reais ou degradam explicitamente;
- [ ] componentes novos usam o Design System;
- [ ] rotas, RBAC e contratos de API preservados;
- [ ] responsividade e acessibilidade verificadas;
- [ ] lint, testes e build verdes;
- [ ] remoção de CSS legado acompanhada de evidência auditável;
- [ ] rollback possível por commit/PR.
