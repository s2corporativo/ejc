# Relatório técnico — Refatoração visual EJC

Data de início: 05/08/2026  
Atualização de homologação: 06/08/2026  
Branch: `refactor/ejc-premium-gold-graphite-20260805`  
Baseline: `539ba09af90d1f81bfd4bba8c02e002323adb00b`

## 1. Resumo executivo

A intervenção foi executada sobre a arquitetura real do EJC, sem alteração de banco de dados, regras de negócio, autenticação, permissões ou contratos de API. A referência visual aprovada foi adaptada ao sistema real, com identidade em grafite, branco e dourado.

A primeira onda concentra-se no AppShell, configurações institucionais públicas, dashboard operacional e acesso diário à agenda. O dashboard financeiro permanece isolado no módulo Financeiro e não é renderizado na página inicial compartilhada.

O PR permanece em rascunho. Este relatório não autoriza merge nem deploy.

## 2. Arquitetura identificada

- Frontend: React 19, TypeScript, Vite, React Router, Zustand e Tailwind CSS.
- Componentes visuais: design system parcial em `frontend/src/components/UI.tsx`, `frontend/src/index.css`, `frontend/src/styles/site-system.css` e `tailwind.config.js`.
- Shell principal: `frontend/src/components/Layout.tsx`.
- Rotas e permissões: `frontend/src/config/moduleRegistry.tsx` e guards de rota.
- Dashboard estável: `frontend/src/pages/Dashboard.tsx`.
- Backend: FastAPI, SQLAlchemy, PostgreSQL e pgvector.

## 3. Implementação realizada

- Preservação do `DashboardModern.tsx` para rollback.
- Nova implementação isolada em `DashboardPremium.tsx`.
- Entrada estável `Dashboard.tsx` aponta para a implementação premium.
- CSS isolado em `premium-shell.css` e `premium-dashboard.css`.
- Configurações públicas centralizadas em `officeBranding.ts`.
- O caminho público da logomarca é consumido pelo shell interno, login e portal do cliente.
- Nenhum segredo é aceito nas variáveis públicas do Vite.
- Topbar premium com data, hora, mensagem institucional, contatos, IA do Escritório e perfil autenticado.
- Calendário semanal integrado a `/atividades`.
- O dia escolhido abre a rota protegida `/atividades/dia/:date`, alimentada pelos mesmos endpoints reais da Central de Atividades.
- A rota diária é registrada como rota oculta no `moduleRegistry.tsx`, preservando governança central de rotas, RBAC e verificação de links internos.
- A agenda diária possui testes para data válida, data inválida e falha de API sem criação de conteúdo fictício.
- Ajustes de acessibilidade para evitar landmark `banner` duplicado e preservar a semântica nativa dos botões do calendário.
- Smoke autenticado do dashboard em sete larguras, com APIs interceptadas somente no ambiente Playwright.

## 4. Variáveis públicas

- `VITE_EJC_OFFICE_NAME`
- `VITE_EJC_LOGO_PATH`
- `VITE_EJC_WHATSAPP_NUMBER`
- `VITE_EJC_CONTACT_EMAIL`
- `VITE_EJC_OFFICE_AI_URL`
- `VITE_EJC_OFFICE_AI_LABEL`
- `VITE_EJC_TIMEZONE`
- `VITE_EJC_DAILY_MESSAGE`
- `VITE_EJC_DAILY_MESSAGE_SOURCE`

As variáveis acima não podem receber token, senha, cookie, chave de API ou credencial.

## 5. Endpoints consumidos

Dashboard premium:

- `GET /dashboard/`
- `GET /atividades`
- `GET /agenda-eventos/`
- `GET /movimentos/recentes?limit=8`

Agenda diária:

- `GET /atividades`
- `GET /agenda-eventos/`

## 6. Resultados de homologação automatizada

SHA integralmente aprovado antes da centralização final da logomarca: `53e22edeadc7dceec17d24ad183eb9129fe87bab`.

Resultados registrados nessa execução:

