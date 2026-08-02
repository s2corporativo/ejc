#!/usr/bin/env python3
"""Lembrete de orientação por graphify (hook PreToolUse de Read/Glob/Grep).

Substitui os dois hooks inline que injetavam "MANDATORY: you MUST run graphify
before reading source files" em **toda** leitura — inclusive de `CLAUDE.md`, de
`AGENTS.md` e dos documentos de governança, e em todo comando de shell que
contivesse a substring `grep` (`git log | grep`, por exemplo).

Três mudanças de comportamento, todas deliberadas:

1. **Só arquivos de código.** Documento (.md/.txt/.rst) e o próprio
   `graphify-out/` não disparam nada: grafo de símbolos não indexa prosa.
2. **Uma vez por sessão.** O lembrete orienta; repetido a cada leitura vira
   ruído que compete com a instrução real da tarefa.
3. **Recomendação, não ordem.** `graphify` é um índice auxiliar e pode estar
   desatualizado — quando está, o aviso diz isso e manda conferir na fonte.
   Ferramenta de apoio não pode ter precedência sobre ler o código.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

EXT_CODIGO = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".go", ".rs",
    ".java", ".rb", ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".kt",
    ".swift", ".php", ".scala", ".lua",
}

RAIZ = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
GRAFO = RAIZ / "graphify-out" / "graph.json"


def desatualizado() -> bool:
    """Grafo mais antigo que o último commit."""
    try:
        ts = subprocess.run(
            ["git", "-C", str(RAIZ), "log", "-1", "--format=%ct"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return bool(ts) and GRAFO.stat().st_mtime < float(ts)
    except Exception:
        return False


def ja_avisou(sessao: str) -> bool:
    """Marca a sessão; devolve True se o aviso já saiu antes."""
    if not sessao:
        return False
    marca = Path(tempfile.gettempdir()) / f"ejc-graphify-{sessao}.marca"
    if marca.exists():
        return True
    try:
        marca.touch()
    except Exception:
        pass
    return False


def toca_codigo(dados: dict) -> bool:
    entrada = dados.get("tool_input") or {}
    valores = [
        str(entrada.get(k) or "")
        for k in ("file_path", "pattern", "path", "glob", "command")
    ]
    juntos = " ".join(valores).replace("\\", "/")
    if "graphify-out/" in juntos:
        return False
    return any(v and Path(v.split()[-1] if " " in v else v).suffix in EXT_CODIGO for v in valores)


def main() -> None:
    if not GRAFO.exists():
        return
    try:
        dados = json.load(sys.stdin)
    except Exception:
        return
    if not toca_codigo(dados):
        return
    if ja_avisou(str(dados.get("session_id") or "")):
        return

    aviso = (
        "Dica de orientação: existe um grafo do código em graphify-out/. "
        'Para localizar código, `graphify query "<pergunta>"`, '
        '`graphify explain "<conceito>"` ou `graphify path "<A>" "<B>"` '
        "costumam custar menos contexto que varrer arquivos. "
        "É índice auxiliar, não fonte da verdade: confirme no arquivo antes de editar ou concluir."
    )
    if desatualizado():
        aviso += (
            " ATENÇÃO: o grafo está mais antigo que o último commit — pode apontar "
            "para símbolos que já mudaram. Rode `graphify update .` ou prefira ler o código."
        )

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": aviso,
                }
            }
        )
    )


if __name__ == "__main__":
    main()
