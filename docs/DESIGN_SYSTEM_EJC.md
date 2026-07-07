# Design System EJC

## Objetivo

Padronizar a interface do EJC como um SaaS jurídico profissional, moderno e consistente, evitando que cada tela seja construída com combinações próprias de classes Tailwind.

O projeto já possui tokens visuais globais em `frontend/src/index.css`, incluindo paleta jurídica marrom, bronze e dourado, além de classes base como `card`, `btn`, `badge`, `table`, `input` e variações.

Esta fundação adiciona componentes React oficiais em `frontend/src/components/ui` para que as novas telas e refatorações usem os mesmos padrões.

## Componentes iniciais

- `Button`: ações primárias, secundárias, outline, ghost e danger.
- `Card`: contêiner padrão para blocos de conteúdo.
- `Badge`: status visuais padronizados.
- `Page`: estrutura de página, cabeçalho, descrição, ações e grid.

## Regra de evolução

Novas telas não devem criar botões, cards e badges manualmente com classes soltas quando já houver componente oficial equivalente.

Ao migrar telas antigas, fazer por PRs pequenos, módulo por módulo, sem misturar regra de negócio com alteração visual.

## Importação recomendada

```tsx
import { Badge, Button, Card, Page, PageHeader, PageTitle } from "../components/ui";
```

Ajustar o caminho relativo conforme a pasta da tela.

## Próximas etapas

1. Migrar primeiro telas críticas e muito acessadas: Dashboard, Clientes, Casos/Processos e Financeiro.
2. Criar componentes oficiais para `Input`, `Select`, `Table`, `EmptyState`, `Modal`, `Tabs`, `StatCard` e `AiPanel`.
3. Remover duplicidades visuais progressivamente.
4. Manter cada PR visual pequeno, com CI verde e sem alteração de backend.
