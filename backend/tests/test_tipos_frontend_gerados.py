"""S1 — tipos TS gerados do backend não podem envelhecer.

Regenera `frontend/src/types/gerado.ts` em memória (scripts/gerar_tipos_frontend.py)
e compara com o arquivo commitado. Falhou? Rode `npm run types:gerar` no
frontend (ou o script no backend) e commite o resultado.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "backend" / "scripts" / "gerar_tipos_frontend.py"
GERADO = RAIZ / "frontend" / "src" / "types" / "gerado.ts"


def _carregar_script():
    spec = importlib.util.spec_from_file_location("gerar_tipos_frontend", SCRIPT)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def gerador():
    return _carregar_script()


def test_arquivo_gerado_esta_em_dia(gerador):
    assert GERADO.exists(), f"{GERADO} não existe — rode scripts/gerar_tipos_frontend.py"
    esperado = gerador.gerar()
    atual = GERADO.read_text(encoding="utf-8")
    assert atual == esperado, (
        "frontend/src/types/gerado.ts diverge do backend — regenere com "
        "`npm run types:gerar` (frontend) e commite."
    )


def test_cabecalho_marca_arquivo_gerado(gerador):
    assert gerador.gerar().startswith("// ARQUIVO GERADO — não edite.")


def test_todas_as_areas_tem_rotulo(gerador):
    from app.core.taxonomia import AREAS_CANONICAS

    assert set(gerador.ROTULOS_AREA) == set(AREAS_CANONICAS)
    assert set(gerador.AREAS_DESTAQUE) <= set(AREAS_CANONICAS)


def test_origem_de_prazo_cobre_valores_gravados(gerador):
    # D5: `entrada_unica` (entrada_service) e `importacao_ia` (importação de
    # documento) existem no banco — o contrato TS precisa declará-los.
    assert {"manual", "datajud", "importacao_ia", "entrada_unica"} == set(
        gerador.DEADLINE_ORIGENS
    )


def test_enums_canonicos_aparecem_no_ts(gerador):
    from app.models.case import CaseStatus
    from app.models.legal_doc import PecaStatus
    from app.models.user import UserRole

    conteudo = gerador.gerar()
    for nome in ("CaseArea", "CaseStatus", "DeadlineOrigem", "UserRole", "PecaStatus"):
        assert f"export type {nome} =" in conteudo
    for valor in (*[s.value for s in CaseStatus], *[r.value for r in UserRole], *[p.value for p in PecaStatus]):
        assert f'"{valor}",' in conteudo
