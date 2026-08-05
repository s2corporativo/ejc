# Relatório técnico — Refatoração visual EJC

Data: 05/08/2026  
Branch: `refactor/ejc-premium-gold-graphite-20260805`  
Baseline: `539ba09af90d1f81bfd4bba8c02e002323adb00b`

## 1. Resumo executivo

A intervenção foi iniciada sobre a arquitetura real do EJC, sem alteração de banco de dados, regras de negócio, autenticação, permissões ou contratos de API. A referência visual aprovada foi adaptada ao sistema real, com identidade em grafite, branco e dourado.

A primeira onda concentra-se no AppShell, configurações institucionais públicas e dashboard operacional. O dashboard financeiro permanece isolado no módulo Financeiro e não é renderizado na página inicial compartilhada.

## 2. Arquitetura identificada

- Frontend: React 19, TypeScript, Vite, React Router, Zustand e Tailwind CSS.
- Componentes visuais: design system parcial em `frontend/src/components/UI.tsx`, `frontend/src/index.css`, `frontend/src/styles/site-system.css` e `tailwind.config.js`.
- Shell principal: `frontend/src/components/Layout.tsx`.
- Rotas e permissões: `frontend/src/config/moduleRegistry.tsx` e guards de rota.
- Dashboard estável: `frontend/src/pages/Dashboard.tsx`.
- Backend: FastAPI, SQLAlchemy, PostgreSQL e pgvector.

## 3. Riscos mapeados

1. O shell existente reúne navegação, notificações, busca, privacidade, tema, criação de caso e perfil; por isso não foi substituído integralmente.
2. A sidebar e o cabeçalho foram refatorados por camada visual isolada, preservando a árvore funcional existente.
3. O endpoint `/dashboard/` ainda devolve um bloco financeiro por compatibilidade do backend; a nova página não lê nem renderiza esse bloco.
4. Links de contato e IA dependem de variáveis públicas configuradas no ambiente. Quando ausentes, os botões aparecem desabilitados, sem destino falso.
5. O calendário semanal usa `/atividades` e degrada explicitamente para estado indisponível em caso de falha.

## 4. Estratégia aplicada

- Preservação do `DashboardModern.tsx` para rollback.
- Nova implementação isolada em `DashboardPremium.tsx`.
- Entrada estável `Dashboard.tsx` aponta para a implementação premium.
- CSS isolado em `premium-shell.css` e `premium-dashboard.css`.
- Configurações públicas centralizadas em `officeBranding.ts`.
- Nenhum segredo é aceito nas variáveis públicas do Vite.
- O dia escolhido no calendário semanal é transmitido por `?data=AAAA-MM-DD`, aplicado na Central de Atividades e removível por controle visível.

## 5. Variáveis públicas

- `VITE_EJC_OFFICE_NAME`
- `VITE_EJC_LOGO_PATH`
- `VITE_EJC_WHATSAPP_NUMBER`
- `VITE_EJC_CONTACT_EMAIL`
- `VITE_EJC_OFFICE_AI_URL`
- `VITE_EJC_OFFICE_AI_LABEL`
- `VITE_EJC_TIMEZONE`
- `VITE_EJC_DAILY_MESSAGE`
- `VITE_EJC_DAILY_MESSAGE_SOURCE`

## 6. Endpoints consumidos pelo dashboard premium

- `GET /dashboard/`
- `GET /atividades`
- `GET /agenda-eventos/`
- `GET /movimentos/recentes?limit=8`

## 7. Rollback

Opção preferencial: reverter os commits da branch ou fechar o PR sem merge.

Rollback específico do dashboard: restaurar em `frontend/src/pages/Dashboard.tsx` o export anterior para `DashboardModern`.

Rollback integral: retornar ao baseline `539ba09af90d1f81bfd4bba8c02e002323adb00b`.

## 8. Critérios de homologação

- Lint sem erros.
- Typecheck aprovado.
- Testes unitários aprovados.
- Build Vite aprovado.
- Login, logout, RBAC e navegação sem regressão.
- Validação visual em 360, 390, 768, 1024, 1366, 1440 e 1920 px.
- WhatsApp, e-mail e IA do Escritório validados somente após configurar as URLs reais.
- Nenhum indicador financeiro no dashboard compartilhado.
- Nenhum merge ou deploy automático.
