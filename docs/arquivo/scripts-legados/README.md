# Scripts legados de deploy — ARQUIVADOS em 2026-09-06 (INF-03)

Estes scripts contornavam os gates da esteira (sem mutex, sem backup cifrado
obrigatório, sem classificação de migration, `pg_dump` em claro,
`git reset --hard` no checkout de produção). Ficam aqui só como histórico e
**não devem ser executados**.

| Script | Substituto |
|---|---|
| `deploy.sh`, `deploy-vps.sh` | primeira instalação: `scripts/vps_setup.sh` com `FIRST_INSTALL=1`; atualizações: `RUNBOOK_DEPLOY_MANUAL.md` |
| `atualizar-vps.sh` | `scripts/deploy_manual.sh --sha <SHA>` (manual) ou `infra/host-automation/ejc-deploy-approved.sh` (automático) |
