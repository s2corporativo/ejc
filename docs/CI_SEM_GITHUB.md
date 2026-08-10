# CI fora do GitHub Actions — fallback autônomo do EJC

## Objetivo

Este módulo permite validar Pull Requests quando GitHub Actions/runner hospedado está indisponível, sem transformar a VPS produtiva em executor de código não confiável.

O GitHub continua sendo o **control plane** para repositório, Pull Requests, review, branch protection, Check Runs e merge. A contingência elimina apenas a dependência do GitHub Actions como executor único dos testes.

A autorização administrativa da contingência está registrada na Issue #998 e o hardening do root of trust na Issue #1012.

## Invariantes de segurança

1. `/opt/ejc`, banco de produção, containers canônicos e host produtivo nunca executam código de PR.
2. Código de PR nunca executa no mesmo UID que possui `gh`, GitHub App, evidência promovível ou poder de merge.
3. Uma tentativa nova invalida imediatamente qualquer sucesso anterior do mesmo SHA.
4. Sucesso promovível exige exatamente oito logs: backend, eval, frontend, P0, governança, arquitetura, continuidade e UI extra.
5. Check Run obrigatório precisa ser do App autorizado, SHA exato, `external_id` exato e execução matching mais recente.
6. Merge revalida evidência, `origin/main`, head do PR, review, branch protection e Check Run imediatamente antes do `PUT` com SHA esperado.
7. Indisponibilidade externa nunca vira verde.
8. Falha real de teste não entra em retry automático do mesmo SHA.
9. Branch protection não é reduzida para contornar a indisponibilidade do Actions.
10. Migrations destrutivas e caminhos de exceção §6-A não são auto-integrados.

## Arquitetura de confiança

### Control plane

Executa sob o usuário operador da máquina dedicada e contém apenas componentes confiáveis da `main`:

- `scripts/ci-fallback.sh`;
- `scripts/ci-fallback-watch.sh`;
- `scripts/ci-fallback-activate.sh`;
- `scripts/ci_evidence.py`;
- `scripts/ci_activation_journal.py`;
- `scripts/github-app-auth.sh`;
- `scripts/governanca/ci-local-governanca.sh`;
- `scripts/governanca/branch-protection.sh`.

Somente esse plano pode acessar:

- autenticação de usuário do `gh`;
- chave privada do GitHub App;
- installation token efêmero;
- evidência promovível;
- branch protection;
- review e operação de merge.

### Worker plane

`scripts/ci-worker-isolation.sh` executa o código do PR sob uma conta Unix dedicada informada por `EJC_CI_WORKER_USER`.

O preflight falha fechado se o worker:

- for root ou usar o mesmo UID do controlador;
- pertencer a `docker`, `sudo`, `wheel` ou `adm`;
- conseguir executar `sudo` por conta própria;
- conseguir ler/escrever `/var/run/docker.sock`;
- conseguir ler a chave privada do GitHub App;
- conseguir ler a configuração autenticada do `gh`;
- conseguir ler/escrever o state/evidence root do controlador;
- conseguir escrever no checkout ou nos scripts do root of trust;
- possuir HOME persistente gravável;
- possuir o utilitário `at` disponível;
- não possuir Python 3.11, Node 22, PostgreSQL 16, `psql`/`pg_dump` 16 e as extensões `vector`, `pg_trgm` e `pgcrypto`.

Cada stage recebe:

- clone Git novo do SHA, criado com `--no-hardlinks`;
- checkout detached;
- remote `origin` removido;
- HOME, TMP e cache efêmeros;
- ambiente iniciado com `env -i`;
- acesso de escrita somente às áreas de trabalho necessárias (`backend`, `frontend` e estado efêmero);
- cópia read-only de `ci-local.sh` proveniente do control plane, não do PR.

Após o stage, o controlador mata processos residuais do UID do worker, remove crontab do worker, limpa arquivos pertencentes ao UID em `/tmp` e `/dev/shm` e remove a árvore efêmera do stage.

## Pipeline local

`scripts/ci-local.sh` contém os gates técnicos e continua sendo o executor canônico de cada stage. No fallback promovível ele é chamado exclusivamente pela cópia trusted materializada pelo worker.

Modos:

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

O runtime promovível exige Python 3.11, Node 22 e PostgreSQL 16. `EJC_ALLOW_PYTHON_MISMATCH=1` é exclusivamente diagnóstico e não pode produzir gate promovível.

O banco de CI é efêmero, usa bind apenas em `127.0.0.1`, autenticação host SCRAM e nunca utiliza banco de produção.

O venv da aplicação é content-addressed por versão exata do Python e SHA-256 de `backend/requirements.txt`, protegido por lock e `pip check`. `pip-audit` usa ambiente de tooling separado para não alterar a identidade do venv da aplicação.

## Evidência local

`ci_evidence.py` mantém um namespace por SHA:

```text
<evidence-root>/<sha>/
  .lock
  latest-attempt.json
  latest-success.json
  attempts/<attempt-id>/
    backend.log
    eval.log
    frontend.log
    p0.log
    governanca.log
    architecture.log
    continuity.log
    ui-extra.log
    summary.json
```

