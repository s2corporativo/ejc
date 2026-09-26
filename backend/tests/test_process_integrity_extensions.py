from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.schemas.process import ProcessCreate
from app.services.saneamento import aplicacao


class _Result:
    def __init__(self, *, rows=None, one=None):
        self._rows = rows
        self._one = one

    def scalars(self):
        return self

    def all(self):
        return list(self._rows or [])

    def scalar_one_or_none(self):
        return self._one


class _FakeDB:
    def __init__(self, *results):
        self._results = list(results)
        self.add = MagicMock()

    async def execute(self, _stmt):
        return self._results.pop(0)




def test_process_schema_aceita_data_ajuizamento():
    payload = ProcessCreate(
        numero_cnj=None,
        data_ajuizamento=date(2026, 9, 25),
    )
    assert payload.data_ajuizamento == date(2026, 9, 25)


def test_rotulo_datajud_rejeita_codigo_numerico_sem_descricao():
    assert aplicacao.rotulo_datajud("12345") is None
    assert aplicacao.rotulo_datajud({"codigo": 12345}) is None
    assert aplicacao.rotulo_datajud({"codigo": 12345, "nome": "Vara Cível"}) == "Vara Cível"


@pytest.mark.anyio
async def test_aplicacao_assistida_data_ajuizamento(monkeypatch):
    processo = SimpleNamespace(
        id="proc-1",
        case_id="case-1",
        is_principal=True,
        data_ajuizamento=None,
    )
    snapshot = SimpleNamespace(
        numero_cnj="10182841320268130027",
        data_ajuizamento=date(2026, 8, 14),
        nivel_sigilo=0,
        payload={"dataAjuizamento": "2026-08-14"},
        coletado_em=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )
    divergencia = SimpleNamespace(
        id=7,
        numero_cnj="10182841320268130027",
        tipo="data_ajuizamento_divergente",
        tratada=False,
        tratada_por=None,
        tratada_em=None,
    )
    db = _FakeDB(
        _Result(rows=[processo]),
        _Result(one=snapshot),
    )
    atualizar = AsyncMock(return_value={"id": "proc-1"})
    proveniencia = AsyncMock()
    monkeypatch.setattr(aplicacao, "atualizar_processo", atualizar)
    monkeypatch.setattr(aplicacao, "registrar_proveniencia", proveniencia)

    resultado = await aplicacao.aplicar_divergencia(
        db,
        divergencia=divergencia,
        user_id="adv-1",
    )

    assert resultado["process_id"] == "proc-1"
    assert resultado["campos"] == {"data_ajuizamento": date(2026, 8, 14)}
    assert divergencia.tratada is True
    assert divergencia.tratada_por == "adv-1"
    atualizar.assert_awaited_once()
    proveniencia.assert_awaited_once()
    db.add.assert_called_once()


@pytest.mark.anyio
async def test_aplicacao_assistida_recusa_processo_sigiloso(monkeypatch):
    processo = SimpleNamespace(
        id="proc-1",
        case_id="case-1",
        is_principal=True,
        classe="Antiga",
    )
    snapshot = SimpleNamespace(
        numero_cnj="10182841320268130027",
        data_ajuizamento=None,
        nivel_sigilo=1,
        payload={"classe": {"nome": "Nova"}},
        coletado_em=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )
    divergencia = SimpleNamespace(
        id=8,
        numero_cnj="10182841320268130027",
        tipo="classe_divergente",
        tratada=False,
        tratada_por=None,
        tratada_em=None,
    )
    db = _FakeDB(
        _Result(rows=[processo]),
        _Result(one=snapshot),
    )
    monkeypatch.setattr(aplicacao, "atualizar_processo", AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await aplicacao.aplicar_divergencia(
            db,
            divergencia=divergencia,
            user_id="adv-1",
        )

    assert exc.value.status_code == 422
