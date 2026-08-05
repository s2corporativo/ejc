# Restilização EJC v2

## Status

Implementação em branch isolada, sem merge automático na `main`.

## Objetivo

Reconstruir o shell e o dashboard do EJC com fidelidade ao conceito aprovado:
preto, branco e dourado, logomarca original em área branca, cabeçalho superior
com hora, mensagem diária, contatos, IA do escritório e perfil autenticado,
sidebar com calendário semanal e dashboard jurídico sem dados financeiros.

## Princípios

1. Preservar autenticação, RBAC, rotas, APIs e regras de negócio.
2. Não usar dados fictícios permanentes.
3. Não alterar banco de dados ou migrations.
4. Construir componentes próprios em vez de apenas repintar telas antigas.
5. Manter estados de carregamento, erro e indisponibilidade explícitos.
6. Validar desktop, tablet e celular antes de propagar aos demais módulos.

## Arquivos centrais

- `frontend/src/components/Layout.tsx`
- `frontend/src/components/SidebarWeek.tsx`
- `frontend/src/components/header/*`
- `frontend/src/pages/DashboardModern.tsx`
- `frontend/src/styles/ejc-shell-v2.css`
- `frontend/src/config/office.ts`
- `frontend/src/content/dailyMessages.ts`

## Configurações públicas

As variáveis estão documentadas em `frontend/.env.example`:

- `VITE_EJC_OFFICE_NAME`
- `VITE_EJC_TIMEZONE`
- `VITE_EJC_WHATSAPP_NUMBER`
- `VITE_EJC_CONTACT_EMAIL`
- `VITE_EJC_OFFICE_AI_URL`

Nenhuma dessas variáveis deve conter credenciais ou segredos.

## Escopo concluído nesta etapa

- sidebar escura reconstruída;
- logomarca original em tile branco;
- cabeçalho superior escuro;
- relógio e data no fuso configurável;
- mensagem diária auditável;
- atalhos compactos de WhatsApp, e-mail e IA;
- calendário semanal integrado à agenda;
- dashboard jurídico reconstruído;
- quatro KPIs não financeiros;
- andamentos recentes;
- agenda semanal;
- distribuição por área;
- distribuição por status;
- atalhos rápidos por perfil;
- comportamento responsivo básico.

## Fora do escopo desta etapa

- propagação visual módulo a módulo;
- alteração do portal externo do cliente;
- mudança de contratos de API;
- criação de novas permissões;
- deploy ou merge automático.

## Critérios de aceite antes do merge

- build e typecheck aprovados;
- testes automatizados aprovados;
- validação visual nas larguras de 1440, 1366, 1024, 768, 390 e 360 px;
- ausência de overflow horizontal;
- navegação, notificações, privacidade, tema e perfil preservados;
- homologação do titular.