### Máquina de estados

`start` cria uma tentativa única e atualiza atomicamente `latest-attempt.json`. A partir desse instante, qualquer `latest-success.json` de tentativa anterior deixa de ser válido, mesmo que a nova tentativa ainda não tenha produzido um log.

`finish success --promote` somente é aceito quando:

- a tentativa é a tentativa atual;
- `exit_code=0`;
- existem exatamente os oito logs esperados;
- cada log é arquivo regular e não symlink;
- hashes SHA-256 e tamanhos são calculados;
- `summary.json` é escrito atomicamente e sincronizado com `fsync`;
- `latest-success.json` referencia a mesma tentativa atual e o hash do summary.

`verify` recalcula hash/tamanho em streaming, rejeita path traversal, symlink, summary adulterado, log alterado, tentativa stale e conjunto parcial/extra de logs.

Complexidade de finalização/verificação: O(B) em tempo, onde B é o total de bytes dos logs, e O(1 MiB) de memória adicional.

### Retenção

O watcher executa `prune` periodicamente. A retenção padrão mantém quantidade e idade limitadas de SHAs/tentativas. SHAs com lock ativo não são removidos. A exclusão usa rename para namespace de quarantine antes da remoção, impedindo que uma recriação concorrente do mesmo SHA seja apagada por engano.

## GitHub App e Check Run

O GitHub App dedicado é usado somente para o Check Run promovível. A autenticação:

- valida a chave fora do repositório/produção;
- exige permissões owner-only e rejeita symlink;
- cria JWT RS256 curto;
- solicita installation token restrito ao repositório EJC e `checks:write`;
- mantém token somente em memória e renova antes de expirar.

O required check do modo fallback é:

```text
EJC Local Full Gate
```

Os subgates `EJC Local / ...` são statuses informativos e não substituem o required check.

`full_gate_is_green()` exige simultaneamente:

- ID exato do Check Run da promoção atual;
- nome correto;
- SHA correto;
- `external_id` correto;
- `app.id` autorizado;
- `status=completed`;
- `conclusion=success`;
- ID igual ao Check Run matching mais recente retornado com filtros `check_name`, `app_id` e `filter=latest`.

Um Check Run verde antigo não satisfaz uma promoção nova.

## Governança trusted

A versão de `ci-local-governanca.sh` executada é a versão do control plane. `EJC_GOV_SOURCE_ROOT` aponta para um worktree do SHA do PR, que é apenas lido.

A governança trabalha sobre paths alterados de forma NUL-safe e tem complexidade O(bytes alterados). O root of trust inclui:

- `ci-local.sh`;
- `ci-fallback*.sh`;
- `ci-worker-isolation.sh`;
- `ci_evidence.py`;
- `github-app-auth.sh`;
- branch protection e governança local.

Mudanças nesses caminhos exigem registro literal `security-auditor: executado` no PR promovível.

O scanner cobre `.env`, private keys e padrões de credenciais AWS, OpenAI, Slack e GitHub. Nenhum valor detectado deve ser reproduzido em log ou comentário.

## Promoção e merge

### `--promote-only`

Requer evidência atual e íntegra e revalida a governança do corpo atual do PR antes de publicar o Check Run. Não chama merge.

### `--merge-only` / `--merge`

Antes de integrar, o control plane exige:

- `origin/main` ainda ancestral do SHA;
- PR aberto e não-draft;
- head do PR ainda igual ao SHA validado;
- `reviewDecision=APPROVED`;
- ausência de `retencao-humana`;
- evidência local atual;
- Check Run canônico atual;
- branch protection live com `strict`, App/contexto correto, `enforce_admins`, review mínimo, CODEOWNERS, aprovação do último push, conversas resolvidas, histórico linear, sem force-push e sem deleção;
- ausência de caminho §6-A;
- migration com patch disponível e sem padrão destrutivo detectado.

O snapshot é repetido imediatamente antes do `PUT /merge`, que também recebe `sha=<SHA esperado>`. Qualquer mudança concorrente retém o merge.

## Watcher e retries

`ci-fallback-watch.sh` processa apenas PRs abertos, não-draft e com base `main`.

Ele mantém fingerprint por PR para evitar reprocessamento pesado de estado inalterado e reutiliza evidência verde apenas quando a evidência continua atual/íntegra.

Retry automático do mesmo SHA ocorre somente quando o log do stage atual ou o log da própria invocação contém assinatura inequívoca de infraestrutura externa, por exemplo:

- DNS/name resolution;
- `EAI_AGAIN`;
- `ECONNRESET`;
- `ETIMEDOUT`;
- falha de TLS/network;
- registry npm/PyPI indisponível;
- respostas 429/502/503/504 qualificadas;
- impossibilidade de obter installation token ou criar Check Run.

O retry usa backoff exponencial com teto e número máximo configurável. Pytest, lint, typecheck, build ou governança vermelhos sem assinatura externa são classificados como falha real e o mesmo SHA não é repetido automaticamente.

Exit code 75 representa contenção/indisponibilidade transitória e nunca aprovação.

