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

O script recusa host com marcadores de produção em `/opt/ejc`, containers canônicos do EJC ativos ou ambiente `production`. O PostgreSQL efêmero em Docker publica a porta somente no loopback (`127.0.0.1`).

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

`--merge-only` permite reavaliar aprovação/branch protection do mesmo SHA depois de a suíte já ter passado, sem repetir testes pesados. O merge continua sujeito às proteções do GitHub e ao SHA esperado.

## Branch protection em contingência

A proteção normal exige os cinco contexts do Actions. Em contingência, `scripts/governanca/branch-protection.sh --fallback` mantém o mesmo mecanismo clássico de `contexts` já usado pelo EJC e troca **somente o contexto obrigatório** para:

```text
EJC Local Full Gate
```

Esse commit status é produzido pelo fallback somente após a suíte integral. Permanecem inalterados:

- `strict=true` (branch atualizada);
- `enforce_admins=true`;
- review obrigatório;
- CODEOWNERS;
- aprovação do último push;
- conversas resolvidas;
- histórico linear;
- force-push proibido;
- deleção da branch protegida proibida.

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
- SHA já aprovado não repete a suíte e apenas reavalia merge;
- falha da API/fetch não mata o watcher e nunca vira sucesso;
- a cópia local da `main` só avança por `git merge --ff-only origin/main` e apenas quando está limpa;
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

1. recusa `/opt/ejc`, `root`, containers canônicos e ambiente marcado como produção;
2. exige checkout limpo da `main`, exatamente igual a `origin/main`;
3. verifica `git`, `gh`, `jq`, Python 3.11, Node 22, npm, psql e Docker;
4. confirma que existe `systemd --user` ou `crontab` antes de tocar a branch protection;
5. ativa `.githooks` para o pré-push;
6. muda a branch protection para `EJC Local Full Gate`;
7. instala e confirma o watcher;
8. se a instalação do watcher falhar depois da troca de proteção, tenta restaurar automaticamente o modo cloud.

Desativação:

```bash
bash scripts/ci-fallback-activate.sh --disable
```

A desativação restaura **primeiro** a branch protection cloud e só então encerra o watcher. Se o GitHub/API estiver indisponível e a proteção não puder ser restaurada, o watcher permanece ativo em vez de deixar a `main` esperando um gate sem executor.

## Segurança e LGPD

- nunca rodar em `/opt/ejc` nem em host com marcadores/containers canônicos de produção;
- não apontar `DATABASE_URL` para produção;
- PostgreSQL é efêmero, loopback-only e recebe somente massa de teste;
- não versionar token ou credencial; `gh` usa a autenticação já existente no host;
- logs completos não são enviados ao GitHub pelo fallback;
- falha de pré-requisito, banco, teste, lint, auditoria, restore ou browser é bloqueante;
- nenhuma migration destrutiva é promovida automaticamente;
- o fallback não substitui HITL, RBAC, LGPD, citation gate ou revisão independente.

### Risco residual do status externo

Para evitar provisionar uma nova GitHub App/segredo persistente, a contingência usa um contexto clássico de status, igual ao modelo de `contexts` já utilizado pela proteção atual. Uma identidade com permissão suficiente de escrita/status no repositório pode, em tese, tentar publicar o mesmo contexto. Por isso o fallback **não remove** review, CODEOWNERS, aprovação do último push, `strict=true`, conversa resolvida nem SHA exato. Quando o Actions normalizar, `--cloud` restaura imediatamente os cinco contexts originais.

## GitHub Actions durante a contingência

Os workflows podem permanecer habilitados e funcionar como evidência adicional quando houver runner. Um X decorrente de job que não chegou ao primeiro step não é tratado como falha de aplicação. A promoção depende do `EJC Local Full Gate` enquanto a branch protection estiver no modo fallback.

Assim não é necessário editar os workflows a cada incidente e a reversão para o modo cloud é imediata.
