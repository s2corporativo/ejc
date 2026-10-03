# Plano de validação — lifecycle de módulos

## Cenários funcionais

1. Sem override:
   - o módulo segue o manifesto frontend;
   - nenhuma consulta ao banco altera o RBAC.

2. Status `hidden`:
   - o módulo desaparece do menu;
   - a URL direta continua acessível;
   - endpoints continuam sujeitos ao RBAC.

3. Status `disabled` sem substituição:
   - o menu não exibe o módulo;
   - a URL apresenta indisponibilidade;
   - nenhum dado é excluído.

4. Status `disabled` com substituição:
   - a URL redireciona apenas para rota interna;
   - URLs externas e `//host` são rejeitadas.

5. Reset:
   - o override é excluído;
   - o comportamento retorna ao manifesto versionado.

6. Módulo protegido:
   - Dashboard, Configurações, Usuários, Auditoria e Mapa de Módulos não podem ser desabilitados ou ocultados.

## Segurança

- [ ] feature flag não concede permissão;
- [ ] usuário sem role continua recebendo 403 no backend;
- [ ] alteração gera audit log;
- [ ] rota substituta não aceita destino externo;
- [ ] falha ao carregar overrides não derruba o EJC;
- [ ] nenhum segredo operacional é armazenado na tabela.

## Banco e rollback

- [ ] upgrade 080 → 081;
- [ ] downgrade 081 → 080;
- [ ] tabela isolada de dados jurídicos;
- [ ] backup obrigatório antes de downgrade em produção.