## Ativação transacional

O caminho canônico é:

```bash
bash scripts/ci-fallback-activate.sh --status
bash scripts/ci-fallback-activate.sh --enable
bash scripts/ci-fallback-activate.sh --disable
```

### Pré-condições

Antes de alterar branch protection, `--enable` exige:

- host não produtivo;
- execução não-root;
- nenhum marcador `/opt/ejc` de produção;
- checkout `main` limpo e idêntico a `origin/main`;
- Docker disponível apenas ao controlador para preflights do pipeline legado, sem containers canônicos EJC co-residentes;
- Python 3.11, Node 22, PostgreSQL client, `git`, `gh`, `jq`, `flock`, OpenSSL, cURL, `sudo`, `setfacl`, `pgrep` e `getent`;
- scheduler persistente: cron/crond ativo ou systemd de usuário com `Linger=yes`;
- `ci-local.sh fast` verde;
- worker isolation preflight verde;
- acesso funcional do GitHub App à Checks API.

Nenhuma branch protection é alterada se o worker falhar no preflight.

### Journal durável

`ci_activation_journal.py` registra as fases:

```text
starting -> draining -> watcher -> hooks -> protection -> commit -> active
```

O journal é owner-only, 0600, sob state root 0700, sem symlink/hardlink, com escrita atômica e `fsync`. Fases só avançam.

Ativação:

1. inicia journal;
2. cria drain;
3. instala watcher ainda drenado;
4. registra/restaura `core.hooksPath` somente local;
5. salva snapshot exato dos required status checks e aplica o fallback;
6. grava estado ativo com App, scheduler, state root e worker;
7. remove drain;
8. conclui/limpa journal.

Se o processo morrer no meio, `--status` retorna `recovery_required` e `--disable` executa recovery idempotente.

### Desativação

A ordem é obrigatória:

1. journal + drain;
2. lock do watcher;
3. restaura **exatamente** o snapshot anterior dos required status checks;
4. somente depois remove watcher/scheduler;
5. restaura `core.hooksPath`;
6. remove estado, snapshot e drain;
7. conclui o journal.

Se a restauração da proteção falhar, o watcher/drain/journal/snapshot permanecem para recuperação; o sistema não deixa um required check sem produtor por uma limpeza parcial.

## Branch protection

`branch-protection.sh` altera somente o subrecurso `required_status_checks` e preserva as demais proteções por construção.

`--fallback` exige `EJC_FALLBACK_AUTHORIZATION=998`, salva snapshot exato e configura `EJC Local Full Gate` vinculado ao App autorizado.

O PATCH usa read-after-write: se a resposta HTTP se perder depois de o GitHub ter aplicado a alteração, o script relê o estado efetivo antes de decidir se houve falha ou se deve restaurar.

## Performance

- evidência: O(B) tempo / O(1 MiB) memória adicional;
- governança: O(bytes alterados);
- lock por SHA: O(1) estado;
- watcher: enumeração O(P), trabalho pesado tendendo a O(PRs alterados) em estado estável;
- snapshot por stage: aproximadamente O(S) de I/O, S = tamanho materializado do repositório;
- venv: custo de instalação apenas no primeiro uso do hash de runtime+requirements;
- pipeline pesado permanece sequencial até existir capacity planning explícito do host.

O custo de criar snapshot novo por stage é deliberado: evita cache/code poisoning e persistência lateral entre gates. Qualquer cache futuro compartilhado deve ser read-only ou content-addressed/verificado e passar por novo threat model.

## Segurança e LGPD

O fallback não precisa de PII nem de documentos reais. Não versiona nem registra `.env`, chaves, tokens ou dados jurídicos.

Logs completos e evidência permanecem no host dedicado sob permissões restritas. O banco do CI é efêmero. RBAC, AuthMiddleware, HITL, citation gate, regras jurídicas e dados de cliente não são alterados por este módulo.

Além da separação Unix, o host dedicado deve bloquear por rede o acesso do worker a produção e serviços privados. Esse isolamento de rede precisa ser comprovado durante o bootstrap do host; não deve ser presumido pelo código do repositório.

## Bootstrap e limitações

O próprio fallback é root of trust e altera `scripts/`/governança. Por isso seu bootstrap é exceção §6-A: **não pode auto-integrar a si próprio** usando o mecanismo que ainda não está na `main`.

Antes da ativação real são obrigatórios:

1. revisão independente do head final;
2. execução de `ci-local.sh full` em host Linux dedicado elegível;
3. comprovação do worker Unix separado;
4. comprovação de isolamento de rede do worker em relação a produção/private services;
5. validação real do GitHub App/installation e scheduler persistente;
6. somente depois, integração controlada e ativação do fallback.

Enquanto essas provas não existirem, não é correto afirmar que o fallback está ativo nem que PRs foram validados por ele.

## Rollback

Se o fallback já estiver ativo, use exclusivamente:

```bash
bash scripts/ci-fallback-activate.sh --disable
```

A desativação restaura o snapshot real dos required checks antes de remover o produtor. O código pode ser revertido sem migration, schema ou dado de aplicação.
