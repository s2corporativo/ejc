# CI fora do GitHub Actions — fallback autônomo do EJC

## Objetivo e fronteira de confiança

O GitHub permanece fonte de verdade para código, Pull Requests, reviews, branch protection, Check Runs e merge. O fallback remove **GitHub Actions/runner como executor único**, não elimina o GitHub como control plane.

A execução promovível exige host Linux **dedicado e não produtivo**. `/opt/ejc`, banco de produção, serviços privados do EJC e containers persistentes não participam da CI de PR.

Autorização administrativa: Issue #998. Hardening do root of trust: Issue #1012.

## Invariantes não negociáveis

1. código de PR nunca executa no mesmo UID que possui `gh`, chave do GitHub App, evidência promovível ou poder de merge;
2. produção nunca executa código de PR;
3. uma tentativa nova do mesmo SHA invalida semanticamente qualquer sucesso local anterior;
4. sucesso promovível exige exatamente os oito gates e oito logs esperados;
5. evidência adulterada, incompleta, stale, com symlink ou path traversal falha fechada;
6. `EJC Local Full Gate` válido precisa ser o Check Run exato, mais recente, do SHA/App/contexto/external_id atuais;
7. merge relê `origin/main`, head, review, proteção e gate imediatamente antes do ato;
8. migrations sem diff integral ou potencialmente destrutivas permanecem retidas;
9. branch protection nunca é reduzida para contornar indisponibilidade;
10. falha de rede/App/API nunca vira verde;
11. enable/disable nunca deixa required check sem produtor operacional;
12. nenhum segredo é persistido em repositório, evidência ou log.

## Arquitetura de segurança

### Control plane — confiável

Executado pelo usuário controlador:

- `scripts/ci-fallback.sh`;
- `scripts/ci-fallback-watch.sh`;
- `scripts/ci-fallback-activate.sh`;
- `scripts/ci_evidence.py`;
- `scripts/github-app-auth.sh`;
- branch protection;
- governança trusted;
- `gh`, review, Check Runs e merge.

O control plane não executa Python, TypeScript ou shell proveniente do PR como código confiável.

### Worker plane — não confiável

`scripts/ci-worker-isolation.sh` executa cada gate de aplicação sob `EJC_CI_WORKER_USER`, com:

- UID distinto de root e do controlador;
- sem grupos `docker`, `sudo`, `wheel` ou `adm`;
- sem sudo próprio;
- sem leitura/escrita do Docker socket;
- sem acesso à chave do GitHub App;
- sem acesso à configuração autenticada do `gh`;
- sem acesso à evidência/estado do control plane;
- HOME cadastrado inexistente ou não gravável;
- `env -i` e HOME/TMP/XDG cache efêmeros por stage;
- PostgreSQL 16 + `vector`, `pg_trgm` e `pgcrypto` locais sob o próprio UID;
- snapshot Git novo por stage, `--no-hardlinks`, detached e sem `origin`;
- cópia read-only do `ci-local.sh` trusted do controlador;
- limpeza de processos, crontab, `/tmp`, `/dev/shm` e árvore do stage ao final.

O worker só recebe escrita em `backend/`, `frontend/` e estado efêmero do stage. A raiz do snapshot e `scripts/` permanecem sem write para impedir substituição do orquestrador trusted por rename/directory write.

## `scripts/ci-local.sh`

Gates:

```bash
bash scripts/ci-local.sh backend
bash scripts/ci-local.sh eval
bash scripts/ci-local.sh frontend
bash scripts/ci-local.sh p0
bash scripts/ci-local.sh architecture
bash scripts/ci-local.sh continuity
bash scripts/ci-local.sh ui-extra
bash scripts/ci-local.sh required
bash scripts/ci-local.sh full
bash scripts/ci-local.sh fast
```

### Runtime hermético

Baseline promovível:

- Python 3.11;
- Node 22;
- PostgreSQL 16;
- pgvector.

`EJC_ALLOW_PYTHON_MISMATCH=1` e `EJC_ALLOW_POSTGRES_MISMATCH=1` são apenas diagnósticos e não produzem evidência promovível.

### Venv da aplicação

O ambiente Python é content-addressed por:

```text
versão exata do Python + SHA-256 de backend/requirements.txt
```

A materialização usa `flock`, diretório de build temporário, `pip check`, marker `.ejc-ready` e promoção por rename. `CI_SKIP_PIP=1` falha se o ambiente correto ainda não existir.

`pip-audit==2.10.0` vive em tool-venv separado. Ferramentas do pipeline não alteram o venv que representa as dependências declaradas da aplicação.

### PostgreSQL

Quando Docker está disponível ao executor direto de diagnóstico, o banco usa `pgvector/pgvector:pg16` com bind apenas em `127.0.0.1`.

No worker promovível não existe Docker socket: o `ci-local.sh` usa PostgreSQL 16 local. Host auth é SCRAM; `listen_addresses=127.0.0.1`; banco e PGDATA são efêmeros.

Backend e continuity têm ciclos de banco independentes.

