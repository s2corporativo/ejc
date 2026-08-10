# CI fora do GitHub Actions — fallback autônomo do EJC

## Objetivo e fronteira de confiança

O GitHub continua sendo a fonte de verdade para código, Issues, Pull Requests, review, branch protection e histórico. O fallback elimina **GitHub Actions/runner hospedado como executor único**, não elimina o GitHub como control plane.

Quando Actions não consegue iniciar jobs, o SHA pode ser validado em uma máquina Linux **não produtiva**, em `git worktree` isolado, com PostgreSQL 16 + pgvector efêmero. `/opt/ejc`, a VPS de produção, banco de produção e containers canônicos do EJC são proibidos como executor de PR.

A autorização administrativa desta contingência está registrada na Issue #998. O hardening Staff do root of trust está registrado na Issue #1012.

## Invariantes

1. nenhuma indisponibilidade vira verde;
2. uma tentativa nova invalida imediatamente o sucesso local anterior do mesmo SHA;
3. sucesso promovível exige os oito gates completos e logs íntegros;
4. o Check Run obrigatório precisa ser do GitHub App esperado, do SHA exato e ser a execução canônica mais recente;
5. merge exige evidência local atual, review aprovado, branch protection íntegra, `main` compatível e SHA esperado;
6. produção nunca executa código de PR;
7. branch protection não é reduzida para destravar contingência;
8. migrations potencialmente destrutivas e paths §6-A continuam retidos.

## `scripts/ci-local.sh`

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

### Runtime e cache herméticos

O modo promovível exige Python 3.11 e Node 22. `EJC_ALLOW_PYTHON_MISMATCH=1` é exclusivamente diagnóstico e não pode produzir gate promovível.

O venv da aplicação é content-addressed por:

- versão **exata** do Python;
- SHA-256 de `backend/requirements.txt`.

A instalação é protegida por `flock`, possui marker de conclusão e executa `pip check`. `CI_SKIP_PIP=1` falha se o venv correto não estiver materializado.

Ferramentas do pipeline não contaminam esse ambiente. `pip-audit==2.10.0` vive em venv próprio, também versionado e bloqueado. Assim, a identidade do venv da aplicação representa seu conteúdo declarado.

### Isolamento e memória

`STATE_ROOT`, `PGDATA`, relatórios, tooling e restore report precisam ficar fora do checkout, de `/opt/ejc` e do HOME raiz. Limpeza destrutiva é restrita a descendentes de `STATE_ROOT`; não há `rm -rf`.

PostgreSQL usa porta efêmera e bind apenas em `127.0.0.1`. Backend e continuity encerram seus bancos entre estágios.

O full gate permanece sequencial por padrão. Essa decisão é deliberada: backend DB-level, restore drill e browser têm picos de CPU/RAM/IO; paralelizar sem orçamento de recursos pode trocar tempo de parede menor por OOM/thrashing e falso diagnóstico. A otimização aplicada é de trabalho redundante: o build frontend validado no mesmo processo/SHA é reutilizado pelo gate de browser; em execução standalone, `ui-extra` continua construindo o frontend.

## `scripts/ci_evidence.py` — máquina de estados da evidência

A evidência é organizada por SHA:

