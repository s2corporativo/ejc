from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routers.notifications import _criticidade, listar


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _FakeDB:
    def __init__(self, rows, total, nao_lidas):
        self._results = [
            _RowsResult(rows),
            _ScalarResult(total),
            _ScalarResult(nao_lidas),
        ]
        self.queries = []

    async def execute(self, query):
        self.queries.append(query)
        return self._results.pop(0)


def _notification(tipo="prazo", idx=1):
    return SimpleNamespace(
        id=f"n{idx}",
        titulo="Aviso",
        mensagem="Mensagem operacional",
        tipo=tipo,
        link="/prazos",
        lida=False,
        created_at=datetime(2026, 8, 9, 12, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    ("tipo", "esperado"),
    [
        ("prazo", "critica"),
        ("intimacao", "critica"),
        ("audiencia", "critica"),
        ("auditoria", "critica"),
        ("financeiro", "atencao"),
        ("assinatura", "atencao"),
        ("sistema", "atencao"),
        ("ia", "informativa"),
        ("tipo_novo", "informativa"),
        (None, "informativa"),
    ],
)
def test_criticidade_e_deterministica_pelo_tipo(tipo, esperado):
    assert _criticidade(tipo) == esperado


@pytest.mark.asyncio
async def test_contrato_legado_data_e_nao_lidas_permanece_compativel():
    db = _FakeDB([_notification()], total=141, nao_lidas=141)
    cu = SimpleNamespace(id="u1")

    out = await listar(
        apenas_nao_lidas=False,
        limit=15,
        page=None,
        page_size=None,
        ordenar_criticidade=False,
        db=db,
        cu=cu,
    )

    assert out["data"][0]["id"] == "n1"
    assert out["data"][0]["criticidade"] == "critica"
    assert out["nao_lidas"] == 141
    assert out["total"] == 141
    assert out["page"] == 1
    assert out["page_size"] == 15
    assert out["paginado"] is False
    assert "OFFSET" not in str(db.queries[0]).upper()

    params = db.queries[0].compile().params
    assert "u1" in params.values()


@pytest.mark.asyncio
async def test_pagina_dois_aplica_offset_sem_truncar_unread_count():
    db = _FakeDB([_notification("financeiro", 2)], total=141, nao_lidas=137)
    cu = SimpleNamespace(id="u1")

    out = await listar(
        apenas_nao_lidas=False,
        limit=30,
        page=2,
        page_size=50,
        ordenar_criticidade=True,
        db=db,
        cu=cu,
    )

    assert out["page"] == 2
    assert out["page_size"] == 50
    assert out["paginado"] is True
    assert out["total"] == 141
    assert out["nao_lidas"] == 137
    assert out["data"][0]["criticidade"] == "atencao"
    consulta = str(db.queries[0]).upper()
    assert "OFFSET" in consulta
    assert "CASE" in consulta


@pytest.mark.asyncio
async def test_filtro_nao_lidas_tambem_restringe_total_da_listagem():
    db = _FakeDB([_notification()], total=12, nao_lidas=12)
    cu = SimpleNamespace(id="u1")

    out = await listar(
        apenas_nao_lidas=True,
        limit=30,
        page=1,
        page_size=30,
        ordenar_criticidade=False,
        db=db,
        cu=cu,
    )

    assert out["total"] == 12
    assert out["nao_lidas"] == 12
    assert "notifications.lida" in str(db.queries[1])
