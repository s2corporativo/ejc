# Matriz de Permissões do EJC

Esta matriz orienta implementação, revisão e testes. Em caso de conflito, o backend deve bloquear o acesso.

Perfis oficiais:

- superadmin
- admin
- socio
- advogado
- advogado_auxiliar
- estagiario
- financeiro
- cliente_externo

## Módulos e acesso esperado

| Módulo | Perfis com acesso | Observação |
|---|---|---|
| Dashboard | autenticados internos | Cliente externo deve usar portal próprio. |
| Clientes | superadmin, admin, socio, advogado, advogado_auxiliar, estagiario | Respeitar ownership quando aplicável. |
| Casos | superadmin, admin, socio, advogado, advogado_auxiliar, estagiario | Advogado/auxiliar/estagiário só devem ver casos permitidos. |
| Processos/DataJud | superadmin, admin, socio, advogado, advogado_auxiliar, estagiario | Não expor estratégia interna ao cliente externo. |
| Prazos | superadmin, admin, socio, advogado, advogado_auxiliar, estagiario | Bloquear exclusões indevidas. |
| Tarefas/Agenda | superadmin, admin, socio, advogado, advogado_auxiliar, estagiario | Escopo por responsável/equipe quando aplicável. |
| Documentos | superadmin, admin, socio, advogado, advogado_auxiliar, estagiario | Validar ownership, confidencialidade e auditoria. |
| Documentos confidenciais | superadmin, admin, socio | Exige trilha de auditoria. |
| Financeiro consolidado | superadmin, admin, socio, financeiro | Não expor a advogado comum ou estagiário. |
| Despesas | superadmin, admin, socio, financeiro | Exportação é ação sensível. |
| Sociedade | superadmin, admin, socio, financeiro | Dados societários são sensíveis. |
| Honorários | superadmin, admin, socio, advogado, financeiro | Advogado comum só quando houver regra de caso permitida. |
| Auditoria | superadmin, admin, socio | Não expor logs a perfis operacionais. |
| Usuários/configurações | superadmin, admin | Criação de usuário deve exigir troca de senha. |
| IA jurídica | superadmin, admin, socio, advogado, advogado_auxiliar, estagiario | Respeitar escopo do caso e registrar uso. |
| Base de conhecimento | superadmin, admin, socio | Pode conter teses e material interno. |
| Governança IA | superadmin, admin, socio | Deve controlar logs, fontes e revisão humana. |
| Portal do cliente | cliente_externo | Apenas próprios casos, documentos liberados e financeiro próprio. |

## Regras obrigatórias de teste

1. Testar acesso autorizado.
2. Testar acesso negado por perfil.
3. Testar acesso negado por ownership.
4. Testar cliente externo tentando acessar rota interna.
5. Testar documento confidencial com perfil sem permissão.
6. Testar exportações financeiras.
7. Testar menu visual e rota backend separadamente.

## Regra de ouro

Se o menu mostra algo que o backend bloqueia, é problema de UX.
Se o backend permite algo que deveria bloquear, é falha de segurança.
