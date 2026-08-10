# CI fora do GitHub Actions — fallback autônomo do EJC

## Objetivo

O GitHub permanece fonte de verdade para código, Issues, Pull Requests, review, branch protection e histórico. O fallback elimina **GitHub Actions/runner hospedado como executor único**, sem transformar a VPS de produção em runner.

A contingência só pode operar em **host Linux dedicado e não produtivo**, sem serviços co-residentes do EJC. `/opt/ejc`, banco de produção, containers de produção e o runner `ejc-vps` são proibidos.

Autorização administrativa: Issue #998. Hardening Staff do root of trust: Issue #1012.

## Modelo de confiança

A arquitetura é dividida em dois planos:

### Control plane — confiável

Executa sob o usuário controlador e contém:

- `gh` autenticado para leitura de PR/review e merge sujeito à branch protection;
- chave privada do GitHub App;
- emissão do Check Run promovível;
- evidência local;
- branch protection;
- watcher;
- merge.

**Código vindo do PR não pode executar nesse UID.**

### Worker plane — não confiável

Executa o código do PR sob `EJC_CI_WORKER_USER`, uma conta Unix exclusiva do CI:

- UID diferente do controlador e de root;
- fora de grupos `docker`, `sudo`, `wheel` e `adm`;
- sem sudo próprio;
- sem leitura/escrita do Docker socket;
- sem acesso à chave do GitHub App;
- sem acesso ao `hosts.yml` autenticado do `gh`;
- sem HOME persistente gravável;
- sem `at`;
- HOME, TMP e cache efêmeros por stage;
- PostgreSQL 16 + pgvector local sob o próprio UID, sem Docker.

O controlador pode executar **somente** `sudo -n -u <worker>`; o worker não pode elevar privilégio.

Após cada stage, processos residuais do UID são encerrados, arquivos desse UID em `/tmp`/`/dev/shm` são removidos, crontab do worker é apagado e o snapshot inteiro do stage é descartado.

## Invariantes

1. indisponibilidade nunca vira verde;
2. código do PR nunca executa no mesmo principal que controla `gh`, App, evidência ou merge;
3. cada stage recebe snapshot Git limpo do SHA exato;
4. uma tentativa nova invalida imediatamente sucesso local anterior do mesmo SHA;
5. sucesso exige os oito gates e seus logs íntegros;
6. Check Run exigido precisa pertencer ao App, SHA, `external_id` e execução canônica mais recente;
7. merge exige evidência atual, review aprovado, proteção íntegra e `main` compatível, revalidados no instante final;
8. produção nunca executa PR;
9. migrations potencialmente destrutivas e paths §6-A continuam retidos.

## `scripts/ci-worker-isolation.sh`

É a fronteira obrigatória entre control plane e código não confiável.

### Preflight

Antes da ativação e antes de executar um PR, valida:

- conta worker existente, não-root e diferente do controlador;
- ausência de grupos privilegiados;
- worker sem sudo próprio;
- worker sem Docker socket;
- worker incapaz de ler chave do App e config autenticada do `gh`;
- HOME cadastrado não gravável;
- Python 3.11, Node 22, Git, PostgreSQL client/server e pgvector;
- ausência do utilitário `at`.

Se qualquer invariante falhar, o fallback é **não ativável**.

### Snapshot por stage

Para cada gate:

1. o controlador resolve o SHA já buscado;
2. cria referência temporária local;
3. faz `git clone --no-hardlinks --single-branch` em árvore nova;
4. destaca o SHA exato;
5. remove `origin`;
6. injeta uma cópia read-only do **`ci-local.sh` trusted do control plane**, não o orquestrador eventualmente modificado pelo PR;
7. concede ACL somente ao worker e controlador no diretório efêmero;
8. executa o stage com `sudo -u worker env -i`;
9. encerra processos/persistência e remove o snapshot.

Fresh snapshot por stage evita que um teste anterior altere o código que um gate posterior examina. A escolha aumenta I/O, mas elimina cache poisoning e persistência lateral entre stages.

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

O modo promovível exige Python 3.11 e Node 22.

### Hermeticidade

Em execução trusted direta, o venv da aplicação é identificado por:

- versão exata do Python;
- SHA-256 de `backend/requirements.txt`.

Há `flock`, marker de conclusão e `pip check`. `pip-audit==2.10.0` usa venv de tooling separado, portanto não contamina o runtime da aplicação.

