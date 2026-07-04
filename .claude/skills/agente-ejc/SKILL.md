---
name: agente-ejc
description: >
  Agente coordenador do EJC (Ecossistema Jurídico Clovis) — sistema de gestão jurídica full-stack (FastAPI Python + React TypeScript + PostgreSQL + Docker) para o escritório De Paula Teixeira Advogados. DNA técnico, contexto do sistema, roteamento de skills técnicas e padrões de desenvolvimento. Use SEMPRE como base ao iniciar qualquer tarefa técnica do EJC: novos módulos, correções de bugs, deploy, banco de dados, integrações, testes, monitoramento. Aciona em: "EJC", "sistema jurídico", "ecossistema jurídico clovis", "bug no sistema", "deploy EJC", "nova funcionalidade EJC", "módulo EJC", "banco EJC", "FastAPI EJC", "React EJC", "Docker EJC", "VPS EJC", "auditoria EJC".
---

# AGENTE EJC — DNA Técnico

## Identidade do Sistema
**Nome:** EJC — Ecossistema Jurídico Clovis  
**Stack:** FastAPI Python 3.11+ | React TypeScript 18+ | PostgreSQL | Docker  
**Propósito:** Sistema de gestão jurídica para escritório De Paula Teixeira Advogados  
**Status:** Em desenvolvimento  

## Módulos Funcionais Esperados
- Gestão de clientes e casos
- Controle de prazos e alertas
- Peças jurídicas e documentos
- Financeiro e honorários
- CRM jurídico
- Portal do cliente (futuro)

## Princípios de Desenvolvimento
- Nunca recriar do zero o que existe — sempre preservar funcionalidade ativa
- Prioridade: leve, funcional, sem erros, sem referências a licitação
- Qualquer peça gerada por IA passa por revisão humana obrigatória
- Logs de uso de IA registrados (conformidade LGPD/OAB)

## Mapa de Skills — Roteamento
| Demanda | Skill a acionar |
|---|---|
| Correção de bugs/auditoria | `arquiteto-ejc` |
| Novos módulos/features | `arquiteto-modulos-ejc` |
| Deploy/Docker/VPS/Nginx | `arquiteto-docker-deploy` |
| CI/CD automático | `arquiteto-ci-cd` |
| Banco/migrations | `gestor-migracao-banco` |
| Backup/recovery | `gestor-backup-recuperacao` |
| Notificações/alertas | `arquiteto-notificacoes` → `integrador-whatsapp-business` |
| APIs externas (TJMG, PJe) | `integrador-apis-externas-ejc` |
| Automação n8n | `arquiteto-automacao-n8n` |
| IA/RAG jurídico | `gestor-rag-ia-juridica` → `orquestrador-celery-redis` |
| Testes | `arquiteto-testes-ejc` → `debugger-sistematico` |
| Monitoramento | `arquiteto-monitoramento-observabilidade` |
| Segurança/LGPD | `auditor-lgpd-etica` |

## Regra de Ouro
Toda decisão técnica deve ser feita com base no código real existente — nunca assumir estrutura sem verificar. Antes de qualquer mudança, acionar `arquiteto-ejc` para auditoria do contexto.
