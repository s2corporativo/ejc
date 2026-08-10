# CI fora do GitHub Actions — fallback autônomo do EJC

## Objetivo

O GitHub continua sendo a fonte de verdade para código, Issues, Pull Requests e histórico. O que deixa de ser dependência única é o **GitHub Actions como executor de CI**.

Durante indisponibilidade, fila sem runner ou falha anterior ao primeiro step, o EJC pode validar o SHA em uma **máquina de desenvolvimento/homologação**, dentro de um `git worktree` isolado, com PostgreSQL 16 + pgvector efêmero. Produção não participa da execução.

A decisão do titular está registrada na Issue #998.

## Componentes

### `scripts/ci-local.sh`

Reproduz os gates atuais fora do Actions:

```bash
bash scripts/ci-local.sh backend       # Postgres/pgvector, Alembic, RAG, Ruff, pip-audit, pytest + cobertura
bash scripts/ci-local.sh eval          # gold sets + trajetória do agente, offline
bash scripts/ci-local.sh frontend      # npm ci, Prettier, Vitest, npm audit e build
bash scripts/ci-local.sh p0            # ci_guard + backup/rollback/runner tests
bash scripts/ci-local.sh architecture  # inventário e testes de arquitetura
bash scripts/ci-local.sh continuity    # backup cifrado + restore drill
bash scripts/ci-local.sh ui-extra      # ESLint + Chromium responsivo
bash scripts/ci-local.sh full          # todos os blocos acima
bash scripts/ci-local.sh fast          # diagnóstico rápido pré-push
```

O modo promovível exige, por padrão, Python 3.11, Node 22, `psql`, Docker e dependências bloqueadas do projeto. Incompatibilidade de runtime falha fechada; `EJC_ALLOW_PYTHON_MISMATCH=1` existe apenas para diagnóstico e não deve ser usado como evidência de promoção.

## Worktree isolado e evidência por SHA

`scripts/ci-fallback.sh --pr <N>`:

1. atualiza `origin/main`;
2. resolve o SHA exato do PR;
3. exige que a `main` atual seja ancestral do SHA (`strict=true` equivalente);
4. cria worktree descartável fora do checkout principal;
5. executa backend, eval, frontend, P0, governança, arquitetura, continuidade e UI responsiva;
6. guarda logs somente na máquina local, com permissão restrita;
7. publica apenas status/resumo mínimo por SHA;
8. remove o worktree ao final.

Nenhum status obrigatório fica verde parcialmente: os contextos de sucesso só são publicados depois que **todo o fallback completo** termina com exit 0.

O resumo local fica em `~/.cache/ejc-ci-evidence/<sha>/summary.json`, contendo hashes SHA-256 e tamanho dos logs — não o conteúdo deles.

## Branch protection em contingência

A proteção normal exige os cinco contexts do Actions. Em contingência, `scripts/governanca/branch-protection.sh --fallback` troca **somente o executor obrigatório** para:

```text
EJC Local Full Gate
```

O status é aceito como CI externo. Permanecem inalterados:

- `strict=true` (branch atualizada);
- `enforce_admins=true`;
- review obrigatório;
- CODEOWNERS;
- aprovação do último push;
- conversas resolvidas;
- histórico linear;
- force-push proibido;
- deleção da branch protegida proibida.

O modo fallback usa `app_id=-1` para não vincular o contexto ao aplicativo GitHub Actions.

Para restaurar o executor em nuvem:

```bash
bash scripts/governanca/branch-protection.sh --cloud
```

Cada alteração de proteção salva uma cópia anterior em `var/`, que já é ignorado pelo Git.

## Watcher autônomo

`scripts/ci-fallback-watch.sh` percorre PRs abertos e não-draft para `main`.

- um SHA novo é validado uma vez;
- SHA reprovado não entra em loop infinito;
- novo commit gera novo SHA e nova validação;
- quando `EJC_FALLBACK_AUTO_MERGE=1`, o watcher solicita merge depois do gate completo;
- branch protection/reviews continuam sendo a autoridade final;
- caminhos de exceção da Governança §6-A e migrations potencialmente destrutivas continuam retidos.

O watcher não usa a VPS de produção e não instala runner do GitHub.

## Ativação reversível

Em uma máquina **não produtiva** com clone autenticado do EJC:

```bash
bash scripts/ci-fallback-activate.sh --enable
```

A ativação:

1. recusa `/opt/ejc`, `root` e ambiente marcado como produção;
2. verifica `git`, `gh`, `jq`, Python 3.11, Node 22, npm, psql e Docker;
3. ativa `.githooks` para o pré-push;
4. muda a branch protection para `EJC Local Full Gate`;
5. instala o watcher no usuário, via `systemd --user` ou `crontab`;
6. inicia o acompanhamento automático.

Desativação:

```bash
bash scripts/ci-fallback-activate.sh --disable
```

Ela para o watcher e restaura a política cloud de branch protection.

## Segurança e LGPD

- nunca rodar em `/opt/ejc`;
- não apontar `DATABASE_URL` para produção;
- PostgreSQL é efêmero e recebe somente massa de teste;
- não versionar token ou credencial; `gh` usa a autenticação já existente no host;
- logs completos não são enviados ao GitHub pelo fallback;
- falha de pré-requisito, banco, teste, lint, auditoria, restore ou browser é bloqueante;
- nenhuma migration destrutiva é promovida automaticamente;
- o fallback não substitui HITL, RBAC, LGPD, citation gate ou revisão independente.

## GitHub Actions durante a contingência

Os workflows podem permanecer habilitados e funcionar como evidência adicional quando houver runner. Um X decorrente de job que não chegou ao primeiro step não é tratado como falha de aplicação. A promoção depende do `EJC Local Full Gate` enquanto a branch protection estiver no modo fallback.

Assim não é necessário editar os workflows a cada incidente e a reversão para o modo cloud é imediata.
