# CI fora do GitHub Actions — fallback autônomo do EJC

## Objetivo

O GitHub continua sendo a fonte de verdade para código, Issues, Pull Requests, status e histórico. O que deixa de ser dependência única é o **GitHub Actions/runner como executor de CI**.

Durante indisponibilidade, fila sem runner ou job encerrado antes do primeiro step, o EJC pode validar o SHA em uma **máquina de desenvolvimento/homologação**, dentro de `git worktree` isolado, com PostgreSQL 16 + pgvector efêmero. Produção não participa da execução.

A autorização administrativa deste fallback está registrada na **Issue #998**.

## Regra de autonomia

Quando GitHub/Actions falhar por infraestrutura, o agente não deve pedir ao titular que escolha manualmente outra rota. O procedimento é:

1. classificar infraestrutura x falha real de código;
2. continuar trabalho/diagnóstico em cópia ou worktree isolado;
3. executar o gate local equivalente;
4. corrigir localmente até verde;
5. preservar evidência por SHA;
6. sincronizar status/PR quando a API GitHub estiver disponível;
7. nunca reduzir branch protection, reviews, CODEOWNERS ou controles jurídicos para “destravar” o fluxo.

Não criar `postinstall`, dependência, workflow, hook ou commit temporário apenas para fazer o Actions revelar um diagnóstico reproduzível localmente.

## `scripts/ci-local.sh`

Reproduz os gates críticos fora do Actions:

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

### Runtime hermético

O modo promovível exige Python 3.11 e Node 22. `EJC_ALLOW_PYTHON_MISMATCH=1` existe apenas para diagnóstico; `scripts/ci-fallback.sh` recusa publicar status promovível quando essa variável estiver ativa.

O venv Python padrão é identificado por:

- versão exata do Python; e
- SHA-256 de `backend/requirements.txt`.

Assim, uma mudança de requirements cria outro ambiente e impede que pacote removido sobreviva silenciosamente de uma validação anterior. `CI_SKIP_PIP=1` só funciona quando o venv correspondente já existe; caso contrário, falha fechado.

### Isolamento

Estado operacional, venv, PGDATA, relatórios, screenshots e restore report ficam fora do repositório, sob o cache do usuário. O PostgreSQL efêmero escolhe porta livre e publica somente no loopback (`127.0.0.1`). `pip-audit` usa a versão fixada pelo CI cloud (`2.10.0`).

O script recusa:

- `/opt/ejc` e host com marcadores da instalação produtiva;
- `APP_ENV=production` ou `EJC_ENV=production`;
- containers canônicos `ejc_backend`, `ejc_worker`, `ejc_db`, `ejc_frontend`, `ejc_redis` ativos;
- execução promovível como root.

Limpeza temporária é restrita ao `STATE_ROOT` e não usa `rm -rf`.

O gate de browser instala Chromium sem `--with-deps`. Dependência de sistema ausente reprova fechada, em vez de executar `sudo/apt` silenciosamente.

## Worktree isolado e evidência por SHA

`scripts/ci-fallback.sh --pr <N>`:

1. atualiza `origin/main`;
2. resolve o SHA exato do PR;
3. exige que a `main` atual seja ancestral do SHA;
4. cria worktree descartável fora do checkout principal;
5. executa backend, eval, frontend, P0, governança, arquitetura, continuidade e UI responsiva;
6. guarda logs somente na máquina local, com permissão restrita;
7. grava `summary.json` com SHA exato, resultado e hashes/tamanhos dos logs;
8. revalida a governança do **corpo atual do PR** imediatamente antes da promoção;
9. publica commit status por SHA quando a API estiver disponível;
10. remove o worktree ao final.

O resumo fica em `~/.cache/ejc-ci-evidence/<sha>/summary.json`. Nenhum status obrigatório fica verde parcialmente.

## Namespace de status local

Statuses locais têm namespace próprio e **nunca reutilizam nomes do GitHub Actions**:

```text
EJC Local / Backend
EJC Local / Eval
EJC Local / Frontend
EJC Local / P0 Guard
EJC Local / Governança
EJC Local Full Gate
```