- Prettier: aprovado.
- ESLint: aprovado.
- TypeScript: aprovado.
- Build Vite de produção: aprovado; 2.910 módulos transformados.
- Vitest: 59 arquivos e 367 testes aprovados.
- Backend em PostgreSQL/pgvector: 4.822 testes aprovados, 1 ignorado, 77 subtestes aprovados e 16 avisos.
- Ruff: aprovado.
- `pip-audit`: nenhuma vulnerabilidade conhecida encontrada.
- Migrations Alembic: aprovadas em banco real de CI.
- Prova de backup cifrado e restauração em banco vazio: aprovada.
- Chromium autenticado: aprovado em 360, 390, 768, 1024, 1366, 1440 e 1920 px.
- Smoke visual: sem overflow horizontal, sem erros de console e sem renderização das sentinelas financeiras inseridas na resposta de teste.
- Release Gate, Architecture Inventory e governança: aprovados.

A centralização final do caminho da logomarca deverá repetir os gates no novo SHA antes de qualquer decisão de merge.

## 7. Riscos e pendências residuais

### 7.1 Dependências frontend

O `npm audit` registrou quatro vulnerabilidades não críticas:

- 1 moderada em `postcss`;
- 2 altas relacionadas a `brace-expansion`;
- 1 alta em `react-router`/`react-router-dom` no modo RSC.

O gate atual bloqueia vulnerabilidades críticas e, por isso, permaneceu verde. Não foi aplicado `npm audit fix --force`, pois a correção indicada para React Router envolve alteração potencialmente incompatível. Deve ser aberta correção separada, com atualização controlada, testes de regressão e avaliação de aplicabilidade ao modo de uso real do EJC.

### 7.2 Avisos de testes

- Dois testes frontend existentes emitem aviso de atualização React fora de `act(...)`: `EntradaUnica.test.tsx` e `TabTimeline.test.tsx`.
- O ambiente de teste backend gera chave Fernet efêmera quando `VAULT_MASTER_KEYS` não está definido; produção deve manter chave estável e protegida.
- Há aviso de depreciação na integração Starlette/TestClient com `httpx`.
- Há aviso do serviço de embeddings sobre alteração de pooling do modelo `intfloat/multilingual-e5-large`; a compatibilidade semântica deve permanecer monitorada.

Esses avisos não causaram falha nos testes, mas devem ser tratados em frentes técnicas independentes.

### 7.3 Integrações públicas

- WhatsApp, e-mail e IA do Escritório dependem de valores reais no ambiente. Quando ausentes, os controles ficam desabilitados, sem destino fictício.
- O endpoint `/dashboard/` continua devolvendo bloco financeiro por compatibilidade do backend; a página compartilhada não lê nem renderiza esse bloco.
- O calendário semanal depende de `/atividades` e apresenta indisponibilidade explícita se a fonte falhar.

### 7.4 Revisão humana

- As evidências automatizadas foram produzidas e anexadas ao workflow.
- A revisão automática do CodeRabbit não foi concluída por limitação temporária de taxa.
- A homologação visual humana e a aprovação funcional por responsável do escritório continuam obrigatórias antes do merge.

## 8. Rollback

1. Antes do merge: fechar o PR e excluir a branch.
2. Depois do merge: reverter os commits do PR.
3. Rollback específico do dashboard: restaurar `frontend/src/pages/Dashboard.tsx` para exportar `./DashboardModern`.
4. Rollback integral: retornar ao baseline `539ba09af90d1f81bfd4bba8c02e002323adb00b`.

## 9. Critérios obrigatórios antes do merge

- Todos os gates verdes no SHA final da branch.
- Revisão das evidências visuais das sete larguras.
- Validação manual de login, logout, RBAC, navegação, criação de caso e privacidade.
- Configuração e validação dos links reais de WhatsApp, e-mail e IA do Escritório.
- Confirmação de que o dashboard compartilhado permanece sem informações financeiras.
- Aprovação humana formal registrada no PR.
- Nenhum merge automático e nenhum deploy automático.
