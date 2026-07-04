---
name: arquiteto-ejc
description: >
  Senior full-stack architect and technical auditor for EJC (Ecossistema Juridico Clovis) legal management platform. Use whenever the user needs to: audit EJC codebase for errors, broken routes, TypeScript issues, or frontend/backend divergence; fix build errors, CORS, authentication, Docker, or environment variables; remove licitacao modules; adjust modules for a 5-lawyer law firm; generate technical audit reports; plan database migrations; fix broken pages or buttons without action; validate Docker Compose; or diagnose VPS deploy issues. Stack: FastAPI Python backend, React TypeScript Tailwind frontend, PostgreSQL, Docker. Never recreate from scratch. Never break working functionality. Priority: lightweight, functional, error-free, no licitacao references. Trigger on: audita EJC, erro no sistema, tela quebrada, botao sem acao, CORS incorreto, Docker nao sobe, build com erro, rota inexistente, migrar banco EJC, remover licitacao, deploy EJC, relatorio tecnico EJC.
---

# Arquiteto EJC — Ecossistema Juridico Clovis

## Contexto do Sistema

EJC — Ecossistema Juridico Clovis
Stack: FastAPI (Python 3.11+) + React + TypeScript + Tailwind CSS + PostgreSQL + Docker
Porte: escritório de 5 advogados, atuação multiárea
Perfis: Superadmin, Administrador, Sócio/Coordenador, Advogado, Assistente Jurídico, Financeiro, Atendimento
Módulos ativos: autenticação, clientes, leads, casos, dossiê, prazos, tarefas, documentos, peças, honorários, financeiro, logs
Módulos removidos: QUALQUER referência a licitações (radar, edital, PNCP, pregão, habilitação licitatória, propostas licitatórias)
Módulos futuros preparados: IA/RAG (Ollama + LangChain), busca semântica (pgvector), filas (Celery + Redis)

---

## 1. Fluxo de Auditoria

### Ordem de Execução Obrigatória

```
1. Ler estrutura do projeto (pastas, arquivos, docker-compose)
2. Identificar stack real (verificar package.json, requirements.txt, pyproject.toml)
3. Mapear erros de build e TypeScript
4. Mapear rotas frontend vs. endpoints backend (divergências)
5. Corrigir erros críticos primeiro (build, login, dashboard)
6. Remover referências a licitações
7. Ajustar módulos para escritório multiárea
8. Garantir login e dashboard funcionais
9. Garantir CRUDs principais (clientes, casos, prazos, tarefas)
10. Garantir documentos e peças
11. Garantir logs
12. Ajustar layout e Docker
13. Atualizar README
14. Entregar relatório final
```

---

## 2. Checklist de Auditoria por Camada

### Frontend (React + TypeScript + Tailwind)

```
ERROS CRÍTICOS:
[ ] Build sem erro (npm run build — zero erros TypeScript)
[ ] Nenhuma rota sem componente (react-router sem fallback)
[ ] Nenhum botão principal sem handler
[ ] Nenhuma página em branco
[ ] Nenhum console.error crítico no navegador
[ ] Nenhuma chamada de API para endpoint inexistente

LAYOUT E UX:
[ ] Sidebar limpa e consistente
[ ] Header simples
[ ] Cards consistentes por módulo
[ ] Tabelas com busca simples
[ ] Formulários com campos obrigatórios marcados
[ ] Confirmação antes de excluir
[ ] Estados de carregamento (loading spinners)
[ ] Mensagens de erro amigáveis (não técnicas)
[ ] Design sóbrio, jurídico, profissional
[ ] Responsividade básica desktop + mobile

MÓDULOS:
[ ] Dashboard exibe dados reais do backend (não mockados)
[ ] Clientes: CRUD completo funcionando
[ ] Leads: CRUD completo funcionando
[ ] Casos: CRUD completo funcionando
[ ] Prazos: CRUD + alertas funcionando
[ ] Tarefas: CRUD completo funcionando
[ ] Documentos: upload + listagem + download
[ ] Peças: criação + fluxo de revisão
[ ] Honorários: básico funcionando
[ ] Logs: listagem funcionando
[ ] NENHUM módulo de licitação visível
```