A branch protection em contingência exige somente `EJC Local Full Gate`. Os cinco checks canônicos do Actions continuam exclusivos do modo `--cloud`. Isso impede que um verde local antigo satisfaça acidentalmente um check cloud depois da restauração.

## API GitHub indisponível durante a suíte

Falha ao publicar `pending`, `success` ou `failure` **não interrompe testes locais já em andamento**. O fallback registra a sincronização pendente, preserva a evidência e termina a prova local.

Isso não produz falso verde: branch protection continua exigindo um status remoto antes do merge. Quando a API voltar, a evidência do mesmo SHA pode ser promovida sem repetir a suíte pesada.

## `--promote-only` e `--merge-only`

Metadados do PR podem mudar sem novo commit. Por isso:

### `--promote-only`

- exige `summary.json` local com `target_sha` idêntico e `result=success`;
- reexecuta a governança contra o corpo atual do PR;
- republica status;
- **nunca tenta merge**.

### `--merge-only`

Além das regras acima:

- confirma que o PR continua no mesmo SHA;
- respeita draft e `retencao-humana`;
- retém caminhos de exceção §6-A;
- retém migration potencialmente destrutiva;
- depende de review, CODEOWNERS, branch protection e demais requisitos remotos;
- merge usa o SHA esperado.

Assim, mudança de descrição/labels/review não herda autorização antiga e não exige repetir backend/frontend quando o código permaneceu idêntico.

## Retry automático somente para infraestrutura

O watcher pode repetir o **mesmo SHA** apenas quando o log da tentativa atual contém assinatura inequívoca de falha externa, como:

- DNS/registry (`Could not resolve host`, `EAI_AGAIN`);
- reset/timeout (`ECONNRESET`, `ETIMEDOUT`);
- indisponibilidade qualificada de registry/API (`429`, `502`, `503`, `504` associada à operação externa).

O retry tem backoff exponencial e limite de tentativas. Falha de pytest, Ruff, Vitest, typecheck ou build sem assinatura externa é tratada como falha real e fica retida até novo SHA, salvo opt-in operacional explícito.

Retry nunca produz sucesso por si só.

## Branch protection em contingência

O modo normal exige os cinco contexts do Actions. Em contingência:

```bash
EJC_FALLBACK_AUTHORIZATION=998 \
  bash scripts/governanca/branch-protection.sh --fallback
```

`--fallback` é **ATO ADMINISTRATIVO PROTEGIDO**. Sem `EJC_FALLBACK_AUTHORIZATION=998`, a alteração é recusada. O ativador canônico injeta essa autorização porque a decisão está registrada na Issue #998.

O fallback muda somente o contexto obrigatório para:

```text
EJC Local Full Gate
```

Permanecem ativos:

- `strict=true`;
- `enforce_admins=true`;
- review obrigatório;
- CODEOWNERS;
- aprovação do último push;
- conversas resolvidas;
- histórico linear;
- force-push proibido;
- deleção da branch protegida proibida.

Restauração cloud:

```bash
bash scripts/governanca/branch-protection.sh --cloud
```

Cada alteração salva backup em `var/`, já ignorado pelo Git.

## Watcher autônomo

`scripts/ci-fallback-watch.sh` percorre PRs abertos e não-draft para `main`.

- SHA novo sem evidência → valida;
- falha real de código/teste → não repete indefinidamente;
- falha classificada como infraestrutura → retry limitado com backoff;
- `summary.json` aprovado → suíte pesada não repete;
- com `EJC_FALLBACK_AUTO_MERGE=1`, evidência aprovada usa `--merge-only`;
- com `EJC_FALLBACK_AUTO_MERGE=0`, usa `--promote-only`, portanto nunca tenta integrar;
- API/fetch fora → daemon permanece vivo, sem converter indisponibilidade em sucesso;
- `main` local só avança por `git merge --ff-only origin/main` quando limpa.

O watcher não usa VPS de produção e não instala GitHub runner.

## Ativação persistente e reversível

Em máquina **não produtiva** com clone autenticado:

```bash
bash scripts/ci-fallback-activate.sh --enable
```

A ativação só prossegue depois de:

