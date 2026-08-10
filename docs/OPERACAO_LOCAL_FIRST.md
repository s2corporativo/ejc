# Operação local-first do EJC

Decisão do titular: 2026-08-09. Registro: Issue #1000.

## Objetivo

O GitHub deixa de ser dependência para **continuar desenvolvimento, checkpoint e validação**. Ele permanece como repositório remoto, histórico, revisão e sincronização quando disponível.

A indisponibilidade de GitHub, GitHub Actions ou runner não deve fazer o agente parar nem pedir ao titular qual alternativa usar. O caminho automático passa a ser:

```text
cópia/worktree isolado
  → edição
  → checkpoint local sem segredos/dados
  → scripts/ci-local.sh
  → correção local até verde
  → tentativa de sync não destrutiva quando origin voltar
  → PR/revisão/integração remota como confirmação
```

**Produção não é workspace.** Este wrapper não publica código nem opera `/opt/ejc`. O deploy continua na esteira segura existente (`scripts/deploy_vps_safe.sh`) depois que a versão validada estiver integrada/sincronizada. Isso evita criar um segundo pipeline de produção e evita copiar `.env` para worktrees.

## Comando único

Use `scripts/operacao-local-first.sh`.

```bash
# Diagnóstico do diretório e identidade local
scripts/operacao-local-first.sh status

# Cria worktree Git local sem acessar remoto; sem .git, cria cópia isolada via rsync
scripts/operacao-local-first.sh prepare p01-vigencia

# Checkpoint de código sem .env, uploads, dados, backups, caches ou build
scripts/operacao-local-first.sh checkpoint <worktree>

# Alias compatível
scripts/operacao-local-first.sh snapshot <worktree>

# Validação completa fora do GitHub Actions
scripts/operacao-local-first.sh validate <worktree>

# Quando origin estiver disponível: fetch + push normal, nunca force
scripts/operacao-local-first.sh sync <worktree>
```

`EJC_CI_MODE=full` é o padrão. Para uma rodada intermediária rápida:

```bash
EJC_CI_MODE=fast scripts/operacao-local-first.sh validate <worktree>
```

## Identidade local

A prova do código em trabalho não depende do GitHub.

1. Se existe `.git` e a árvore tracked está limpa, usa o SHA local do commit.
2. Se há alteração tracked não commitada, calcula fingerprint SHA-256 determinístico de todos os arquivos versionados existentes e expõe `local-<40 hex>`.
3. Sem `.git`, calcula fingerprint apenas do código/config/documentação versionável, excluindo segredos, dados e artefatos.

Com Git, `git ls-files` é a fonte da lista: arquivos não versionados como `.env`, uploads e dados reais não entram na identidade.

## GitHub indisponível

Quando GitHub/conector/Actions falhar:

1. classificar se é falha de infraestrutura ou falha real do código;
2. para 5xx, timeout, rate limit, runner indisponível ou job que morreu antes do primeiro step, não insistir indefinidamente no Actions;
3. continuar no worktree/cópia isolada;
4. criar checkpoint antes de mudanças de risco;
5. reproduzir o gate com `scripts/ci-local.sh` e corrigir localmente;
6. manter commits/checkpoints locais;
7. tentar `sync` quando origin voltar.

O comando `sync` usa somente `fetch` e `push` normais. Se o remoto estiver indisponível, retorna **75 (TEMPFAIL)** e preserva o trabalho local. Se a branch remota avançou ou divergiu, falha fechado: não faz rebase automático, reset nem force-push.

A indisponibilidade do GitHub é problema de sincronização/auditoria remota, não prova de defeito do código. Por outro lado, falha de CI local continua bloqueante.

## Segurança e LGPD

O modo local-first não reduz controles:

- `/opt/ejc` e seus subdiretórios são recusados como workspace;
- worktrees/checkpoints ficam fora do diretório produtivo;
- `.env`, uploads, data, backups, caches e builds não entram em cópia sem Git;
- com Git, checkpoint usa apenas arquivos tracked;
- não usa `git push --force`, `git reset --hard` ou `git clean -fd`;
- não altera RBAC, HITL, citation gate, sanitização de PII ou kill-switch;
- não cria banco de produção nem acessa credenciais para validar código;
- não cria segundo pipeline de deploy.

## Por que o wrapper não faz deploy direto do worktree

`deploy_vps_safe.sh` usa o diretório produtivo e o `.env` preservado do VPS. Um worktree de desenvolvimento **não deve conter esse `.env`**. Fazer `APP_DIR=<worktree>` falharia corretamente por ausência do segredo; copiar ou linkar o `.env` para contornar isso ampliaria a superfície de exposição.

Por isso, desenvolvimento/CI ficam independentes do GitHub, mas publicação continua no único pipeline de produção já endurecido, com backup, health/readiness e rollback. A indisponibilidade remota não justifica inventar uma segunda esteira menos auditável.

## Checkpoint local

O checkpoint gera, por padrão em `$HOME/.local/state/ejc/snapshots`:

- `source.tar.gz`;
- `source.tar.gz.sha256`;
- `source_id.txt`;
- lista de arquivos tracked quando houver Git.

Nenhum desses artefatos é criado dentro do repositório.

## Checklist operacional

- [ ] trabalho em cópia/worktree isolado
- [ ] workspace diferente de `/opt/ejc`
- [ ] checkpoint sem segredo/PII
- [ ] `scripts/ci-local.sh full` verde
- [ ] alterações commitadas localmente
- [ ] sync remoto tentado sem force/rewrite
- [ ] PR/review quando GitHub estiver disponível
- [ ] deploy somente pela esteira produtiva já existente
- [ ] backup/health/readiness/rollback preservados
