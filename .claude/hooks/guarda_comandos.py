#!/usr/bin/env python3
"""Guarda de comandos sensíveis e destrutivos do EJC (hook PreToolUse de Bash).

Converte em bloqueio automático as proibições de governança e impede que
permissões Bash de diagnóstico sejam usadas para ler segredos, alterar remotes
ou tags, executar scripts de instalação não autorizados ou apontar Compose para
arquivos externos/produção.

Regra de desenho: bloquear com precisão. Citar uma proibição em documentação
não é executá-la; ler `.env.example` também continua permitido.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import PurePosixPath

DOC = "CLAUDE.md regra 12 / GOVERNANCA_IA.md §§6, 7 e 10"

# (regex, motivo). Aplicados sobre o comando sem literais citados.
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
        r"\bgit\s+remote\s+(add|remove|rm|rename|set-url|set-head|prune|update)\b",
        "Mutação de remote é proibida para agentes. Use apenas `git remote -v` ou "
        "`git remote get-url` e registre qualquer alteração para execução humana.",
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
        r"(?:\bcd\b|\brsync\b|\bscp\b|\brm\b|\bmv\b|\bcp\b|\btee\b|\bchown\b|\bchmod\b|>)"
        r"[^|;&]*/opt/ejc",
        "`/opt/ejc` na VPS É a produção — nenhum agente opera nela "
        "(GOVERNANCA_IA.md §7, FLUXO_DE_DESENVOLVIMENTO.md 'Ambientes').",
    ),
]

# `rm -rf` recebe tratamento próprio: o scratchpad e /tmp são uso legítimo.
RM_RECURSIVO = re.compile(
    r"\brm\s+(-[A-Za-z]*\s+)*-?[A-Za-z]*[rR][A-Za-z]*f"
    r"|\brm\s+-[A-Za-z]*f[A-Za-z]*[rR]"
)

GIT_MUTANTE = re.compile(r"\bgit\s+(commit|push|merge|rebase|cherry-pick|revert)\b")

# Literais entre aspas são DADO, não comando para as regras destrutivas:
# `grep -rn "rm -rf" docs/` cita a proibição. A inspeção de arquivos sensíveis
# usa o comando bruto e um parser separado, portanto caminhos citados continuam
# protegidos (`cat ".env"` é negado).
CITACAO = re.compile(r"'[^']*'|\"[^\"]*\"|<<'?EOF'?.*?EOF", re.DOTALL)

OPERADORES = {"&&", "||", "|", ";", "&"}
SEPARADORES = OPERADORES | {"<", ">", "<<", ">>", "2>", "2>>"}

LEITORES_TODOS_ARGUMENTOS = {
    "cat",
    "head",
    "tail",
    "less",
    "more",
    "nl",
    "strings",
    "base64",
    "xxd",
    "cp",
    "mv",
    "rsync",
    "scp",
    "tar",
    "zip",
    "source",
    ".",
}
LEITORES_COM_EXPRESSAO = {"grep", "egrep", "fgrep", "rg", "sed", "awk", "jq", "yq"}
EXTENSOES_SECRETAS = {".key", ".pem", ".p12", ".pfx", ".jks", ".keystore"}
NOMES_SECRETOS = re.compile(
    r"^(?:credentials?|service[-_]?account|client[-_]?secret|secrets?)(?:[._-].*)?$",
    re.IGNORECASE,
)


def sem_citacoes(cmd: str) -> str:
    """Comando com os literais entre aspas substituídos por marcador neutro."""
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


def tokens_shell(cmd: str) -> list[str]:
    """Tokeniza operadores básicos sem executar expansão de shell."""
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars="|&;<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return []


def segmentos_shell(cmd: str) -> list[list[str]]:
    """Divide uma linha em comandos simples para identificar leitores e arquivos."""
    segmentos: list[list[str]] = []
    atual: list[str] = []
    for token in tokens_shell(cmd):
        if token in OPERADORES:
            if atual:
                segmentos.append(atual)
                atual = []
            continue
        atual.append(token)
    if atual:
        segmentos.append(atual)
    return segmentos


def normaliza_caminho(token: str) -> str:
    caminho = token.strip().replace("\\", "/")
    while caminho.startswith("./"):
        caminho = caminho[2:]
    return caminho


def caminho_secreto(token: str) -> bool:
    """True para arquivos de ambiente, credencial ou chave privada.

    `.env.example` é documentação pública e permanece liberado.
    """
    caminho = normaliza_caminho(token)
    if not caminho or caminho.startswith("-"):
        return False
    nome = PurePosixPath(caminho).name.lower()
    if nome == ".env.example":
        return False
    if nome == ".env" or nome.startswith(".env."):
        return True
    if NOMES_SECRETOS.match(nome):
        return True
    if nome in {"id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"}:
        return True
    return PurePosixPath(nome).suffix.lower() in EXTENSOES_SECRETAS


def argumentos_nao_opcao(args: list[str]) -> list[str]:
    """Remove flags simples; valores restantes podem conter caminhos."""
    return [arg for arg in args if arg not in SEPARADORES and not arg.startswith("-")]


def caminhos_do_leitor(comando: str, args: list[str]) -> list[str]:
    """Extrai operandos que podem representar arquivos lidos/copiados.

    Para grep/rg/sed/awk/jq/yq, o primeiro argumento posicional costuma ser
    expressão/filtro. Quando `-e`, `-f` ou `--files` já definiu o modo, todos os
    posicionais são tratados como possíveis caminhos.
    """
    posicionais = argumentos_nao_opcao(args)
    if comando in LEITORES_TODOS_ARGUMENTOS:
        return posicionais
    if comando not in LEITORES_COM_EXPRESSAO:
        return []

    padrao_por_opcao = any(
        arg in {"-e", "--regexp", "-f", "--file", "--files", "--files-with-matches"}
        or arg.startswith(("-e=", "--regexp=", "-f=", "--file="))
        for arg in args
    )
    if padrao_por_opcao:
        return posicionais
    return posicionais[1:] if len(posicionais) > 1 else []


def leitura_segredo(cmd: str) -> str | None:
    """Retorna o caminho sensível alcançado por leitor shell, se houver."""
    tokens = tokens_shell(cmd)
    for indice, token in enumerate(tokens[:-1]):
        if token == "<" and caminho_secreto(tokens[indice + 1]):
            return tokens[indice + 1]

    for segmento in segmentos_shell(cmd):
        if not segmento:
            continue
        indice = 0
        while indice < len(segmento) and (
            "=" in segmento[indice] and not segmento[indice].startswith(("/", "./"))
        ):
            indice += 1
        while indice < len(segmento) and segmento[indice] in {"sudo", "command", "env"}:
            indice += 1
        if indice >= len(segmento):
            continue
        comando = PurePosixPath(segmento[indice]).name
        args = segmento[indice + 1 :]
        for caminho in caminhos_do_leitor(comando, args):
            if caminho_secreto(caminho):
                return caminho
    return None


def tag_mutante(cmd: str) -> bool:
    """Nega criação/alteração/exclusão de tag; permite apenas listagem explícita."""
    for segmento in segmentos_shell(cmd):
        try:
            indice = segmento.index("git")
        except ValueError:
            continue
        resto = segmento[indice + 1 :]
        if not resto or resto[0] != "tag":
            continue
        args = resto[1:]
        if not args:
            return False
        opcoes_leitura = {
            "--list",
            "-l",
            "--contains",
            "--points-at",
            "--merged",
            "--no-merged",
            "--sort",
            "--format",
            "--column",
        }
        if any(
            arg in {"-d", "--delete", "-f", "--force", "-a", "--annotate", "-s", "-u"}
            for arg in args
        ):
            return True
        if args[0] not in opcoes_leitura and not any(
            args[0].startswith(f"{opcao}=")
            for opcao in opcoes_leitura
            if opcao.startswith("--")
        ):
            return True
    return False


def npm_ci_com_scripts(cmd: str) -> bool:
    for segmento in segmentos_shell(cmd):
        for indice in range(len(segmento) - 1):
            if segmento[indice : indice + 2] == ["npm", "ci"]:
                return "--ignore-scripts" not in segmento[indice + 2 :]
    return False


def compose_externo(cmd: str) -> str | None:
    """Bloqueia `-f` absoluto ou com `..`; Compose padrão do repositório é permitido."""
    for segmento in segmentos_shell(cmd):
        if "docker" not in segmento or "compose" not in segmento:
            continue
        for indice, token in enumerate(segmento):
            if token in {"-f", "--file"} and indice + 1 < len(segmento):
                caminho = normaliza_caminho(segmento[indice + 1])
                if caminho.startswith(("/", "~")) or ".." in PurePosixPath(caminho).parts:
                    return segmento[indice + 1]
            if token.startswith("--file="):
                caminho = normaliza_caminho(token.split("=", 1)[1])
                if caminho.startswith(("/", "~")) or ".." in PurePosixPath(caminho).parts:
                    return caminho
    return None


def alvos_rm(cmd: str) -> list[str]:
    """Caminhos passados a `rm`, já sem aspas e sem flags."""
    try:
        tokens = shlex.split(cmd)
    except ValueError:
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
        resultado = subprocess.run(
            ["git", "symbolic-ref", "--short", "-q", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return resultado.stdout.strip()
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

    segredo = leitura_segredo(bruto)
    if segredo:
        nega(
            f"Leitura de arquivo sensível via Bash é proibida ({DOC}): {segredo}. "
            "Use somente `.env.example` ou solicite tratamento humano controlado."
        )

    if tag_mutante(bruto):
        nega(
            "Criação, alteração ou exclusão de tag é proibida para agentes. "
            "Use somente `git tag --list`/`git show-ref --tags`."
        )

    if npm_ci_com_scripts(bruto):
        nega(
            "`npm ci` pode executar scripts de dependência. Use "
            "`npm ci --ignore-scripts` e execute somente scripts versionados e revisados."
        )

    compose = compose_externo(bruto)
    if compose:
        nega(
            f"Arquivo Compose externo ou fora do repositório é proibido: {compose}. "
            "Use o Compose versionado na branch de desenvolvimento."
        )

    for padrao, motivo in PADROES:
        if re.search(padrao, cmd, re.IGNORECASE):
            nega(motivo)

    if RM_RECURSIVO.search(cmd):
        fora = [alvo for alvo in alvos_rm(bruto) if not temporario(alvo)]
        if fora:
            variavel = [alvo for alvo in fora if "$" in alvo]
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
