# Design System do EJC

## Objetivo

Padronizar a interface do Ecossistema Jurídico Clovis sem alterar regras de negócio, contratos de API, autenticação ou RBAC. A evolução visual deve ser gradual, auditável e reversível.

## Fonte única de verdade

- Tokens de cor, tipografia, espaçamento e elevação: `frontend/tailwind.config.js`.
- Variáveis de tema e regras globais: `frontend/src/index.css`.
- Componentes reutilizáveis: `frontend/src/components/UI.tsx`.
- Estado e persistência de tema: `frontend/src/stores/theme.ts`.
- Seletor reutilizável: `frontend/src/components/ThemeSelector.tsx`.

Não criar paletas locais ou um segundo mecanismo de tema dentro de páginas.

## Temas

O EJC suporta três preferências:

1. `light`: modo claro;
2. `dark`: modo escuro;
3. `system`: acompanha o dispositivo.

A preferência é persistida em `localStorage` pela chave `ejc_theme`. A classe `dark` é aplicada ao elemento `<html>` antes do primeiro render para evitar mudança visual abrupta.

## Estrutura obrigatória de página

Toda nova tela deve conter, quando aplicável:

1. `PageHeader` com título, descrição e ações;
2. filtros em `FilterBar`;
3. conteúdo dentro de `SectionCard` ou `Card`;
4. estados de loading;
5. estado vazio com `EmptyState`;
6. mensagem de erro controlada;
7. confirmação para ação destrutiva;
8. comportamento responsivo;
9. autorização correspondente no backend.

## Semântica visual

- `primary`: marca, navegação e ações principais;
- `success`: concluído, regular ou recebido;
- `warn`: atenção, pendência ou proximidade de prazo;
- `danger`: vencimento, bloqueio ou ação destrutiva;
- `ai`: recursos de inteligência artificial;
- `slate`: informação neutra ou secundária.

Cor nunca deve ser o único meio de comunicar status. Usar texto, ícone ou rótulo em conjunto.

## Regras jurídicas e LGPD

- Não exibir CPF, CNPJ, telefone, e-mail ou dados processuais sensíveis em cards gerais sem necessidade operacional.
- Indicadores financeiros devem respeitar o mesmo conjunto de roles adotado pelas rotas e endpoints.
- Resultados de IA devem indicar que exigem conferência de fontes e revisão humana.
- Exclusão, envio, assinatura, compartilhamento e alteração processual relevante exigem confirmação e auditoria.
- O frontend complementa a autorização; nunca substitui o RBAC do backend.

## Migração das páginas

Ordem recomendada:

1. Dashboard;
2. Clientes e dossiê;
3. Casos e detalhe do caso;
4. Prazos, agenda e tarefas;
5. Documentos e peças;
6. Financeiro;
7. Inteligência jurídica;
8. Administração e governança.

Para cada tela:

- manter a rota;
- preservar o endpoint consumido;
- manter parâmetros de busca e filtros;
- validar roles;
- migrar para os componentes compartilhados;
- testar claro, escuro e sistema;
- validar desktop, tablet e celular;
- remover o componente antigo somente após a validação.

## Critérios de aceite

- [ ] Frontend compila sem erro
- [ ] Rotas preservadas
- [ ] Autorização validada
- [ ] Tema claro funcional
- [ ] Tema escuro funcional
- [ ] Tema do sistema funcional
- [ ] Preferência persistida
- [ ] Loading, erro e estado vazio tratados
- [ ] Sem exposição adicional de dados pessoais
- [ ] Sem alteração de contrato de API
- [ ] Responsividade validada
- [ ] Rollback possível por commit ou pull request
