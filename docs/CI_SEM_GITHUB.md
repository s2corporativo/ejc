# CI fora do GitHub Actions — fallback autônomo do EJC

## Objetivo

O GitHub continua sendo o repositório remoto e o plano de controle de PR/status/merge. **GitHub Actions/runner não é executor único nem ponto de bloqueio operacional.**

Quando Actions/runner estiver indisponível, o EJC valida o SHA em máquina Linux **não produtiva**, em worktree isolado, com PostgreSQL 16 + pgvector efêmero, evidência local content-addressed e Check Run de GitHub App dedicado. Produção não participa da CI de PR.

Autorização administrativa: **Issue #998**.

## Invariantes não negociáveis

1. fallback promovível nunca roda em `/opt/ejc`, host marcado como produção, root ou host com containers canônicos do EJC;
2. Python 3.11, Node 22 e PostgreSQL 16 são o baseline promovível;
3. banco CI é efêmero e loopback-only;
4. nenhuma credencial/token é versionada ou persistida em evidência;
5. `EJC Local Full Gate` só fica verde para o **Check Run exato** criado na promoção atual, no SHA exato e pelo App ID exato;
6. migrations com diff ausente/truncado são retidas fail-closed;
7. alteração da branch protection é restrita a `required_status_checks`; reviews/CODEOWNERS/restrictions e demais políticas não são reconstruídos pelo fallback;
8. evidência aprovada é imutável: tentativa, summary e hashes de logs são verificados antes de republicação/merge;
9. `--disable` é transacional e usa drain + lock do watcher;
10. falha de API/runner/rede nunca é traduzida em verde.

## `scripts/ci-local.sh`

Gates disponíveis:

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

### Estado e hermeticidade

Todos os artefatos mutáveis — PGDATA, venv, relatórios, cobertura, screenshots e restore report — devem ficar sob `EJC_CI_STATE_ROOT` (default sob cache do usuário). Overrides que escapem dessa raiz, apontem para o repositório ou `/opt/ejc` são rejeitados antes de escrita.

A limpeza usa somente caminhos descendentes da raiz de estado e não usa `rm -rf`.

O venv da aplicação é identificado por:

```text
versão exata do Python + SHA-256 de backend/requirements.txt
```

`CI_SKIP_PIP=1` só reutiliza o venv correspondente; ambiente ausente falha fechado.

### PostgreSQL

Preferência: `pgvector/pgvector:pg16` em Docker, bind `127.0.0.1:<porta-efêmera>`.

Fallback local aceita apenas PostgreSQL major 16 em execução promovível. Host auth é SCRAM; trust fica limitado à conexão local do cluster efêmero. `EJC_ALLOW_POSTGRES_MISMATCH=1` é diagnóstico, não evidência promovível.

Backend e continuity usam ciclos de banco independentes e encerram o banco ao fim de cada estágio.

## `scripts/ci-fallback.sh`

Fluxo para `--pr <N>`:

1. atualiza `origin/main`;
2. resolve e fixa `headRefOid`;
3. exige que a main atual seja ancestral do SHA;
4. adquire **lock exclusivo por SHA**; concorrente retorna `75` (TEMPFAIL), sem alterar evidência;
5. valida a credencial efêmera do GitHub App antes da suíte pesada;
6. cria tentativa única em worktree descartável;
7. executa backend, eval, frontend, P0, governança, arquitetura, continuidade e UI/browser;
8. grava logs somente localmente;
9. finaliza tentativa com hashes SHA-256 e tamanhos;
10. em sucesso, atualiza atomicamente `latest-success.json` para apontar para a tentativa imutável;
11. revalida o corpo atual do PR;
12. publica `EJC Local Full Gate` pelo App dedicado;
13. verifica **o ID exato** desse Check Run, SHA, App ID, nome e conclusão;
14. somente então avalia merge.

### Evidência

Estrutura conceitual:

