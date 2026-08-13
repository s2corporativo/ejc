"""Consolidação 12/08/2026 — move routers backend comprovadamente órfãos
(sem consumidor em código prod frontend/backend) para app/routers/_dead_code/.

Órfãos: teses_v4, data_room_v4, diplomacia_v3, veredito_ia_router,
victory_vault_router, peca_geracao_router.

Não movido: intelligence_v3.py — RadarLegislativo.tsx CONSUME
GET /intelligence-v3/radar/legislativo (renomeio de prefixo tratado à parte).
"""
from __future__ import annotations
import os
import shutil
import sys

BASE = "/home/ubuntu/ejc/backend"
ORFAOS = [
    "teses_v4.py",
    "data_room_v4.py",
    "diplomacia_v3.py",
    "veredito_ia_router.py",
    "victory_vault_router.py",
    "peca_geracao_router.py",
]

SRC_DIR = f"{BASE}/app/routers"
DST_DIR = f"{SRC_DIR}/_dead_code"


def main() -> int:
    os.makedirs(DST_DIR, exist_ok=True)
    # README do diretório
    readme = f"{DST_DIR}/README.md"
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as fh:
            fh.write(
                "# Routers desativados (consolidação 12/08/2026)\n\n"
                "Código movido aqui após comprovação de ausência de consumidores\n"
                "em frontend e backend (auditoria de chamadas de API). NÃO\n"
                "importar em main.py. Servem apenas como referência histórica.\n"
                "Decisões registradas em docs/consolidacao/MAPA_VERDADE_V1.md.\n"
            )
    movidos, erros = [], []
    for nome in ORFAOS:
        src = f"{SRC_DIR}/{nome}"
        if not os.path.exists(src):
            erros.append(f"{nome}: não encontrado")
            continue
        shutil.move(src, f"{DST_DIR}/{nome}")
        movidos.append(nome)
    print("Movidos:", movidos)
    if erros:
        print("Erros:", erros, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