```text
<evidence-root>/<sha>/
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

`start` cria uma tentativa única e atualiza atomicamente `latest-attempt.json`. Esse ato invalida semanticamente qualquer verde anterior: `verify` só aceita `latest-success` quando ele aponta para **a mesma tentativa atual**.

Sucesso exige exatamente os oito logs acima, `exit_code=0`, hash SHA-256 e tamanho de cada arquivo. Symlink, path traversal, log ausente/extra, summary adulterado ou tentativa stale falham fechados. Ponteiros e summaries usam escrita atômica, `fsync`, permissão 0600 e diretório 0700.

Complexidade de finalização/verificação: O(B) em tempo, onde B é o total de bytes dos logs, e O(1) em memória adicional; hashing usa blocos fixos de 1 MiB.

## `scripts/github-app-auth.sh` — identidade do gate

Há duas identidades separadas:

- `gh` do usuário/operador: leitura de PR, reviews, arquivos e operação de merge sujeita à branch protection;
- GitHub App dedicado: **somente** emissão/leitura do Check Run promovível.

O App usa chave privada armazenada fora do repositório/produção, owner-only, não-symlink. O script assina JWT RS256 e gera installation token efêmero restrito:

- ao repositório EJC;
- à permissão `checks:write`.

O token existe apenas em memória e é renovado automaticamente antes do limite de uma hora. Não é gravado em `.env`, arquivo, configuração do `gh` ou log.

Variáveis operacionais no host não produtivo:

```text
EJC_FALLBACK_APP_ID
EJC_FALLBACK_APP_INSTALLATION_ID
EJC_FALLBACK_APP_PRIVATE_KEY_FILE
```

A chave privada nunca deve ser colada em chat, Issue, PR, README ou log.

## `scripts/ci-fallback.sh`

Fluxo completo por PR:

1. atualiza `origin/main`;
2. resolve o SHA exato do PR e confirma a branch remota;
3. exige `origin/main` ancestral do SHA;
4. adquire lock exclusivo por SHA;
5. renova a credencial efêmera do GitHub App;
6. cria a tentativa de evidência;
7. cria worktree descartável;
8. inicia o Check Run canônico e statuses informativos;
9. executa backend, eval, frontend, P0, governança, arquitetura, continuity e UI;
10. finaliza/promove a evidência somente depois dos oito gates;
11. revalida o corpo atual do PR;
12. publica o Check Run agregado;
13. antes de qualquer merge, revalida proteção, review, head, ancestry da `main` e evidência;
14. repete esse snapshot imediatamente antes do `PUT /merge`, que também recebe o SHA esperado.

### Check Run canônico

O único required check do modo fallback é:

```text
EJC Local Full Gate
```

Cada execução usa `external_id` próprio. Para ser aceito pelo executor, o Check Run precisa simultaneamente:

- ter o ID exato da promoção atual;
- nome correto;
- `head_sha` correto;
- `external_id` correto;
- `app.id` igual ao App autorizado;
- `status=completed`;
- `conclusion=success`;
- ser o Check Run correspondente mais recente daquele App/contexto no SHA.

Os subgates `EJC Local / ...` são commit statuses informativos; nunca são branch-protected.

## Promoção e merge

### `--promote-only`

- exige evidência local **atual**, completa e íntegra;
- revalida governança do corpo atual do PR;
- publica/republica o Check Run;
- nunca chama merge.

### `--merge-only`

Antes do merge, além da promoção, exige:

- `origin/main` ainda ancestral do SHA;
- head do PR ainda igual ao SHA;
- PR aberto e não-draft;
- `reviewDecision=APPROVED`;
- ausência de `retencao-humana`;
- branch protection com `strict`, App/contexto correto, review, CODEOWNERS, aprovação do último push, conversas resolvidas, histórico linear, sem force-push/deleção;
- nenhum path de exceção §6-A;
- nenhuma migration potencialmente destrutiva detectável; patch indisponível/truncado falha fechado.

O snapshot é lido novamente imediatamente antes do merge. O endpoint recebe `sha=<SHA esperado>`, e `strict=true` continua sendo a última proteção contra avanço concorrente da `main`.

## Retry automático de infraestrutura

`scripts/ci-fallback-watch.sh` só repete o mesmo SHA para assinaturas qualificadas de infraestrutura: DNS, registry, timeout/reset e 429/502/503/504 vinculados a serviços externos.

A classificação considera:

1. log do stage da **tentativa atual**, quando existe;
2. log da própria invocação do orquestrador, cobrindo falha pré-stage de GitHub/App/registry.

Falha de pytest, lint, typecheck, build ou regra de governança sem assinatura externa é defeito real e fica retida até novo SHA. Exit 75 é contenção/indisponibilidade e não vira falha de código.

Retry tem backoff exponencial e teto configurável. Não existe retry infinito nem promoção por mera repetição.

O watcher também reduz churn da API: PR verde e sem mudança relevante só é reavaliado após fingerprint/intervalo configurado.

## Ativação transacional

A ativação só ocorre em host Linux não produtivo, `main` limpa e idêntica a `origin/main`, com Docker, Python 3.11, Node 22, PostgreSQL client, `gh`, `jq`, `flock`, OpenSSL/cURL e scheduler persistente.

O scheduler é cron/crond ativo ou systemd de usuário com `Linger=yes`. PATH e caminhos usados no scheduler passam por validação de quoting.

Antes de alterar required checks, o ativador:

1. valida sintaxe;
2. roda `ci-local.sh fast`;
3. valida chave/identidade do App;
4. salva hooks locais;
5. instala o watcher em estado drenado;
6. salva snapshot exato dos required status checks atuais;
7. aplica o check fallback autorizado;
8. libera o drain somente após tudo estar consistente.

### Desativação — ordem obrigatória

A desativação **não mata o produtor primeiro**. O protocolo correto é:

1. cria `draining`;
2. adquire o lock do watcher e espera a execução em curso terminar;
3. restaura **exatamente** o snapshot anterior de required status checks enquanto o watcher ainda está instalado, mas drenado;
4. se a restauração falhar, remove `draining` e mantém o watcher operacional;
5. somente após a proteção anterior estar ativa remove scheduler/watcher;
6. restaura `core.hooksPath`;
7. remove estado de ativação/drain/backup.

Se a remoção do watcher falhar depois que a proteção já foi restaurada, o drain permanece: executor residual não promove novos PRs e a operação falha explicitamente.

Use o ativador como caminho canônico:

```bash
bash scripts/ci-fallback-activate.sh --status
bash scripts/ci-fallback-activate.sh --enable
bash scripts/ci-fallback-activate.sh --disable
```

Não use `--cloud` como substituto normal de `--disable`: o ativador restaura o snapshot real anterior, não uma suposição sobre ele.

## Branch protection

`scripts/governanca/branch-protection.sh` altera somente o subrecurso `required_status_checks`; reviews, CODEOWNERS, enforce-admins, restrictions, histórico linear e demais proteções não são reescritos por esse script.

`--fallback` requer `EJC_FALLBACK_AUTHORIZATION=998` e vincula `EJC Local Full Gate` ao `app_id` autorizado. A configuração anterior é salva e `--restore` repõe exatamente o snapshot.

O executor, por defesa em profundidade, relê a proteção completa antes do merge e exige os demais invariantes de segurança.

## Governança local

`scripts/governanca/ci-local-governanca.sh` trabalha apenas sobre paths alterados, NUL-safe. Complexidade O(B), B = bytes dos arquivos modificados.

O root of trust abaixo é tratado como mudança sensível/de governança:

- `ci-local.sh`;
- `ci-fallback*.sh`;
- `ci_evidence.py`;
- `github-app-auth.sh`;
- branch protection/governança local.

Mudança nesses caminhos exige registro literal `security-auditor: executado` em PR promovível. O detector cobre `.env*`, private keys, AWS, OpenAI, Slack e famílias modernas de token GitHub, sem versionar ou imprimir o segredo detectado.

## Performance e escalabilidade

O pipeline evita otimizações que criariam risco de memória:

- evidência: streaming O(1) memória;
- governança: O(bytes alterados), não varredura completa repetida;
- venv: cache content-addressed + lock, sem reinstalação em cada stage;
- pip-audit: tooling separado;
- frontend: build reutilizado no full gate quando já validado no mesmo processo/SHA;
- DB: lifecycle independente por stage, sem reuso silencioso.

Paralelização pesada permanece desativada por padrão até existir host dedicado com orçamento explícito de CPU/RAM. Backend DB-level + restore + browser em paralelo pode reduzir wall-clock, mas aumenta pico de memória e IO; em fallback de segurança, previsibilidade é preferível a throughput sem capacity planning.

## Segurança/LGPD

- nenhuma PII ou documento real é necessário para CI;
- logs completos ficam no host de CI com permissões restritas;
- nenhum segredo vai para summary/PR;
- banco CI é efêmero e loopback-only;
- produção/VPS não executa PR;
- fallback não altera AuthMiddleware, RBAC, HITL, citation gate ou regras jurídicas;
- migration destrutiva não é auto-integrada.

## Bootstrap e limitação atual

A própria implementação do fallback altera `scripts/` e branch protection, portanto é exceção §6-A e não se auto-integra usando o mecanismo que ainda não está na `main`.

O primeiro full gate promovível requer um host Linux não produtivo com os pré-requisitos acima. Enquanto esse host não existir/estiver conectado, não é correto afirmar que o full gate independente foi executado, nem publicar o EJC como atualizado por inferência.