```text
<state>/evidence/<sha>/
  .lock
  latest-attempt.json
  latest-success.json
  attempts/
    <timestamp-pid-random>/
      backend.log
      ...
      summary.json
```

`summary.json` contém hashes/tamanhos dos logs. `latest-success.json` contém hash do summary. Antes de promoção/merge, `scripts/ci_evidence.py verify` recalcula tudo em streaming.

Complexidade do hashing: **O(n) tempo e O(1 MiB) de memória adicional**, independentemente do tamanho total dos logs.

### Retenção

`scripts/ci_evidence.py prune` implementa retenção lock-aware:

- default: até 200 SHAs;
- janela default: 30 dias;
- até 5 tentativas não referenciadas por SHA;
- nunca remove SHA com lock ativo;
- preserva a tentativa apontada por `latest-success` e `latest-attempt`;
- não segue symlinks.

O watcher executa manutenção no máximo uma vez por dia. Marcadores auxiliares antigos podem ser removidos; perda desses marcadores causa apenas revalidação, nunca falso verde.

## GitHub App e credencial efêmera

Configuração exigida no host não produtivo:

```text
EJC_FALLBACK_APP_ID=<id numérico>
EJC_FALLBACK_INSTALLATION_ID=<installation id>
EJC_FALLBACK_APP_PRIVATE_KEY_FILE=<caminho absoluto fora do repo e de /opt/ejc>
```

A chave privada:

- não pode ser symlink;
- precisa pertencer ao usuário do fallback;
- não pode possuir permissão de grupo/outros;
- nunca é copiada para o repositório.

`scripts/github-app-auth.sh` gera JWT RS256 em memória e solicita installation token **escopado ao repositório EJC e `checks:write`**. O token fica apenas em memória e é renovado antes de expirar. O código não assume o formato legado de token de 40 caracteres.

O `gh` de usuário permanece para leitura de PR, branch protection e tentativa de merge; a credencial do App é usada somente na Checks API.

## Check Run promovível

Subgates informativos:

```text
EJC Local / Backend
EJC Local / Eval
EJC Local / Frontend
EJC Local / P0 Guard
EJC Local / Governança
```

Gate promovível:

```text
EJC Local Full Gate
```

O runner mantém `FULL_CHECK_ID`. Um sucesso histórico com o mesmo nome não é aceito. `full_gate_is_green()` consulta somente `check-runs/<FULL_CHECK_ID>` e exige simultaneamente:

- SHA alvo;
- App ID esperado;
- nome exato;
- `status=completed`;
- `conclusion=success`.

## `--promote-only` e `--merge-only`

Ambos exigem evidência local íntegra do SHA e revalidam a governança atual do PR.

`--promote-only` apenas cria/publica o Check Run da promoção atual.

`--merge-only` também verifica:

- SHA atual do PR;
- draft;
- `retencao-humana`;
- paths de exceção §6-A;
- migrations;
- branch protection/reviews remotos no momento da tentativa.

### Migrations

A lista de arquivos é obtida pela API de files do PR. Se a chamada falhar, a resposta for inválida ou qualquer migration vier com `patch=null`, o merge é retido. O fallback **não** interpreta ausência de diff como segurança.

Padrões destrutivos (`drop`, `alter_column`, SQL DROP/TRUNCATE/DELETE etc.) mantêm retenção humana.

## Watcher incremental

`scripts/ci-fallback-watch.sh` lista PRs abertos para `main`, mas o trabalho caro é incremental.

Fingerprint por PR:

```text
SHA | updatedAt | mergeState | autoMergeMode
```

PR verde sem alteração não é reprocessado a cada ciclo. Há recheck periódico de segurança (default 30 min).

Assim, o scan de listagem permanece O(P) em número de PRs, mas promoção/revalidação pesada tende a **O(PRs alterados)** em estado estável.

Falha transitória de infraestrutura usa backoff exponencial e limite. Falha real de teste não repete indefinidamente no mesmo SHA.

Exit `75` do lock por SHA é TEMPFAIL/pending, nunca falha de código.

