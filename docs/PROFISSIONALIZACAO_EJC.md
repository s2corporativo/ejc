# Profissionalização do EJC

Este documento define regras mínimas para evoluir o EJC como produto jurídico interno, com segurança, estabilidade e governança.

## Regras centrais

1. Não alterar direto na main.
2. Toda mudança deve passar por branch, Pull Request e CI.
3. Backend é a fonte real de permissão; frontend apenas melhora a experiência visual.
4. Rotas sensíveis exigem autenticação, autorização e regra de ownership.
5. Alterações de banco devem usar migration Alembic.
6. Módulos novos só podem ser criados após verificar se já existe módulo equivalente.
7. IA jurídica deve sugerir e fundamentar, não decidir sem revisão humana.
8. Documento, financeiro, estratégia jurídica, auditoria e IA são áreas sensíveis.
9. Portal do cliente só pode mostrar dados do próprio cliente e documentos liberados.
10. Pull Request sensível deve permanecer em draft até validação completa.

## Prioridades

1. Segurança e permissões.
2. Integridade dos dados.
3. Rotas e migrations estáveis.
4. Auditoria LGPD/OAB.
5. Teste real do fluxo do usuário.
6. Padronização visual.
7. Núcleo único de IA jurídica.
8. Novas funcionalidades.

## Critério de pronto

Uma alteração só está pronta quando o CI passa, as permissões foram revisadas, não há duplicidade de módulo, o fluxo afetado foi testado e as pendências críticas foram resolvidas ou registradas como bloqueio de merge.
