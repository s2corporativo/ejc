# CI sem dependência de GitHub-hosted

## Princípio

O EJC mantém o GitHub como repositório e plano de controle, mas não deve depender
exclusivamente de runners `ubuntu-latest` para validar PRs. Quando o GitHub-hosted
falhar antes do primeiro step, a validação pode migrar para um runner self-hosted
**dedicado e separado da produção**.

> Regra de segurança: código de PR/branch não confiável nunca executa no runner
> `ejc-vps`, no host `/opt/ejc` ou em qualquer máquina que contenha banco,
> uploads, backups ou `.env` de produção.

## CI local canônico

`scripts/ci-local.sh` continua disponível para validação em máquina de
desenvolvimento ou host de CI isolado:

```bash
scripts/ci-local.sh            # backend + banco efêmero + frontend
scripts/ci-local.sh backend    # backend com banco
scripts/ci-local.sh frontend   # frontend
scripts/ci-local.sh fast       # backend rápido, sem banco
```

O PostgreSQL usado pelo CI é efêmero e utiliza `pgvector/pgvector:pg16` quando
Docker está disponível.

## Fallback completo isolado

`scripts/ci-fallback.sh` é o gate de contingência. Ele cobre as famílias dos
gates oficiais: Release Gate P0, Architecture Inventory, PostgreSQL+pgvector,
Alembic, Ruff, pip-audit, pytest com cobertura mínima, gold sets, Prettier,
Vitest, npm audit, ESLint, build, Chromium responsivo e restore drill.

O script falha fechado se detectar sinais de produção, incluindo:

- `APP_ENV=production`;
- `/opt/ejc/.env`;
- `/opt/ejc/.deployed_sha`;
- workspace sob `/opt/ejc`;
- containers `ejc_backend`, `ejc_db`, `ejc_frontend` ou `ejc_worker`.

Não existe opção documentada de bypass desses guardas.

## Runner dedicado `ejc-ci`

O bootstrap seguro é:

```bash
scripts/setup-ci-fallback-runner.sh
```

Ele deve ser executado somente em VM/PC Linux separado da produção. O runner usa
as labels:

```text
self-hosted, linux, ejc-ci, ejc-ci-isolado
```

O usuário do runner não recebe `NOPASSWD`. Docker, Node, Python, PostgreSQL
client e Chromium são preparados no host durante o bootstrap.

Para registrar sem copiar manualmente o token temporário, o bootstrap aceita um
`GH_TOKEN` fornecido apenas no ambiente, com permissão suficiente para solicitar
`actions/runners/registration-token`. O token não deve ser gravado em arquivo,
issue, commit ou log. Também é possível fornecer `RUNNER_TOKEN` temporário.

## Automação de contingência

`.github/workflows/ci-fallback-selfhosted.yml` observa o workflow `CI`. O fallback
automático só roda quando a API comprova que o CI falhou e nenhum job iniciou
steps. Se qualquer step tiver executado, a falha é tratada como falha real de
código/teste e não é mascarada.

O workflow também:

- recusa forks e repositórios externos;
- faz checkout do SHA exato;
- usa `persist-credentials:false`;
- exige o runner `ejc-ci-isolado`;
- publica artifact de evidência vinculado ao SHA.

## Separação entre CI e produção

- `ejc-ci`: valida código de PR/branch em host isolado;
- `ejc-vps`: deploy, backup e operações controladas de produção;
- nunca reutilizar `ejc-vps` como fallback de CI;
- nunca montar `.env`, uploads, backups ou `/opt/ejc` no runner `ejc-ci`.

## Rollback

Para remover a contingência, reverta o PR que adicionou o workflow/scripts e
desregistre o runner `ejc-ci`. Nenhuma migration ou dado de produção é afetado.
