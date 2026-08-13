"""Consolidação 12/08/2026 — funde jurimetria_extra.py em jurimetria.py.

Mesma estratégia do merge ia_extra→ai: o prefixo /jurimetria é idêntico nos
dois arquivos; a divisão era puramente física. O corpo do extra passa a viver
no fim de jurimetria.py, com imports injetados como aliases nomeados (evitam
colisão com os nomes do módulo canônico).
"""
from __future__ import annotations
import re
import sys

ROUTERS = "/home/ubuntu/ejc/backend/app/routers"
SOURCE = f"{ROUTERS}/jurimetria_extra.py"
TARGET = f"{ROUTERS}/jurimetria.py"
MARKER = "# ══ CONSOLIDAÇÃO 12/08/2026: conteúdo migrado de jurimetria_extra.py ══"

# Imports do extra que NÃO existem em jurimetria.py (detectar por grep e
# completar manualmente se necessário — guardas abaixo).
EXTRA_IMPORTS = {
    "import json": "import json as _je_json",
    "from datetime import datetime": "from datetime import datetime as _je_datetime",
    "from pydantic import BaseModel": "from pydantic import BaseModel as _je_BaseModel",
    "from pydantic import Field": "from pydantic import Field as _je_Field",
    "BaseModel": "_je_BaseModel",
    "Field(": "_je_Field(",
}


def main() -> int:
    with open(SOURCE, encoding="utf-8") as fh:
        src = fh.read()
    with open(TARGET, encoding="utf-8") as fh:
        tgt = fh.read()

    if MARKER in tgt:
        print("JÁ CONSOLIDADO (guarda detectada).", file=sys.stderr)
        return 0
    if 'prefix="/jurimetria"' not in src:
        print("ERRO: jurimetria_extra não usa prefixo /jurimetria — abortando.", file=sys.stderr)
        return 2

    linhas = src.splitlines(True)
    ini = next((i for i, l in enumerate(linhas) if l.startswith("router = APIRouter(")), None)
    if ini is None:
        print("ERRO: router não localizado em jurimetria_extra.", file=sys.stderr)
        return 2
    fim = next(i for i in range(ini, len(linhas)) if linhas[i].strip() == ")")
    corpo = "".join(linhas[fim + 1:])
    corpo = re.sub(r"^settings = get_settings\(\)\n", "", corpo, flags=re.M)
    corpo = corpo.replace("router = APIRouter(prefix=\"/jurimetria\", tags=[\"Jurimetria\"])\n", "")

    # Identificar imports do extra não presentes no target (por linha de import)
    alvo_imports = {line.strip() for line in tgt.splitlines()
                    if line.strip().startswith(("from ", "import "))}
    injecoes = []
    for linha in src.splitlines():
        st = linha.strip()
        if st.startswith(("from ", "import ")) and st not in alvo_imports:
            injecoes.append(linha)

    bloco = (
        "\n" + MARKER + "\n"
        "# Origem: app/routers/jurimetria_extra.py. Prefixo /jurimetria idêntico\n"
        "# ao canônico — divisão puramente física. Rotas e regras preservadas.\n"
        "# Imports abaixo cobertos: " + ", ".join(st[:48] for st in injecoes[:12]) + "\n"
        + corpo + "\n"
    )

    with open(TARGET, "w", encoding="utf-8") as fh:
        fh.write(tgt.rstrip() + bloco)
    print(f"Consolidado: {len(corpo.splitlines())} linhas de jurimetria_extra.py → jurimetria.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
