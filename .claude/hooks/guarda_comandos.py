#!/usr/bin/env python3
"""Guarda de comandos destrutivos do EJC (hook PreToolUse de Bash).

Transforma em bloqueio automático as proibições que hoje existem apenas em
prosa: `CLAUDE.md` regra 12, `AGENTS.md` "Limites que nenhum agente ultrapassa"
e `docs/GOVERNANCA_IA.md` seções 6.1, 6.10 e 7.

Regra de desenho: bloquear pouco e com precisão. Um guarda que dispara em falso
ensina o agente a contorná-lo, e aí não guarda nada. Cada padrão abaixo cobre
um comando que o repositório proíbe por escrito — nada além disso.

Escape consciente: `EJC_GUARDA_OFF=1` desliga o guarda para a sessão. Existe
para não travar uma emergência do titular, não para uso de rotina.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

DOC = "CLAUDE.md regra 12 / GOVERNANCA_IA.md §6.10"

# (regex, motivo). Aplicados sobre o comando bruto.
PADROES: list[tuple[str, str]] = [
    (
        r"--dangerously-skip-permissions",
        f"`--dangerously-skip-permissions` é proibido no EJC ({DOC}).",
    ),
    (
        r"\bgit\s+push\b[^|;&]*(--force\b|--force-with-lease\b|(?<![\w-])-f(?![\w-]))",
        f"Force push é proibido no EJC ({DOC}). Resolva por merge/rebase e push normal.",
    ),
    (
        r"\bgit\s+reset\s+--hard\b",
        f"`git reset --hard` é proibido — descarta trabalho sem rastro ({DOC}). "
        "Use `git restore <arquivo>` ou `git stash`.",
    ),
    (
        r"\bgit\s+clean\b[^|;&]*-[A-Za-z]*(fd|df)",
        f"`git clean -fd` é proibido ({DOC}). Remova arquivos um a um, conferindo antes.",
    ),
    (
        r"\bdocker\s+compose\b[^|;&]*\bdown\b[^|;&]*(--volumes\b|(?<![\w-])-v(?![\w-]))",
        f"`docker compose down -v` apaga os volumes (banco e uploads) — proibido ({DOC}). "
        "Use `docker compose down` sem `-v`.",
    ),
    (
        r"\bdocker\s+volume\s+rm\b",
        f"`docker volume rm` apaga dado persistente — proibido ({DOC}).",
    ),
    (
        r"\bdropdb\b|\bDROP\s+DATABASE\b",
        f"Derrubar banco é proibido ({DOC}).",
    ),
    (
        r"\balembic\s+downgrade\s+base\b",
        f"`alembic downgrade base` zera o schema — proibido ({DOC}).",
    ),
    (
        r"(?:\bcd\b|\brsync\b|\bscp\b|\bssh\b|\brm\b|\bmv\b|\bcp\b|\btee\b|\bchown\b|\bchmod\b|>)"
        r"[^|;&]*/opt/ejc",
        "`/opt/ejc` na VPS É a produção — nenhum agente opera nela "
        "(GOVERNANCA_IA.md §7, FLUXO_DE_DESENVOLVIMENTO.md 'Ambientes').",
    ),
]

# `rm -rf` recebe tratamento próprio: o scratchpad e /tmp são uso legítimo.
RM_RECURSIVO = re.compile(r"\brm\s+(-[A-Za-z]*\s+)*-?[A-Za-z]*[rR][A-Za-z]*f|\brm\s+-[A-Za-z]*f[A-Za-z]*[rR]")

GIT_MUTANTE = re.compile(r"\bgit\s+(commit|push|merge|rebase|cherry-pick|revert)\b")

# Literais entre aspas são DADO, não comando: `grep -rn "rm -rf" docs/` cita a
# proibição, não a executa. Casar substring na linha inteira — o defeito dos
# hooks antigos — transforma citação em bloqueio e ensina a contornar o guarda.
CITACAO = re.compile(r"'[^']*'|\"[^\"]*\"|<<'?EOF'?.*?EOF", re.DOTALL)


def sem_citacoes(cmd: str) -> str:
    """Comando com os literais entre aspas substituídos por um marcador neutro."""
    return CITACAO.sub(" ARG ", cmd)


def nega(motivo: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": motivo,
                }
            }
        )
    )
    sys.exit(0)


OPERADORES = {"&&", "||", "|", ";", "&"}


def alvos_rm(cmd: str) -> list[str]:
    """Caminhos passados a `rm`, já sem as aspas e sem as flags.

    Extraídos do comando ORIGINAL: `rm -rf "$TMPDIR/x"` tem alvo legítimo, e
    olhar só a versão com as citações removidas perderia o caminho.
    """
    try:
        tokens = shlex.split(cmd)
    except ValueError:  # aspas desbalanceadas — não dá para afirmar nada
        return ["<comando não parseável>"]
    if "rm" not in tokens:
        return []
    alvos: list[str] = []
    for token in tokens[tokens.index("rm") + 1 :]:
        if token in OPERADORES:
            break
        if not token.startswith("-"):
            alvos.append(token)
    return alvos


def temporario(alvo: str) -> bool:
    """Caminho seguro para apagar em massa: /tmp, /var/tmp e $TMPDIR."""
    return alvo.startswith(("/tmp/", "/var/tmp/", "$TMPDIR", "${TMPDIR"))


def branch_atual() -> str:
    try:
        r = subprocess.run(
            ["git", "symbolic-ref", "--short", "-q", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def main() -> None:
    if os.environ.get("EJC_GUARDA_OFF") == "1":
        return
    try:
        dados = json.load(sys.stdin)
    except Exception:
        return
    bruto = str((dados.get("tool_input") or {}).get("command") or "")
    if not bruto:
        return
    cmd = sem_citacoes(bruto)

    for padrao, motivo in PADROES:
        if re.search(padrao, cmd, re.IGNORECASE):
            nega(motivo)

    if RM_RECURSIVO.search(cmd):
        fora = [a for a in alvos_rm(bruto) if not temporario(a)]
        if fora:
            variavel = [a for a in fora if "$" in a]
            detalhe = (
                "Alvo em variável não é verificável antes de expandir — use caminho literal: "
                f"{', '.join(variavel)}."
                if variavel
                else f"Alvo(s): {', '.join(fora)}. Apague arquivo a arquivo, conferindo antes."
            )
            nega(f"`rm -rf` fora de /tmp é proibido ({DOC}). {detalhe}")

    if GIT_MUTANTE.search(cmd) and branch_atual() in {"main", "master"}:
        nega(
            "Você está na `main`. Nenhum agente commita, empurra ou mescla na main "
            "(GOVERNANCA_IA.md §6.1). Crie a branch da tarefa antes: "
            "`git checkout -b <tipo>/<descricao>`."
        )


if __name__ == "__main__":
    main()
