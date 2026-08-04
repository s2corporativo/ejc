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

## O que deliberadamente ficou de fora

- **`git commit` e `git push`** — continuam pedindo aprovação. São os pontos onde o trabalho
  do agente sai da sessão e vira histórico; vale o clique.
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