1. recusar `/opt/ejc`, root, containers canônicos e ambiente de produção;
2. exigir checkout limpo da `main`, idêntico a `origin/main`;
3. validar `git`, `gh`, `jq`, Python 3.11, Node 22, npm, psql e Docker;
4. comprovar scheduler persistente;
5. validar sintaxe dos componentes;
6. executar `scripts/ci-local.sh fast` com Python canônico;
7. ativar pre-push;
8. aplicar branch protection fallback com autorização #998;
9. instalar e confirmar o watcher.

### Scheduler

O ativador prefere **cron/crond quando o daemon está comprovadamente ativo**. Se não houver cron persistente, aceita `systemd --user` somente quando `loginctl ... Linger=yes`, evitando dependência de sessão humana aberta.

O PATH do watcher é injetado explicitamente no scheduler. PATH, ROOT, LOG_DIR e REPO com caracteres de quoting ambíguo são recusados. Sem scheduler persistente, a ativação falha **antes** de tocar a branch protection.

Se qualquer etapa falhar após a troca da proteção, o ativador tenta restaurar automaticamente `--cloud`.

Desativação:

```bash
bash scripts/ci-fallback-activate.sh --disable
```

A desativação restaura **primeiro** a branch protection cloud e só depois encerra o watcher. Se GitHub/API impedir a restauração, o watcher permanece ativo para não deixar a `main` exigindo um gate sem executor.

## Governança local

`scripts/governanca/ci-local-governanca.sh` replica travas objetivas de migration, segredo, descrição do PR, Issue vinculada e branch protegida.

São superfícies sensíveis, entre outras:

- workflows;
- `scripts/ci-local.sh`;
- `scripts/ci-fallback*.sh`;
- `scripts/governanca/branch-protection.sh`;
- `scripts/governanca/ci-local-governanca.sh`;
- autenticação e uploads.

Mudança nessas áreas exige registro literal `security-auditor: executado` antes de status promovível.

## Segurança e LGPD

- nunca rodar fallback em `/opt/ejc` ou host produtivo;
- não apontar `DATABASE_URL` para produção;
- PostgreSQL efêmero, loopback-only e com massa de teste;
- não versionar token/credencial; `gh` usa autenticação existente no host;
- logs completos permanecem locais;
- falha de pré-requisito, banco, lint, teste, auditoria, restore ou browser é bloqueante;
- nenhuma migration destrutiva é promovida automaticamente;
- fallback não substitui HITL, RBAC, LGPD, citation gate nem revisão independente;
- status local e cloud usam nomes distintos;
- branch protection fallback só pode ser alterada sob autorização #998.

## Risco residual do commit status externo

Para não criar nova GitHub App/segredo persistente, a contingência usa commit status clássico. Uma identidade com permissão suficiente no repositório pode, em tese, tentar publicar o mesmo contexto local. Por isso o fallback mantém como controles independentes:

- review/CODEOWNERS;
- aprovação do último push;
- `strict=true`;
- conversa resolvida;
- SHA exato;
- exceções §6-A;
- retenção de migrations destrutivas.

Quando Actions normalizar, `--cloud` restaura os cinco contexts canônicos, que não colidem com os nomes locais.

## GitHub Actions durante a contingência

Os workflows permanecem habilitados como evidência adicional. Um X de job que morreu antes do primeiro step (`steps=null`) é classificado como falha do executor, não como reprovação do código.

Enquanto a proteção estiver em modo fallback, a promoção depende de `EJC Local Full Gate`; ao retornar para cloud, depende novamente apenas dos cinco checks canônicos do Actions.

## Bootstrap desta implementação

A própria PR que introduz o fallback altera `scripts/` e branch protection. Por segurança, ela é tratada como exceção §6-A e **não deve auto-integrar a si própria usando o mecanismo que ainda não existe na `main`**.

O primeiro bootstrap exige uma destas condições:

- os checks cloud voltarem a executar e aprovarem a PR; ou
- um host Linux não produtivo autorizado executar a validação e o procedimento administrativo de bootstrap, preservando reviews e branch protection.

Não usar admin bypass nem reduzir proteções apenas para bootstrap.