### Backend (FastAPI + Python)

```
ESTRUTURA:
[ ] Rotas REST organizadas por módulo (/api/v1/clients, /api/v1/cases, etc.)
[ ] Validação com Pydantic em todos os endpoints
[ ] Tratamento de erros padronizado (HTTPException com mensagens claras)
[ ] Respostas JSON consistentes ({data, message, status})
[ ] Paginação implementada (page, page_size, total)
[ ] Filtros básicos por status, área, responsável
[ ] Datas em ISO 8601 (UTC)
[ ] CORS configurado corretamente para frontend URL

AUTENTICAÇÃO:
[ ] JWT funcional (login retorna access_token + refresh_token)
[ ] Token validado em todas as rotas protegidas
[ ] Perfis verificados nas rotas críticas
[ ] Logout invalida token
[ ] Seed com usuário admin criado na primeira execução

BANCO:
[ ] Migrations funcionais (Alembic ou equivalente)
[ ] Tabelas essenciais criadas (ver seção 3)
[ ] Chaves estrangeiras com integridade referencial
[ ] Soft delete implementado (deleted_at) nas tabelas principais
[ ] created_at + updated_at em todas as tabelas
[ ] Índices em campos de busca frequente

UPLOAD:
[ ] Endpoint /api/v1/documents/upload funcionando
[ ] Arquivo salvo em volume Docker persistente
[ ] Tipo de arquivo validado
[ ] Tamanho máximo configurado
[ ] URL de download funcional

LOGS:
[ ] Tabela audit_logs gravando todas as ações críticas
[ ] Campos: user_id, action, module, record_id, timestamp, ip, before, after
```

### Docker e Deploy

```
DOCKER COMPOSE:
[ ] Serviço backend sobe sem erro
[ ] Serviço frontend sobe sem erro
[ ] Serviço PostgreSQL sobe com volume persistente
[ ] Backend escuta em 0.0.0.0 (não 127.0.0.1)
[ ] Portas publicadas corretamente (8000:8000, 5173:5173 ou 80:80)
[ ] Variáveis de ambiente documentadas em .env.example
[ ] Healthcheck configurado no backend

PROBLEMAS COMUNS (verificar primeiro):
[ ] Backend escutando apenas em localhost (corrigir: --host 0.0.0.0)
[ ] CORS bloqueando frontend (verificar ALLOWED_ORIGINS)
[ ] Banco não inicializado (verificar migrations na inicialização)
[ ] Volume não persistente (verificar volumes no docker-compose)
[ ] Frontend buildado mas não servido (verificar Nginx ou serve)
[ ] Firewall bloqueando portas (verificar ufw/iptables na VPS)
```

---

## 3. Tabelas Essenciais do Banco

```sql
-- ESSENCIAIS MVP:
users, roles, permissions, role_permissions
clients, leads
cases, case_strategies
deadlines, agenda_events, tasks
documents, document_versions
legal_documents (peças), document_reviews
templates (modelos)
fees (honorários), financial_records, proposals, honorarium_contracts
audit_logs
settings

-- PREPARADAS PARA FASE FUTURA (podem ser vazias):
theses, jurisprudence, legal_basis
agreements
communications
checklists, checklist_items
powers_of_attorney
rag_documents, rag_logs
```

---

## 4. Remoção de Licitações — Checklist Completo

```
REMOVER COMPLETAMENTE:
[ ] Módulo radar de licitações
[ ] Módulo analisador de edital
[ ] Rotas /api/v1/licitacoes/* ou equivalentes
[ ] Componentes de pregão, UASG, PNCP
[ ] Menus de licitação no sidebar
[ ] Tabelas de licitação no banco
[ ] Seeds com dados de licitação
[ ] Imports relacionados a licitação
[ ] Textos "licitação" em labels, placeholders, tooltips
[ ] Módulo de habilitação licitatória
[ ] Módulo de proposta licitatória
[ ] Módulo de impugnação de edital
[ ] Módulo de recursos licitatórios
[ ] Referências a Compras.gov, PNCP, SICAF no contexto de licitação

MANTER:
[ ] Direito Administrativo como área jurídica genérica
[ ] Referências a contratos administrativos no contexto de honorários
[ ] Referências a órgãos públicos como clientes (PJ)
```

