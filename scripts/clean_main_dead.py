"""Remove de main.py os imports e include_router dos routers movidos a
_dead_code (órfãos comprovados, consolidação 12/08/2026)."""
from __future__ import annotations
import sys

MAIN = "/home/ubuntu/ejc/backend/app/main.py"
NOMES = [
    "data_room_v4",
    "diplomacia_v3",
    "peca_geracao_router",
    "teses_v4",
    "veredito_ia_router",
    "victory_vault_router",
]


def main() -> int:
    with open(MAIN, encoding="utf-8") as fh:
        linhas = fh.read().splitlines()
    antes = len(linhas)
    novas = [
        l for l in linhas
        if not any(
            (l.startswith(f"from app.routers import {n}") or
             l.startswith(f"app.include_router({n}."))
            for n in NOMES
        )
    ]
    with open(MAIN, "w", encoding="utf-8") as fh:
        fh.write("\n".join(novas) + "\n")
    print(f"Removidas {antes - len(novas)} linhas de main.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
