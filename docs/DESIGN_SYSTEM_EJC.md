# Design System EJC — identidade canônica DPT

## Autoridade visual

A identidade canônica do EJC é a referência DPT aprovada em 18/09/2026:
verde-esmeralda profundo, ouro institucional, marfim/off-white, títulos
editoriais serifados e interface sans-serif limpa.

A imagem de referência define o **idioma visual**. O código vigente define a
**autoridade funcional**. Nenhuma alteração visual pode substituir dados reais,
rotas, RBAC, contratos de API ou fluxos jurídicos por elementos cenográficos.

## Fonte única de verdade

| Assunto | Fonte canônica |
|---|---|
| Tokens semânticos de cor, raio, sombra e tipografia | `frontend/src/styles/ejc-tokens.css` |
| Mapeamento Tailwind dos tokens | `frontend/tailwind.config.js` |
| Primitivos React reutilizáveis | `frontend/src/components/UI.tsx` |
| AppShell | `frontend/src/components/LayoutReference.tsx` |
| Dashboard/Início | `frontend/src/pages/DashboardUltra.tsx` |
| Composição premium do Dashboard | `frontend/src/styles/ejc-dashboard-premium.css` |
| Acabamento global de páginas antigas e novas | `frontend/src/styles/ejc-reference-systemwide.css` |
| Auditoria de CSS | `frontend/scripts/auditar-css.mjs` |
| Governança das camadas globais | `frontend/scripts/css-governance.json` |

Os tokens `--ejc-*` devem ser preferidos em toda evolução visual. Não criar
paleta local quando já existir token semântico equivalente.

## Paleta

Famílias principais:

- **Esmeralda:** superfícies institucionais, sidebar e ações estruturais.
- **Ouro:** destaque, foco, seleção e elementos editoriais.
- **Marfim/off-white:** canvas principal.
- **Branco:** superfícies de trabalho.
- **Tinta escura:** texto principal.
- **Cores semânticas:** sucesso, atenção, perigo e informação.

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
4. nunca trocar o visual DPT por uma identidade paralela;
5. nunca fazer big-bang rewrite apenas para saneamento visual.

O gate `npm run audit:css:verificar` impede aumento das camadas globais do
`main.tsx` e garante que `ejc-tokens.css` continue sendo a última camada do
cascade. O relatório de regras potencialmente órfãs é conservador e deve ser
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

- [ ] identidade DPT preservada;
- [ ] nenhuma nova camada global de CSS criada sem decisão explícita;
- [ ] tokens canônicos continuam por último no cascade;
- [ ] dados do dashboard são reais ou degradam explicitamente;
- [ ] componentes novos usam o Design System;
- [ ] rotas, RBAC e contratos de API preservados;
- [ ] responsividade e acessibilidade verificadas;
- [ ] lint, testes e build verdes;
- [ ] remoção de CSS legado acompanhada de evidência auditável;
- [ ] rollback possível por commit/PR.
