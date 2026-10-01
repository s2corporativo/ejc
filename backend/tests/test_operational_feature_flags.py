import pytest
from fastapi import HTTPException

from app.core.operational_flags import _require


def test_operational_flag_on_nao_bloqueia():
    _require(True, "FLAG", "Fluxo")


def test_operational_flag_off_falha_com_503():
    with pytest.raises(HTTPException) as exc:
        _require(False, "FLAG", "Fluxo")
    assert exc.value.status_code == 503
    assert "FLAG=false" in str(exc.value.detail)


def test_main_aplica_kill_switch_financeiro_a_todas_as_superficies_canônicas():
    from pathlib import Path
    src=(Path(__file__).resolve().parents[1]/"app/main.py").read_text()
    for router in (
        "centro_custos", "despesas", "despesas_processuais", "extratos", "fees",
        "financeiro_consolidado", "gestao_societaria", "partner_withdrawals", "pix",
    ):
        linha=f"app.include_router({router}.router, prefix=API, dependencies=[Depends(require_financeiro_enabled)])"
        assert linha in src
