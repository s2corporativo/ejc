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
bash scripts/ci-local.sh continuity    # schema migrado + backup cifrado + restore drill
bash scripts/ci-local.sh ui-extra      # ESLint + Chromium responsivo
bash scripts/ci-local.sh full          # todos os blocos acima
bash scripts/ci-local.sh fast          # diagnóstico rápido pré-push/preflight
```

O modo promovível exige Python 3.11 e Node 22. Incompatibilidade de runtime falha fechada. `EJC_ALLOW_PYTHON_MISMATCH=1` existe apenas para diagnóstico; `scripts/ci-fallback.sh` recusa explicitamente publicar status promovível quando essa variável estiver ativa.

Estado operacional, venv, PGDATA, relatórios, screenshots e restore report ficam fora do repositório, sob o cache do usuário por padrão. O PostgreSQL efêmero escolhe porta livre e publica somente no loopback (`127.0.0.1`). `pip-audit` usa a mesma versão fixada pelo CI em nuvem (`2.10.0`).

O script recusa host com marcadores de produção em `/opt/ejc`, containers canônicos do EJC (`backend`, `worker`, `db`, `frontend`, `redis`) ativos ou ambiente `production`. Limpeza temporária é limitada ao diretório de estado do CI; não usa `rm -rf`.

O gate de browser instala o Chromium do Playwright sem `--with-deps`. Dependência de sistema ausente reprova fechada, em vez de permitir `sudo/apt` silencioso em execução autônoma.

## Worktree isolado e evidência por SHA

`scripts/ci-fallback.sh --pr <N>`:

1. atualiza `origin/main`;
2. resolve o SHA exato do PR;
3. exige que a `main` atual seja ancestral do SHA (`strict=true` equivalente);
4. cria worktree descartável fora do checkout principal;
5. executa backend, eval, frontend, P0, governança, arquitetura, continuidade e UI responsiva;
6. guarda logs somente na máquina local, com permissão restrita;
7. grava `summary.json` com SHA exato, resultado e hashes/tamanhos dos logs;
8. revalida a governança do **corpo atual do PR** imediatamente antes de promover status;
9. publica status por SHA quando a API estiver disponível;
10. remove o worktree ao final.

Nenhum status obrigatório fica verde parcialmente. `EJC Local Full Gate=success` só é publicado depois da suíte integral **e** da revalidação atual da governança.

O resumo local fica em `~/.cache/ejc-ci-evidence/<sha>/summary.json`. Ele é a evidência canônica de que a suíte pesada daquele SHA terminou. Os logs completos permanecem locais; o resumo contém hashes SHA-256 e tamanhos, não seu conteúdo.

### API GitHub falha no meio da suíte

A indisponibilidade da API para publicar `pending`/`success`/`failure` **não interrompe testes locais já em execução**. O fallback registra que a sincronização de status ficou pendente, preserva a evidência local e termina a validação. O watcher pode republicar posteriormente o resultado do mesmo SHA sem repetir a suíte pesada.

Isso não produz falso verde: branch protection continua exigindo o status remoto antes do merge.

### `--merge-only`

`--merge-only` não confia apenas em um status remoto antigo. Ele exige:

- `summary.json` local com `target_sha` idêntico e `result=success`;
- PR ainda aberto e no mesmo SHA;
- governança reexecutada contra o corpo atual do PR;
- ausência de retenção humana e demais exceções;
- branch protection/reviews satisfeitos.

Título, descrição, labels e reviews podem mudar sem novo commit. Por isso a governança é reavaliada em toda tentativa de merge, sem repetir backend/frontend quando o código não mudou.

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

- um SHA novo sem evidência é validado;
- falha real de código/teste não entra em loop infinito;
- novo commit gera novo SHA e nova validação;
- `summary.json` aprovado é a fonte para saber que a suíte pesada não precisa repetir;
- se a suíte passou mas status/API ou metadados mutáveis impediram promoção, o SHA continua marcado como código aprovado e o watcher executa `--merge-only` no ciclo seguinte;
- `--merge-only` revalida a governança atual e tenta republicar status sem repetir backend/frontend;
- falha da API/fetch não mata o watcher e nunca vira sucesso;
- a cópia local da `main` só avança por `git merge --ff-only origin/main` e apenas quando está limpa;
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
4. confirma que existe `systemd --user` ou `crontab`;
5. valida sintaxe de todos os componentes do fallback;
6. executa `scripts/ci-local.sh fast` com Python canônico **antes** de tocar a branch protection;
7. ativa `.githooks` para o pré-push;
8. muda a branch protection para `EJC Local Full Gate`;
9. instala e confirma o watcher com `EJC_ALLOW_PYTHON_MISMATCH=0`;
10. se qualquer passo após a troca falhar, tenta restaurar automaticamente o modo cloud.

Assim, a proteção nunca é apontada deliberadamente para um host que não passou nem pelo preflight local mínimo. O primeiro SHA de PR ainda precisa passar pela suíte completa para gerar `EJC Local Full Gate=success`.

Desativação:

```bash
bash scripts/ci-fallback-activate.sh --disable
```

A desativação restaura **primeiro** a branch protection cloud e só então encerra o watcher. Se o GitHub/API estiver indisponível e a proteção não puder ser restaurada, o watcher permanece ativo em vez de deixar a `main` esperando um gate sem executor.

## Governança local

`scripts/governanca/ci-local-governanca.sh` replica as travas objetivas de migration, segredo, descrição do PR, Issue vinculada e branch protegida. Também trata como superfície sensível:

- workflows;
- `scripts/ci-local.sh`;
- `scripts/ci-fallback*.sh`;
- `scripts/governanca/branch-protection.sh`;
- `scripts/governanca/ci-local-governanca.sh`;
- autenticação, uploads e outras portas de segurança já previstas.

Mudança nessas áreas exige registro literal `security-auditor: executado` antes de status promovível.

## Segurança e LGPD

- nunca rodar em `/opt/ejc` nem em host com marcadores/containers canônicos de produção;
- não apontar `DATABASE_URL` para produção;
- PostgreSQL é efêmero, loopback-only e recebe somente massa de teste;
- não versionar token ou credencial; `gh` usa autenticação já existente no host;
- logs completos não são enviados ao GitHub pelo fallback;
- falha de pré-requisito, banco, teste, lint, auditoria, restore ou browser é bloqueante;
- nenhuma migration destrutiva é promovida automaticamente;
- o fallback não substitui HITL, RBAC, LGPD, citation gate ou revisão independente.

### Risco residual do status externo

Para evitar provisionar uma nova GitHub App/segredo persistente, a contingência usa um contexto clássico de status, igual ao modelo de `contexts` já utilizado pela proteção atual. Uma identidade com permissão suficiente de escrita/status no repositório pode, em tese, tentar publicar o mesmo contexto. Por isso o fallback **não remove** review, CODEOWNERS, aprovação do último push, `strict=true`, conversa resolvida nem SHA exato. Quando o Actions normalizar, `--cloud` restaura imediatamente os cinco contexts originais.

## GitHub Actions durante a contingência

Os workflows podem permanecer habilitados e funcionar como evidência adicional quando houver runner. Um X decorrente de job que não chegou ao primeiro step não é tratado como falha de aplicação. A promoção depende do `EJC Local Full Gate` enquanto a branch protection estiver no modo fallback.

Assim não é necessário editar workflows a cada incidente e a reversão para o modo cloud é imediata.