## Evidência: `scripts/ci_evidence.py`

Estrutura:

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

`start` cria tentativa única e troca atomicamente `latest-attempt.json`. A partir desse instante qualquer `latest-success` de tentativa anterior deixa de ser promovível.

`finish success` exige:

- tentativa ainda atual;
- `exit_code=0`;
- exatamente os oito logs;
- hashes/tamanhos calculáveis em arquivos regulares.

`verify` exige que `latest-success` e `latest-attempt` apontem para a **mesma tentativa** e recalcula hash/tamanho de todos os logs e do summary.

Ponteiros e summaries usam arquivo temporário + `fsync` + `os.replace`; diretórios também recebem `fsync` quando suportado.

Complexidade de finalização/verificação: **O(B)** em tempo, B = bytes totais dos logs, e memória adicional limitada ao bloco de hashing de 1 MiB.

### Retenção

`prune` preserva as melhorias do #1004:

- default 200 SHAs;
- janela default 30 dias;
- até 5 tentativas não referenciadas por SHA;
- lock por SHA;
- SHA antigo é renomeado atomicamente para quarentena antes da exclusão física;
- não segue symlinks;
- preserva histórico apontado por `latest-success` e estado atual apontado por `latest-attempt`.

Preservar histórico **não** o torna novamente promovível: se uma tentativa posterior falhou, `verify` continua false.

## GitHub App e Check Run canônico

Variáveis do host dedicado:

```text
EJC_FALLBACK_APP_ID
EJC_FALLBACK_APP_INSTALLATION_ID
EJC_FALLBACK_APP_PRIVATE_KEY_FILE
```

A chave privada precisa ficar fora do repositório e de `/opt/ejc`, não pode ser symlink, deve pertencer ao controlador e não pode ter permissões para grupo/outros.

`github-app-auth.sh`:

- gera JWT RS256 curto;
- cria installation token limitado ao repositório EJC e `checks:write`;
- mantém token somente em memória;
- renova antes de uma hora;
- nunca grava token na configuração do `gh`.

O gate promovível é **somente**:

```text
EJC Local Full Gate
```

Cada promoção recebe `external_id` próprio. `full_gate_is_green()` exige:

- `FULL_CHECK_ID` exato;
- nome exato;
- SHA exato;
- `external_id` exato;
- App ID exato;
- `status=completed`;
- `conclusion=success`;
- o mesmo ID como Check Run matching mais recente daquele App/contexto no SHA.

Commit statuses `EJC Local / ...` são observabilidade e nunca substituem esse Check Run.

## Fluxo de `ci-fallback.sh`

1. valida control plane e worker;
2. atualiza `origin/main`;
3. resolve `headRefOid` exato do PR;
4. exige `origin/main` ancestral do SHA;
5. adquire lock exclusivo por SHA; concorrência retorna `75`;
6. valida `checks:write` do GitHub App;
7. inicia nova tentativa de evidência;
8. executa backend, eval, frontend, P0, arquitetura, continuity e UI em worker isolado, cada um com snapshot novo;
9. executa governança usando o script trusted do controlador contra worktree do PR apenas lido;
10. promove evidência somente depois dos oito gates;
11. revalida governança atual;
12. publica Check Run canônico;
13. valida evidência + Check Run;
14. quando merge foi solicitado, aplica as travas finais.

## Merge e TOCTOU

`verify_merge_snapshot()` exige simultaneamente:

- `origin/main` atualizado e ancestral do SHA;
- evidência local atual e íntegra;
- Full Gate canônico verde;
- branch protection live com `strict=true`;
- required check associado ao App esperado;
- `enforce_admins`;
- pelo menos uma aprovação;
- CODEOWNERS;
- aprovação do último push;
- conversas resolvidas;
- histórico linear;
- force-push e deleção proibidos;
- PR aberto, não draft;
- `reviewDecision=APPROVED`;
- head ainda igual ao SHA;
- ausência de `retencao-humana`.

Paths §6-A e migrations potencialmente destrutivas continuam sem auto-merge. Patch de migration ausente/truncado é fail-closed.

O snapshot é executado uma vez antes das verificações de arquivos e **novamente imediatamente antes** do `PUT /merge`. O endpoint ainda recebe `sha=<SHA esperado>`.

## Watcher incremental

`scripts/ci-fallback-watch.sh` mantém:

- fingerprint `SHA | updatedAt | mergeState | autoMergeMode`;
- recheck periódico de PR verde;
- backoff exponencial limitado;
- retenção diária lock-aware;
- avanço da `main` somente por `git merge --ff-only origin/main`;
- drain operacional.

Falha de infraestrutura é reconhecida somente por assinatura qualificada de DNS, timeout/reset, registry ou 429/502/503/504 ligado a serviço externo.

A classificação usa primeiro o log do stage da **tentativa atual** e, se a falha ocorreu antes do primeiro stage, o log da própria invocação do orquestrador. Pytest/lint/typecheck/build sem sinal externo é falha real e não entra em loop.

Exit `75` significa contenção/indisponibilidade, não reprovação do SHA.

