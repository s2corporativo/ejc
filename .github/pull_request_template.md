## Objetivo

Descreva o problema, o comportamento esperado e o impacto jurídico/operacional.

## Escopo

- [ ] Alteração pequena e coesa
- [ ] Sem credenciais, dados pessoais ou documentos reais
- [ ] Sem deploy direto ou mudança manual não registrada

## Segurança e dados

- [ ] Ownership/RBAC/ABAC revisados
- [ ] LGPD e exposição de metadados avaliadas
- [ ] Logs e erros não revelam segredos ou PII
- [ ] Migração possui estratégia de rollback/compatibilidade

## Evidências

- [ ] Testes adicionados ou atualizados
- [ ] CI completo aprovado
- [ ] P0 Guard aprovado
- [ ] Continuity and UI Gates aprovado
- [ ] Evidência manual anexada quando a mudança exigir interação humana

## Banco e continuidade

- [ ] `alembic upgrade head` validado
- [ ] Backup/restore considerado antes de alteração destrutiva
- [ ] Nenhum `DROP`, exclusão física ou cutover irreversível sem plano aprovado

## Rollback

Explique como reverter código, configuração e banco com segurança.