No fallback canônico, cada stage usa `STATE_ROOT` efêmero do worker, então não existe cache Python/Node persistente entre PRs/stages. Isso é deliberado: isolamento tem prioridade sobre throughput.

PGDATA, relatórios, tooling e restore report ficam fora do checkout/produção. Limpeza é limitada ao state root e não usa `rm -rf`.

PostgreSQL usa porta efêmera e bind `127.0.0.1`. Backend e continuity usam bancos independentes.

## `scripts/ci_evidence.py`

Máquina de estados de evidência por SHA:

```text
<evidence>/<sha>/
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

`start` atualiza atomicamente `latest-attempt`. Assim, iniciar B invalida imediatamente sucesso A sem apagar histórico.

`finish` só aceita a tentativa atual. Sucesso exige:

- `exit_code=0`;
- exatamente os oito logs;
- nenhum symlink/path traversal;
- hash SHA-256 e tamanho corretos;
- summary íntegro.

Ponteiros/summaries usam escrita atômica, `fsync`, arquivo 0600 e diretório 0700.

**Complexidade:** `start` O(1); finalização/verificação O(B), B = bytes totais dos logs; memória adicional O(1), com hashing em blocos de 1 MiB.

## `scripts/github-app-auth.sh`

O GitHub App é usado somente para Checks API.

A chave fica fora do repo/produção, é owner-only e não-symlink. O helper assina JWT RS256 curto e solicita installation token restrito:

- ao repositório EJC;
- a `checks:write`.

O token existe apenas em memória e é renovado antes do limite de uma hora.

Variáveis do control plane:

```text
EJC_FALLBACK_APP_ID
EJC_FALLBACK_APP_INSTALLATION_ID
EJC_FALLBACK_APP_PRIVATE_KEY_FILE
```

Nunca registrar conteúdo da chave/token em `.env` versionado, Issue, PR, chat ou log.

## `scripts/ci-fallback.sh`

É o control plane por PR.

Fluxo:

1. valida worker dedicado;
2. atualiza `origin/main`;
3. resolve SHA exato e confirma branch remota;
4. exige `origin/main` ancestral do SHA;
5. adquire lock por SHA;
6. renova credencial do App;
7. cria tentativa de evidência;
8. executa backend, eval, frontend, P0, arquitetura, continuity e UI no worker, cada um em snapshot novo;
9. executa governança com script trusted do controlador contra worktree do SHA apenas lido;
10. finaliza/promove evidência somente após os oito gates;
11. publica o Check Run agregado;
12. revalida governança, review, proteção, head, `main` e evidência;
13. repete o snapshot imediatamente antes do `PUT /merge` com SHA esperado.

Nenhum subprocesso do worker recebe `GH_TOKEN`, chave do App, `SSH_AUTH_SOCK` ou HOME do controlador.

## Check Run canônico

Required check do modo fallback:

```text
EJC Local Full Gate
```

Aceitação exige simultaneamente:

- ID exato da promoção;
- nome correto;
- SHA exato;
- `external_id` exato;
- `app.id` autorizado;
- completed/success;
- ser o matching check mais recente do App/contexto no SHA.

A consulta usa filtros server-side `check_name`, `app_id` e `filter=latest`.

Subgates `EJC Local / ...` são statuses informativos, nunca branch-protected.

## Promoção e merge

### `--promote-only`

Exige evidência atual e revalida governança, publica Check Run e **não chama merge**.

### `--merge-only`

Exige ainda:

- `origin/main` ancestral do SHA;
- head do PR == SHA;
- PR aberto/não-draft;
- `reviewDecision=APPROVED`;
- ausência de `retencao-humana`;
- `strict`, App/contexto corretos, review, CODEOWNERS, last-push approval, conversas resolvidas, histórico linear, sem force/delete;
- ausência de paths §6-A;
- migration destrutiva retida; patch ausente/truncado falha fechado.

O snapshot de segurança é executado novamente imediatamente antes do merge. O endpoint recebe `sha=<SHA esperado>`.

## Watcher e retry

`scripts/ci-fallback-watch.sh` trabalha apenas como control plane.

Falha de infraestrutura é identificada por:

1. log do stage da tentativa atual; ou
2. log da invocação quando falhou antes do primeiro stage.

Somente sinais externos qualificados (DNS, registry, reset/timeout, GitHub/npm/PyPI 429/502/503/504) entram em retry limitado com backoff exponencial.

Pytest/lint/typecheck/build/governança reais ficam retidos até novo SHA. Exit 75 significa contenção/indisponibilidade e não reprovação do código.

`AUTO_MERGE=0` usa `--promote-only`.

## Ativação transacional

`ci-fallback-activate.sh --enable` exige:

- host CI dedicado e não produtivo;
- nenhum serviço/container co-residente;
- main limpa == `origin/main`;
- controlador não-root;
- worker dedicado conforme preflight;
- Python 3.11, Node 22, PostgreSQL+pgvector;
- Git/gh/jq/flock/OpenSSL/cURL/sudo/setfacl;
- scheduler persistente (systemd user+linger ou cron ativo);
- App funcional em Checks API.

Ordem de ativação:

1. valida scripts/worker/App;
2. roda `ci-local fast` trusted na main;
3. limpa scheduler órfão e salva hooks;
4. cria `draining`;
5. instala watcher **ainda drenado**;
6. salva snapshot exato de required checks;
7. aplica `EJC Local Full Gate` ligado ao App;
8. confirma proteção;
9. grava `active.json`;
10. remove drain.

Falha após qualquer mutação tenta restaurar proteção, watcher e hooks.

### Desativação

1. cria drain;
2. adquire lock e espera execução atual;
3. restaura exatamente snapshot anterior dos required checks **com watcher ainda instalado**;
4. se restauração falha, remove drain e mantém watcher;
5. depois remove watcher;
6. restaura hooks;
7. remove estado.

Não use `--cloud` como substituto normal de `--disable`; o ativador restaura o snapshot real anterior.

## Branch protection

`branch-protection.sh` altera somente `required_status_checks`. Reviews, CODEOWNERS, restrictions e demais proteções não são reescritos.

`--fallback` requer autorização #998 e associa `EJC Local Full Gate` ao `app_id` esperado. `--restore` devolve exatamente o snapshot salvo.

O merge guard relê a proteção completa independentemente desse script.

## Governança local

O script executado é sempre o **trusted** do control plane. `EJC_GOV_SOURCE_ROOT` aponta para o snapshot do PR, que é lido sem executar seu `ci-local-governanca.sh` modificado.

A varredura é NUL-safe e O(B), B = bytes dos arquivos alterados.

Root of trust classificado como sensível:

- `ci-local.sh`;
- `ci-fallback*.sh`;
- `ci-worker-isolation.sh`;
- `ci_evidence.py`;
- `github-app-auth.sh`;
- branch protection/governança.

Mudança exige `security-auditor: executado`. Detector cobre `.env*`, private keys, AWS, OpenAI, Slack e famílias modernas de token GitHub.

## Performance e capacidade

O fallback canônico privilegia isolamento:

- evidência: O(B) tempo/O(1) memória;
- governança: O(bytes alterados);
- cada stage: novo clone/snapshot do SHA, portanto aproximadamente O(S) I/O por stage, S = tamanho materializado do repositório;
- nenhum cache de dependência não confiável é compartilhado entre stages/PRs;
- stages pesados continuam sequenciais para limitar pico de RAM/IO.

O custo de I/O é maior que um runner persistente, mas remove cache poisoning, persistência entre stages e acesso do PR ao root of trust. Otimizações futuras só devem usar cache read-only/verificado ou snapshots/reflinks após threat-model específico.

## Requisito de rede do host

O worker precisa de internet para npm/PyPI e testes externos permitidos, mas **não deve ter rota para produção ou redes privadas do escritório**. Essa restrição é responsabilidade da rede/security group/firewall do host dedicado e precisa ser provada no primeiro bootstrap. O repositório não deve fingir que consegue comprovar essa propriedade sozinho.

## Segurança/LGPD

- CI não requer PII/documento real;
- logs ficam no control plane com permissão restrita;
- nenhum segredo entra no worker;
- banco do worker é efêmero/loopback-only;
- produção não executa PR;
- Auth/RBAC/HITL/citation gate não são alterados;
- migration destrutiva não é auto-integrada.

## Bootstrap e limitação atual

A própria frente do fallback altera root of trust e é exceção §6-A. Não pode auto-integrar a si própria.

O primeiro full gate promovível exige host dedicado com:

- usuário controlador;
- worker Unix isolado;
- sudoers mínimo controlador→worker;
- Python 3.11/Node 22;
- PostgreSQL 16 + pgvector;
- isolamento de rede de produção/private services;
- App/checks configurado.

Enquanto esse host não estiver disponível e testado, **não afirmar que o full gate independente foi executado ou que as alterações estão publicadas**.
