"""Separa o teste test_data_room_ownership_pente_fino.py (12/08/2026):

Os 7 primeiros testes exercem o contrato CANÔNICO (data_room.py) e continuam
no lugar. Os 3 últimos (test_v4_*) exercem o router legado data_room_v4
(deprecação, header, sala avulsa) — migrados para
tests/_dead_code/test_data_room_v4_legado.py, apontando para o código
arquivado em app/routers/_dead_code/data_room_v4.py.
"""
from __future__ import annotations
import re
import sys

BASE = "/home/ubuntu/ejc/backend"
SRC = f"{BASE}/tests/test_data_room_ownership_pente_fino.py"
DST_LEGACY = f"{BASE}/tests/_dead_code/test_data_room_v4_legado.py"

with open(SRC, encoding="utf-8") as fh:
    conteudo = fh.read()

partes = conteudo.split(
    "@pytest.mark.asyncio\nasync def test_v4_listagem_advogado_filtra_clientes_visiveis",
)
if len(partes) != 2:
    print("ERRO: split inesperado", len(partes), file=sys.stderr)
    sys.exit(2)

canonico, legado = partes

# ── Arquivo canônico: remover import de data_room_v4 ──
canonico = re.sub(
    r"from app\.routers\.data_room_v4 import \(\n(?:.|\n)*?\)\n",
    "",
    canonico,
)
with open(SRC, "w", encoding="utf-8") as fh:
    fh.write(canonico)

# ── Arquivo legado: recriar com os imports mortos restaurados ──
header = '''"""Contratos do router LEGADO data_room_v4 (movido a _dead_code em
12/08/2026 — docs/consolidacao/MAPA_VERDADE_V1.md). Estes testes protegem o
comportamento de depreciação do contrato antigo (header deprecation,
rejeição de sala avulsa para não-gestores, validação de carteira) contra o
código arquivado — não contra main.py. NÃO reativar sem decisão escrita.
"""
'''
legado = header + legado
with open(DST_LEGACY, "w", encoding="utf-8") as fh:
    fh.write(legado)

print("Split concluído. Legacy:", DST_LEGACY)
