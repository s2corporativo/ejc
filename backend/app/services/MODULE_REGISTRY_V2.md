# Mapa de Módulos v2

Esta evolução amplia o registro declarativo do EJC para cobrir os principais módulos do menu e routers críticos.

A alteração é somente declarativa e não cria migration.

Campos por módulo:

- module_key
- nome
- grupo
- frontend_route
- backend_prefixes
- status
- perfis
- dependencias
- usa_ia
- dados_sensiveis
- responsavel_operacional
- responsavel_tecnico

Objetivo:

- melhorar governança modular;
- identificar módulos sem endpoint detectado;
- identificar módulos sem manual;
- classificar módulos que usam IA;
- classificar módulos que tratam dados sensíveis;
- preparar futura tela de edição e feature flags.
