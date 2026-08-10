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
bash scripts/ci-local.sh backend
bash scripts/ci-local.sh eval
bash scripts/ci-local.sh frontend
bash scripts/ci-local.sh p0
bash scripts/ci-local.sh architecture
bash scripts/ci-local.sh continuity
bash scripts/ci-local.sh ui-extra
bash scripts/ci-local.sh full
bash scripts/ci-local.sh fast
```

### Runtime hermético

O modo promovível exige Python 3.11 e Node 22. `EJC_ALLOW_PYTHON_MISMATCH=1` existe apenas para diagnóstico; `scripts/ci-fallback.sh` recusa publicar evidência promovível quando essa variável estiver ativa.

O venv Python padrão é identificado por versão exata do Python e SHA-256 de `backend/requirements.txt`. Mudança de requirements cria outro ambiente; `CI_SKIP_PIP=1` só funciona quando o venv correspondente já existe.

### Isolamento

Estado operacional, venv, PGDATA, relatórios, screenshots e restore report ficam fora do repositório, sob o cache do usuário. O PostgreSQL efêmero escolhe porta livre e publica somente no loopback (`127.0.0.1`). `pip-audit` usa a versão fixada pelo CI cloud (`2.10.0`).

O script recusa `/opt/ejc`, host com marcadores da instalação produtiva, `APP_ENV/EJC_ENV=production`, containers canônicos do EJC ativos e execução promovível como root. Limpeza temporária é restrita ao `STATE_ROOT` e não usa `rm -rf`.

O gate de browser instala Chromium sem `--with-deps`. Dependência de sistema ausente reprova fechada, em vez de executar `sudo/apt` silenciosamente.

## Worktree isolado e evidência por SHA

`scripts/ci-fallback.sh --pr <N>`:

1. atualiza `origin/main`;
2. resolve o SHA exato do PR;
3. exige que a `main` atual seja ancestral do SHA;
4. valida **antes da suíte pesada** que a credencial usada por `gh` consegue criar Check Run e pertence ao `EJC_FALLBACK_APP_ID` esperado;
5. cria worktree descartável fora do checkout principal;
6. executa backend, eval, frontend, P0, governança, arquitetura, continuidade e UI responsiva;
7. guarda logs somente na máquina local, com permissão restrita;
8. grava `summary.json` com SHA exato, resultado e hashes/tamanhos dos logs;
9. revalida a governança do **corpo atual do PR** imediatamente antes da promoção;
10. publica o agregado `EJC Local Full Gate` como **Check Run do GitHub App dedicado**, vinculado ao `app_id`; os subgates locais usam commit status clássico apenas como observabilidade;
11. remove worktrees temporários, inclusive o worktree de revalidação de governança, ao final ou em saída antecipada.

O resumo fica em `~/.cache/ejc-ci-evidence/<sha>/summary.json`. Nenhum gate obrigatório fica verde parcialmente.

## Namespace de status local

Os subgates informativos usam namespace próprio:

```text
EJC Local / Backend
EJC Local / Eval
EJC Local / Frontend
EJC Local / P0 Guard
EJC Local / Governança
```

O único gate promovível é:

```text
EJC Local Full Gate
```

Ele é um **Check Run** produzido pelo GitHub App dedicado. Em contingência, `required_status_checks.checks` exige esse contexto com o `app_id` exato. Um commit status clássico com o mesmo nome não satisfaz a proteção. Os cinco checks canônicos do Actions continuam exclusivos do modo `--cloud`.

## API GitHub indisponível durante a suíte

Falha ao publicar substatus informativo não transforma teste em sucesso. A evidência local é preservada por SHA e pode ser sincronizada depois. O gate agregado depende do Check Run remoto do App; sem ele, merge continua bloqueado.

## `--promote-only` e `--merge-only`

### `--promote-only`

- exige `summary.json` local com `target_sha` idêntico e `result=success`;
- reexecuta a governança contra o corpo atual do PR;
- republica evidência do mesmo SHA;
- **nunca tenta merge**.

### `--merge-only`

Além das regras acima, confirma SHA, draft, `retencao-humana`, exceções §6-A, migration potencialmente destrutiva e depende de review, CODEOWNERS, branch protection e demais requisitos remotos. O merge usa SHA esperado.

## Retry automático somente para infraestrutura

O watcher pode repetir o mesmo SHA apenas quando o log da tentativa atual contém assinatura inequívoca de falha externa, como DNS/registry, reset/timeout ou indisponibilidade qualificada 429/502/503/504 associada à operação externa. O retry tem backoff exponencial e limite de tentativas. Falha real de teste fica retida até novo SHA, salvo opt-in operacional explícito. Retry nunca produz sucesso por si só.

## Branch protection em contingência

O modo normal exige os cinco contexts do Actions. Em contingência, a alteração exige a autorização registrada e o App ID dedicado:

```bash
EJC_FALLBACK_AUTHORIZATION=998 \
EJC_FALLBACK_APP_ID=<id-numerico-do-app> \
  bash scripts/governanca/branch-protection.sh --fallback
