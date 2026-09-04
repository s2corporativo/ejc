# Design System EJC

## Objetivo

Padronizar a interface do EJC como um SaaS jurídico profissional, moderno e consistente, evitando que cada tela seja construída com combinações próprias de classes Tailwind.

O projeto já possui tokens visuais globais em `frontend/src/index.css`, incluindo paleta jurídica marrom, bronze e dourado, além de classes base como `card`, `btn`, `badge`, `table`, `input` e variações.

Esta fundação adiciona componentes React oficiais em `frontend/src/components/UI.tsx` e uma camada visual complementar em `frontend/src/styles/site-system.css` para que as novas telas e refatorações usem os mesmos padrões.

## Direção visual

O EJC segue um idioma **flat e compacto** (padrão Verdelimp, mantendo a paleta dourada da casa): cards brancos com borda de 1px visível e raio 10–12px, sombras mínimas (sem elevação no hover), tipografia densa (títulos de página ~20px/700, labels 11px/600, inputs compactos com raio 8px e fonte 13px) e hierarquia clara.

Evitar gradientes decorativos, véus/blobs, glassmorphism e sombras chamativas. Destaques por cor chapada da paleta: botão primário ouro chapado, KPI cards com borda superior de 3px na cor do indicador, cabeçalho de tabela em faixa clara da marca (ouro palha) com texto escuro da marca.

## Aplicação global

O layout interno envolve as páginas com `ejc-modern-scope`. A camada `site-system.css` aplica acabamento global em cards, superfícies, inputs, tabelas, badges e blocos antigos, inclusive telas que ainda não foram migradas para componentes React oficiais.

Isso evita que apenas uma tela fique moderna enquanto o restante do sistema mantém aparência antiga.

## Componentes iniciais

- `Button`: ações primárias, secundárias, outline e ghost.
- `Card`: contêiner padrão para blocos de conteúdo — branco, borda 1px visível, raio 12px e sombra mínima.
- `Badge`: status visuais padronizados.
- `Input`, `Select` e `Textarea`: campos oficiais com label, hint, erro e suporte a ícones.
- `PageHeader`: cabeçalho de página com título e ações.

## Regra de evolução

Novas telas não devem criar botões, cards, badges e inputs manualmente com classes soltas quando já houver componente oficial equivalente.

Ao migrar telas antigas, fazer por PRs pequenos, módulo por módulo, sem misturar regra de negócio com alteração visual.

## Importação recomendada

```tsx
import { Badge, Button, Card, Input, PageHeader } from "../components/UI";
```

Ajustar o caminho relativo conforme a pasta da tela.

## Primeira tela migrada

- `frontend/src/pages/RamosHub.tsx`: modernizada para padrão SaaS/site, com header editorial, cards sem borda pesada, sombra, ícones limpos e CTA discreto.

## Próximas etapas

1. Migrar primeiro telas críticas e muito acessadas: Dashboard, Clientes, Casos/Processos e Financeiro.
2. Criar componentes oficiais para `Table`, `EmptyState`, `Modal`, `Tabs`, `StatCard` e `AiPanel`.
3. Remover duplicidades visuais progressivamente.
4. Manter cada PR visual pequeno, com CI verde e sem alteração de backend.
