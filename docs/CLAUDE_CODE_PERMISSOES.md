# Permissões do Claude Code no EJC

**Estado: aplicado em `.claude/settings.json` (2026-08-02), por autorização explícita do
titular.** Este documento registra o que foi aplicado e por quê.

Ele nasceu como proposta não aplicada, e a razão importa: um agente não concede permissões a si
mesmo. A lista foi escrita e justificada aqui, e só entrou em vigor quando o titular mandou
aplicar. Qualquer alteração futura desta lista segue a mesma regra — proposta primeiro,
autorização depois.

## Por que

Hoje `.claude/settings.json` não tem bloco `permissions`. Consequência prática: todo comando
de shell — inclusive `git status`, `pytest` e `npm run lint` — passa por aprovação. Numa
sessão longa isso produz dezenas de interrupções para comandos que não mudam nada, e o custo
real não é o clique: é que aprovar vira reflexo, e aí a aprovação deixa de filtrar o comando
que **de fato** merecia atenção.

A proposta é a inversa da intuição: **liberar explicitamente o que é rotina e sem efeito
colateral**, para que cada prompt restante signifique alguma coisa.

## O que está aplicado

O bloco abaixo vive em `.claude/settings.json`, no mesmo nível de `hooks`. Está **versionado de
propósito**: `.gitignore` (linha 67) ignora `.claude/settings.local.json`, e as sessões do Claude
Code na web clonam o repositório do zero — um arquivo ignorado pelo git não existiria nelas.
Permissão que só vale na máquina de quem editou não serve para este repositório.

```json
{
  "permissions": {
    "allow": [
      "Bash(git status:*)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(git show:*)",
      "Bash(git branch:*)",
      "Bash(git fetch:*)",
      "Bash(git add:*)",
      "Bash(git checkout:*)",
      "Bash(git switch:*)",
      "Bash(git rev-parse:*)",
      "Bash(git ls-files:*)",
      "Bash(graphify:*)",
      "Bash(ruff check:*)",
      "Bash(pytest:*)",
      "Bash(python -m pytest:*)",
      "Bash(python -m alembic heads:*)",
      "Bash(python -m alembic current:*)",
      "Bash(python -m alembic history:*)",
      "Bash(npm run lint:*)",
      "Bash(npm test:*)",
      "Bash(npm run build:*)",
      "Bash(npm ci:*)",
      "Bash(scripts/ci-local.sh:*)"
    ],
    "deny": [
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      "Bash(git reset --hard:*)",
      "Bash(git clean -fd:*)",
      "Bash(docker compose down -v:*)",
      "Bash(docker volume rm:*)",
      "Bash(dropdb:*)",
      "Bash(alembic downgrade base:*)",
      "Read(./.env)",
      "Read(./vps-tools/.env)"
    ]
  }
}
```

## Revisão de 2026-08-07 — comandos de escrita de git e comandos `gh`

Por pedido explícito do titular, a lista acima ganhou os comandos de escrita do ciclo normal
de trabalho (`git commit`, `git checkout`, `git switch`, `git pull`, `git merge`, `git rebase`,
`git remote`, `git stash`) e os comandos `gh` de PR, Issue e Actions. O bloco vigente é o de
`.claude/settings.json` — este documento descreve as decisões, não duplica a lista.

**Risco e justificativa.** O ganho é fechar os travamentos e os prompts repetidos do fluxo
Issue → branch → PR. O custo é que o prompt de permissão deixa de ser a última barreira em
comandos que saem da sessão. Três entradas foram recusadas na auditoria justamente por isso e
**não** entraram na forma pedida:

- `gh api *` — `gh api -X POST .../deploy-vps.yml/dispatches` dispara o deploy de produção
  (`deploy-vps.yml` é `workflow_dispatch`), e `-X PUT /repos/.../contents/...` escreve direto
  na `main`. Entrou apenas `gh api graphql -f query=*`, que é leitura.
- `gh pr merge *` — merge é ato humano (regra 8). Ficou no `deny`.
- `git push *` — permite `git push origin HEAD:main`. Entrou como `git push -u origin *`,
  com `main`/`master` e refspecs `HEAD:` no `deny`.

**Rollback.** Reverter o commit que introduziu o bloco restaura o estado de 2026-08-02; o
arquivo é só configuração, sem migration nem efeito em runtime do app.

**Limite conhecido.** O `deny` é declarativo e casa texto de comando: `git remote "set-url"`
com o subcomando entre aspas escapa tanto do `deny` quanto do hook, que descarta literais
citados antes de aplicar os padrões. Fechar isso exige corrigir `guarda_comandos.py`, e está
fora do escopo desta revisão.

## O que deliberadamente ficou de fora

- **`git push` para `main`/`master` e refspecs `HEAD:`** — estão em `deny`, não em prompt.
  A branch de destino não é detalhe de forma: é a regra 1 da governança.
- **`gh pr merge` e `gh workflow run`** — em `deny`. Merge e deploy são atos humanos
  (regra 8 e regra 9).
- **`docker compose up`, `alembic upgrade`, `pip install`, `rm`** — mudam estado da máquina
  ou do banco. Aprovação caso a caso.
- **Leitura de `.env`** — está em `deny`, não em silêncio: segredo não entra em contexto de
  modelo (`GOVERNANCA_IA.md` §7).

## Relação com o guarda de comandos

O bloco `deny` acima e o hook `.claude/hooks/guarda_comandos.py` cobrem o mesmo conjunto de
comandos proibidos, de propósito. O `deny` é declarativo e o titular lê num relance; o hook
entende contexto que o `deny` não alcança — que `rm -rf /tmp/x` é legítimo e `rm -rf backend`
não, que citar `git push --force` dentro de aspas num documento não é executá-lo, e que
`git commit` estando na `main` viola `GOVERNANCA_IA.md` §6.1. Nenhum dos dois substitui o
outro; o hook tem teste de regressão em `backend/tests/test_guarda_comandos_hook.py`.