## Governança trusted

`ci-local-governanca.sh` é executado a partir da `main` trusted. `EJC_GOV_SOURCE_ROOT` aponta para o snapshot do PR que será apenas inspecionado.

O root of trust inclui:

- `ci-local.sh`;
- `ci-fallback*.sh`;
- `ci-worker-isolation.sh`;
- `ci_evidence.py`;
- `github-app-auth.sh`;
- branch protection;
- governança local.

Mudanças nesses caminhos exigem registro literal `security-auditor: executado`.

A varredura é NUL-safe e trabalha sobre arquivos alterados: complexidade **O(bytes alterados)**. O detector cobre `.env`, chaves privadas e famílias modernas de tokens GitHub, além dos demais padrões sensíveis existentes.

## Branch protection

`branch-protection.sh` altera somente:

```text
/branches/main/protection/required_status_checks
```

Não reescreve reviews, CODEOWNERS, restrictions ou demais proteções.

`--fallback` exige autorização #998, salva snapshot exato dos required checks e passa a exigir `EJC Local Full Gate` vinculado ao App ID.

`--restore` reaplica exatamente o snapshot salvo. A desativação normal usa `--restore`, não uma reconstrução presumida do estado cloud.

## Ativação transacional

Caminho canônico:

```bash
bash scripts/ci-fallback-activate.sh --status
bash scripts/ci-fallback-activate.sh --enable
bash scripts/ci-fallback-activate.sh --disable
```

### Pré-condições de `--enable`

- host Linux dedicado e não produtivo;
- `main` limpa e igual a `origin/main`;
- usuário controlador não root;
- conta worker dedicada em `EJC_CI_WORKER_USER`;
- sudoers mínimo que permita controlador → worker sem dar sudo ao worker;
- Python 3.11, Node 22, PostgreSQL 16, pgvector, `psql`, `pg_dump`;
- `sudo`, `setfacl`, `flock`, `jq`, OpenSSL, cURL e `gh`;
- scheduler persistente: systemd user com linger ou cron/crond;
- sem containers/serviços co-residentes;
- chave/App válidos;
- `ci-local.sh fast` trusted verde.

### Enable: ordem de transação

1. valida sintaxe/root of trust;
2. prova isolamento do worker;
3. roda preflight trusted da `main`;
4. prova `checks:write` do App;
5. escolhe scheduler persistente;
6. salva hooks locais;
7. cria `draining`;
8. instala watcher **ainda drenado**;
9. aplica e confirma branch protection fallback;
10. grava estado ativo;
11. remove drain.

Falha após qualquer mutação tenta restaurar proteção, scheduler e hooks.

### Disable: ordem de transação

1. cria `draining`;
2. adquire o lock do watcher e espera execução em curso terminar;
3. restaura **exatamente** os required checks anteriores;
4. se a restauração falhar, remove drain e mantém o watcher operacional;
5. somente depois remove watcher/scheduler;
6. restaura hooks;
7. remove estado/backup/drain.

Se a proteção voltou mas o scheduler não pôde ser removido, o drain permanece e o executor residual vira no-op.

## Performance e escalabilidade

- evidência: O(B) tempo / O(1 MiB) memória adicional;
- governança: O(bytes alterados);
- watcher: O(P) para listagem de PRs e trabalho pesado próximo de O(PRs alterados) em regime estável;
- snapshot por stage: aproximadamente O(S) de I/O, S = tamanho materializado do repositório.

O custo de snapshot por stage é intencional para eliminar persistência e cache poisoning entre gates. Otimização futura só deve compartilhar cache se ele for read-only/content-verified e passar por threat model específico.

Stages pesados permanecem sequenciais até existir capacity planning de CPU/RAM/IO do host dedicado; paralelizar banco, restore e browser sem orçamento de recursos pode causar OOM/thrashing e falso diagnóstico.

## Segurança e LGPD

- nenhum dado real de cliente é necessário para CI;
- banco de produção não é acessado;
- worker não recebe segredos do control plane;
- App tem `checks:write` no repositório alvo, sem permissão de conteúdo/PR/admin;
- logs/evidências ficam locais e restritos;
- nenhuma migration destrutiva é auto-integrada;
- AuthMiddleware, RBAC, HITL, citation gate, RAG e tratamento de PII da aplicação não são alterados por este módulo.

### Isolamento de rede

O repositório prova isolamento de identidade/arquivo/processo, mas **não consegue provar sozinho firewall/security-group do futuro host**. O bootstrap promovível deve demonstrar que o worker não alcança produção, banco/Redis/Ollama privados ou redes administrativas. Sem essa evidência operacional, o fallback não deve ser ativado.

## Bootstrap e estado atual

A implementação do próprio fallback altera `scripts/` e governança; portanto é exceção §6-A e **não se auto-integra** usando o mecanismo que ainda não está em `main`.

O primeiro full gate requer host dedicado real com worker configurado e isolamento de rede comprovado. Enquanto isso não existir, não é correto afirmar que o full gate reconciliado foi executado ou que produção foi atualizada.