## Branch protection: alteração mínima e reversível

`scripts/governanca/branch-protection.sh` usa exclusivamente o sub-recurso:

```text
/branches/main/protection/required_status_checks
```

Não faz `PUT` da proteção completa.

### Ativar fallback

O script salva snapshot exato dos required status checks atuais e recusa sobrescrever snapshot residual.

```bash
EJC_FALLBACK_AUTHORIZATION=998 \
EJC_FALLBACK_APP_ID=<app-id> \
EJC_BRANCH_PROTECTION_BACKUP=<arquivo-de-estado> \
  bash scripts/governanca/branch-protection.sh --fallback
```

O fallback exige somente `EJC Local Full Gate` + App ID esperado. Reviews, CODEOWNERS, restrictions, enforce-admins, histórico linear, resolução de conversas, force-push/deletion e futuras propriedades continuam intocados por construção.

### Restaurar

```bash
EJC_BRANCH_PROTECTION_BACKUP=<arquivo-de-estado> \
  bash scripts/governanca/branch-protection.sh --restore
```

`--restore` reaplica **exatamente** strict/checks salvos antes da contingência.

`--cloud` existe para aplicar os cinco checks cloud canônicos, mas a desativação transacional usa `--restore`, não uma reconstrução presumida.

## Ativação persistente

```bash
EJC_FALLBACK_APP_ID=<app-id> \
EJC_FALLBACK_INSTALLATION_ID=<installation-id> \
EJC_FALLBACK_APP_PRIVATE_KEY_FILE=/caminho/owner-only/app.pem \
bash scripts/ci-fallback-activate.sh --enable
```

Pré-condições:

- host não produtivo;
- usuário não root;
- Docker acessível e sem containers canônicos;
- `gh` do usuário autenticado;
- Python 3.11 / Node 22 / npm / psql / jq / openssl / curl / flock;
- main limpa e idêntica a `origin/main`;
- scheduler persistente;
- sintaxe dos componentes;
- `ci-local.sh fast` verde;
- GitHub App consegue criar Check Run com App ID esperado.

O estado operacional usa uma raiz única `EJC_CI_STATE_ROOT`/XDG cache compartilhada por ativador, scheduler, watcher, evidência e drain.

Ativação é transacional: falha após mudar status checks tenta restaurar o snapshot anterior, watcher e hooks.

## Desativação transacional

```bash
bash scripts/ci-fallback-activate.sh --disable
```

Ordem:

1. cria `draining` atomicamente;
2. adquire o mesmo lock do scheduler/watcher;
3. restaura **exatamente** os required status checks anteriores;
4. remove/desabilita watcher;
5. restaura `core.hooksPath` local;
6. remove active/snapshot/drain apenas ao concluir.

Se a restauração da proteção falhar, o drain é removido e o watcher continua instalado. Se a proteção for restaurada mas a remoção do scheduler falhar, o drain **permanece**, fazendo qualquer executor residual virar no-op.

## Segurança e LGPD

- sem execução de CI de PR em produção;
- sem banco de produção;
- sem chave/token em repositório, logs ou evidência;
- App token com privilégio mínimo (`checks:write`, repositório EJC);
- worktree descartável;
- PG efêmero e loopback-only;
- evidência com permissões restritas;
- branch protection não é reconstruída integralmente;
- migrations sem prova suficiente são retidas;
- review/CODEOWNERS e exceções §6-A permanecem controles independentes;
- RBAC, HITL, LGPD, citation gate e sanitização de PII da aplicação não são alterados.

## Bootstrap

A PR que introduz esse fallback altera `scripts/` e governança; portanto ela própria continua exceção §6-A e não deve usar o mecanismo que ainda não existe em `main` para auto-integrar a si mesma.

O bootstrap precisa de validação/revisão independente e integração protegida sem bypass. Depois de integrado, indisponibilidade de GitHub Actions deixa de interromper a execução do CI do EJC.