```

`--fallback` é **ATO ADMINISTRATIVO PROTEGIDO**. O payload efetivamente aplicado usa `required_status_checks.checks` e vincula `EJC Local Full Gate` ao `app_id` fornecido. Permanecem `strict=true`, `enforce_admins=true`, review, CODEOWNERS, aprovação do último push, conversas resolvidas, histórico linear, force-push e deleção proibidos.

Restauração cloud:

```bash
bash scripts/governanca/branch-protection.sh --cloud
```

A leitura da proteção atual é fail-closed: somente 404 pode ser interpretado como ausência de proteção; falha de rede, rate limit ou permissão aborta sem sobrescrever o backup estável.

## Watcher autônomo

`scripts/ci-fallback-watch.sh` percorre PRs abertos e não-draft para `main`.

- SHA novo sem evidência → valida;
- falha real → não repete indefinidamente;
- falha de infraestrutura → retry limitado com backoff;
- `summary.json` aprovado → suíte pesada não repete;
- `EJC_FALLBACK_AUTO_MERGE=1` → `--merge-only`;
- `EJC_FALLBACK_AUTO_MERGE=0` → `--promote-only`, sem tentativa de merge;
- API/fetch fora → mantém estado local;
- `main` local só avança por `git merge --ff-only origin/main` quando limpa.

O watcher não usa VPS de produção e não instala GitHub runner.

## Ativação persistente e reversível

Em máquina **não produtiva**, com clone autenticado e credencial de instalação do GitHub App dedicado disponível ao `gh`:

```bash
EJC_FALLBACK_APP_ID=<id-numerico-do-app> \
bash scripts/ci-fallback-activate.sh --enable
```

A ativação só prossegue depois de recusar produção/root/containers canônicos, exigir `main` limpa e igual a `origin/main`, validar dependências, comprovar scheduler persistente, validar sintaxe, executar `ci-local.sh fast`, validar hooks locais e aplicar a proteção fallback com autorização #998.

O ativador prefere cron/crond comprovadamente ativo; usa systemd de usuário somente com `Linger=yes`. O PATH do watcher é explícito e caracteres de quoting ambíguo são recusados. Execuções cron concorrentes são bloqueadas por lock.

Se qualquer etapa falhar depois de tocar a proteção, o rollback restaura a proteção cloud, hooks locais e watcher de forma controlada.

Desativação:

```bash
bash scripts/ci-fallback-activate.sh --disable
```

A desativação **para e remove o watcher primeiro**. Somente depois restaura a branch protection cloud. Assim, um executor antigo não continua tentando promover PRs após a volta ao modo cloud; se a remoção do watcher falhar, a proteção fallback é mantida e o procedimento falha fechado.

## Governança local

`scripts/governanca/ci-local-governanca.sh` usa lista de paths NUL-safe (`git diff --name-only -z`), trata nomes de arquivo como dados opacos, usa `grep --`, não exclui extensões da varredura de segredo e rejeita qualquer `.env*` salvo allowlist explícita de `.env.example`. Falha de leitura/scan é bloqueante.

Mudança em CI/CD, branch protection, autenticação ou uploads exige registro literal `security-auditor: executado` antes de evidência promovível.

## Segurança e LGPD

- nunca rodar fallback em `/opt/ejc` ou host produtivo;
- não apontar `DATABASE_URL` para produção;
- PostgreSQL efêmero, loopback-only e com massa de teste;
- não versionar token/credencial; a credencial do executor deve ser uma instalação do GitHub App dedicado e é validada antes da suíte pesada;
- logs completos permanecem locais;
- falha de pré-requisito, banco, lint, teste, auditoria, restore ou browser é bloqueante;
- nenhuma migration destrutiva é promovida automaticamente;
- fallback não substitui HITL, RBAC, LGPD, citation gate nem revisão independente;
- branch protection fallback só pode ser alterada sob autorização #998.

## Risco residual do gate externo

`EJC Local Full Gate` é um **Check Run emitido por GitHub App dedicado**. A proteção da `main` usa `required_status_checks.checks` para vincular o contexto ao `app_id` esperado. Portanto, um PAT ou commit status clássico não satisfaz esse gate.

Os subgates `EJC Local / ...` permanecem commit statuses meramente informativos. Os controles independentes continuam sendo review/CODEOWNERS, aprovação do último push, `strict=true`, conversa resolvida, SHA exato, exceções §6-A e retenção de migrations destrutivas.

Quando Actions normalizar, `--cloud` restaura os cinco contexts canônicos, que não colidem com o namespace local.

## GitHub Actions durante a contingência

Os workflows permanecem habilitados como evidência adicional. Um job que morre antes do primeiro step (`steps=null`) é classificado como falha do executor, não como reprovação do código.

## Bootstrap desta implementação

A própria PR que introduz o fallback altera `scripts/` e branch protection. Por segurança, ela é exceção §6-A e **não deve auto-integrar a si própria** usando o mecanismo ainda ausente da `main`.

O primeiro bootstrap exige checks cloud reais e verdes ou host Linux não produtivo autorizado executando a validação e o procedimento administrativo, sempre preservando reviews e branch protection. Não usar admin bypass nem reduzir proteções apenas para bootstrap.
