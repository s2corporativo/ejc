#!/usr/bin/env python
"""Ledger de rotas — regenera/confere o snapshot OpenAPI (S6, análise E2E 03/09).

    python scripts/ledger_rotas.py --verificar   # imprime o diff; sai 1 se divergir
    python scripts/ledger_rotas.py --atualizar   # regrava tests/snapshots/openapi_rotas_baseline.json

O teste `tests/test_rotas_registro_explicito.py` continua reprovando toda
mudança NÃO declarada (rota nova/removida ou auth alterada): a declaração é
feita nas listas ADICOES_INTENCIONAIS / REMOCOES_INTENCIONAIS /
AUTH_ALTERACOES_INTENCIONAIS daquele arquivo. Este script existe para que o
diff seja visto e revisado no PR em vez de descoberto por um assert quebrado.
"""
from __future__ import annotations

import json
import os
import sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, RAIZ)
os.environ.setdefault("APP_ENV", "development")

SNAPSHOT = os.path.join(RAIZ, "tests", "snapshots", "openapi_rotas_baseline.json")


def _atual() -> list[dict]:
    from app.main import app
    from tests.test_rotas_registro_explicito import _extrair_rotas

    return _extrair_rotas(app)


def _chave(r: dict) -> tuple[str, str]:
    return (r["path"], r["method"])


def diff(base: list[dict], atual: list[dict]) -> dict:
    b = {_chave(r): r for r in base}
    a = {_chave(r): r for r in atual}
    return {
        "adicionadas": sorted(k for k in a if k not in b),
        "removidas": sorted(k for k in b if k not in a),
        "auth_alterada": sorted(
            (k, b[k]["auth_deps"], a[k]["auth_deps"])
            for k in a
            if k in b and b[k]["auth_deps"] != a[k]["auth_deps"]
        ),
    }


def _descontar_declaradas(d: dict) -> dict:
    """Remove do diff o que já está declarado nas listas do teste (adições e
    remoções intencionais). As alterações de auth ficam sempre visíveis: a
    lista correspondente vive dentro do teste e cada uma exige decisão escrita."""
    try:
        from tests import test_rotas_registro_explicito as t
    except Exception:  # pragma: no cover
        return d
    decl_add = {(p, m) for p, m in getattr(t, "ADICOES_INTENCIONAIS", set())}
    decl_rem = {(p, m) for p, m in getattr(t, "REMOCOES_INTENCIONAIS", set())}
    # AUTH_ALTERACOES_INTENCIONAIS vive dentro do teste: lê-se do fonte.
    import ast
    import re

    decl_auth: set[tuple[str, str, tuple[str, ...]]] = set()
    with open(t.__file__, encoding="utf-8") as fh:
        fonte = fh.read()
    for path, metodo, deps in re.findall(
        r'\(\("(/api/[^"]+)",\s*"([A-Z]+)"\),\s*(\[[^\]]*\])\)', fonte
    ):
        decl_auth.add((path, metodo, tuple(ast.literal_eval(deps))))
    return {
        "adicionadas": [k for k in d["adicionadas"] if k not in decl_add],
        "removidas": [k for k in d["removidas"] if k not in decl_rem],
        "auth_alterada": [
            item for item in d["auth_alterada"]
            if (item[0][0], item[0][1], tuple(item[2])) not in decl_auth
        ],
    }


def _imprimir(d: dict) -> None:
    for titulo, itens in (("ROTAS ADICIONADAS", d["adicionadas"]), ("ROTAS REMOVIDAS", d["removidas"])):
        print(f"\n== {titulo} ({len(itens)})")
        for path, metodo in itens:
            print(f"  {metodo:6} {path}")
    print(f"\n== AUTH ALTERADA ({len(d['auth_alterada'])})")
    for (path, metodo), antes, depois in d["auth_alterada"]:
        print(f"  {metodo:6} {path}\n      antes:  {antes}\n      depois: {depois}")
    total = len(d["adicionadas"]) + len(d["removidas"]) + len(d["auth_alterada"])
    if total:
        print(
            "\nDeclare cada item em tests/test_rotas_registro_explicito.py "
            "(ADICOES_INTENCIONAIS / REMOCOES_INTENCIONAIS / AUTH_ALTERACOES_INTENCIONAIS) "
            "com o motivo, e cite o diff no PR."
        )
    else:
        print("\nSem divergência entre o app e o snapshot.")


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("--verificar", "--atualizar"):
        print(__doc__)
        return 2
    with open(SNAPSHOT, encoding="utf-8") as fh:
        base = json.load(fh)
    atual = sorted(_atual(), key=lambda r: (r["path"], r["method"]))
    if argv[1] == "--atualizar":
        d = diff(base, atual)
        _imprimir(d)
        with open(SNAPSHOT, "w", encoding="utf-8") as fh:
            json.dump(atual, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(
            f"\nSnapshot regravado: {os.path.relpath(SNAPSHOT, RAIZ)} ({len(atual)} rotas).\n"
            "ATENÇÃO: o snapshot novo já contém tudo que estava declarado — esvazie "
            "ADICOES_INTENCIONAIS / REMOCOES_INTENCIONAIS / AUTH_ALTERACOES_INTENCIONAIS "
            "em tests/test_rotas_registro_explicito.py na mesma PR (rebase do ledger)."
        )
        return 0
    d = _descontar_declaradas(diff(base, atual))
    _imprimir(d)
    return 1 if (d["adicionadas"] or d["removidas"] or d["auth_alterada"]) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