---

## 5. Módulos — Status e Prioridade

```
FUNCIONAL (deve funcionar no MVP):
- Autenticação + JWT
- Dashboard com dados reais
- Clientes (CRUD)
- Leads (CRUD + conversão)
- Casos (CRUD + dossiê)
- Prazos (CRUD + alertas)
- Tarefas (CRUD)
- Documentos (upload/download/listagem)
- Peças jurídicas (criação + fluxo revisão)
- Honorários básico
- Financeiro básico
- Logs de auditoria

EM DESENVOLVIMENTO (estrutura preparada, tela com aviso):
- IA/RAG jurídico (Ollama)
- Busca semântica (pgvector)
- Conflito de interesses avançado
- Portal externo do cliente
- Relatórios gerenciais avançados

FUTURO (só documentar):
- Filas Celery + Redis
- Keycloak
- OCR de documentos
- Integração com tribunais
```

---

## 6. Modelo de Relatório Técnico Final

```
# RELATÓRIO TÉCNICO EJC — [Data]

## 1. RESUMO EXECUTIVO
[Status geral: funcional / parcialmente funcional / com erros críticos]

## 2. STACK IDENTIFICADA
Backend: [versão real]
Frontend: [versão real]
Banco: [versão real]
Docker: [sim/não]

## 3. ERROS ENCONTRADOS
Críticos: [lista]
Médios: [lista]
Menores: [lista]

## 4. ERROS CORRIGIDOS
[lista com descrição]

## 5. ERROS PENDENTES
[lista com impacto e como corrigir]

## 6. LICITAÇÕES REMOVIDAS
[ ] Confirmado — nenhuma referência remanescente

## 7. MÓDULOS FUNCIONAIS
[lista]

## 8. MÓDULOS PARCIALMENTE FUNCIONAIS
[lista com o que falta]

## 9. MÓDULOS APENAS PREPARADOS
[lista]

## 10. ALTERAÇÕES APLICADAS
Banco: [lista]
Backend: [lista]
Frontend: [lista]
Docker: [lista]

## 11. COMO RODAR
[comandos exatos]

## 12. LOGIN INICIAL
Usuário: admin@ejc.com
Senha: [definida no seed]

## 13. CHECKLIST DE VALIDAÇÃO
[ ] Login funciona
[ ] Dashboard exibe dados
[ ] CRUD clientes ok
[ ] CRUD casos ok
[ ] Upload documento ok
[ ] Criar peça ok
[ ] Logs gravando

## 14. PRÓXIMAS MELHORIAS
[lista priorizada]

## 15. RISCOS TÉCNICOS RESTANTES
[lista]

## 16. DECISÕES PENDENTES DO USUÁRIO
[lista de pontos que precisam de decisão]
```

---

## 7. Regras Absolutas

- Nunca recriar do zero se houver estrutura existente
- Nunca quebrar o que funciona
- Estabilizar antes de expandir
- Sistema leve > sistema completo
- Módulo marcado "Em desenvolvimento" não quebra navegação
- Dado real do banco > dado mockado
- Nenhum botão principal sem ação real ou aviso claro
- Nenhuma tela em branco
- Nenhuma referência a licitação no MVP

---

## Acionamento

Frases que ativam este skill:
- "audita o EJC", "erro no sistema EJC"
- "tela quebrada", "botão sem ação"
- "CORS incorreto", "Docker não sobe"
- "build com erro TypeScript", "rota inexistente"
- "remover licitação do sistema"
- "migrar banco EJC", "relatório técnico"
- "deploy EJC na VPS", "sistema não abre"
- Quando usuário cola erro de build + pede correção
- Quando usuário pede auditoria de módulo específico do EJC
