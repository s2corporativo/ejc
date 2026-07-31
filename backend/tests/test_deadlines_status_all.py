import inspect

import pytest
from fastapi import HTTPException

from app.models.deadline import DeadlineStatus
from app.routers.deadlines import (
    _normalizar_status_filtro,
    exportar_csv,
    listar,
)


@pytest.mark.parametrize("valor", [None, "", " ", "all", "ALL", " All "])
def test_status_all_ou_vazio_remove_filtro(valor):
    assert _normalizar_status_filtro(valor) is None


@pytest.mark.parametrize("status", list(DeadlineStatus))
def test_status_conhecido_retorna_enum(status):
    assert _normalizar_status_filtro(status.value.upper()) is status


def test_status_desconhecido_falha_com_422_antes_do_banco():
    with pytest.raises(HTTPException) as exc:
        _normalizar_status_filtro("nao_existe")

    assert exc.value.status_code == 422
    assert "Status inválido" in exc.value.detail


def test_listagem_e_csv_compartilham_a_normalizacao():
    assert "_normalizar_status_filtro(status_f)" in inspect.getsource(listar)
    assert "_normalizar_status_filtro(status_f)" in inspect.getsource(exportar_csv)
