# Lifecycle e feature flags de módulos — EJC

Data: 2026-07-10

## Finalidade

Permitir que a administração classifique um módulo como ativo, beta, oculto, legado ou desabilitado, sem alterar o RBAC e sem remover código ou dados de forma imediata.

## Princípios

- Feature flag não concede autorização.
- O backend continua sendo a autoridade para autenticação e RBAC.
- A ausência de override mantém o manifesto versionado como fonte padrão.
- Falha ao carregar overrides não derruba o sistema: o frontend usa fail-open operacional e preserva o manifesto.
- Módulos estruturais não podem ser ocultados ou desabilitados pela interface.
- Rotas substitutas aceitam somente caminhos internos iniciados por `/`.
- Toda criação, alteração ou reset é auditada.

## Estados

- `active`: módulo disponível normalmente.
- `beta`: módulo disponível em validação.
- `hidden`: módulo habilitado, fora do menu, acessível por link direto.
- `legacy`: módulo mantido durante transição.
- `disabled`: módulo bloqueado; pode redirecionar para uma rota substituta interna.

## Persistência

Migration: `081_system_module_settings.py`

Tabela: `system_module_settings`

Campos principais:

- `module_key`
- `enabled`
- `menu_visible`
- `status`
- `replacement_route`
- `removal_date`
- `reason`
- `updated_by`
- timestamps

## Fluxo técnico

1. O manifesto frontend define o catálogo padrão.
2. O endpoint `/api/system-modules/settings` retorna apenas overrides.
3. O menu filtra módulos ocultos ou desabilitados.
4. O gate de rota bloqueia módulos desabilitados ou redireciona para a substituição configurada.
5. O RBAC do endpoint continua obrigatório, independentemente do estado da feature flag.

## Rollback

### Código

Reverter o squash commit do PR correspondente.

### Banco

Antes de downgrade em produção:

```bash
git status
./scripts/backup.sh
docker compose exec backend alembic current
docker compose exec backend alembic downgrade 080_notification_preferences
docker compose exec backend alembic current
```

O downgrade remove somente os overrides de lifecycle. Não remove módulos, documentos ou dados jurídicos.

## Critérios de validação

- [ ] Um módulo oculto não aparece no menu.
- [ ] Um módulo oculto continua acessível por URL direta.
- [ ] Um módulo desabilitado bloqueia a rota.
- [ ] Uma rota substituta interna redireciona corretamente.
- [ ] Uma rota externa é rejeitada.
- [ ] Dashboard, Configurações, Usuários e Auditoria permanecem protegidos.
- [ ] RBAC do backend continua funcionando.
- [ ] Alterações aparecem na auditoria.
- [ ] Migration possui upgrade e downgrade.
- [ ] Workflow final permanece com `contents: read`.
