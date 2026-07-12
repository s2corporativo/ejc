"""Sync de feriados nacionais via BrasilAPI (feriados_service).

Cobertura: merge ADITIVO com a tabela `feriados` (municipais/estaduais nunca
tocados; datas já existentes não duplicam), flag desligada, BrasilAPI fora.
Tudo sem rede e sem banco (fakes).
"""
from datetime import date

import pytest

from app.services import feriados_service as fs


class _FakeResult:
    def __init__(self, vals):
        self._vals = vals

    def scalars(self):
        return self

    def all(self):
        return self._vals


class _FakeDB:
    """Sessão mínima: SELECT devolve as datas já existentes; add() coleta."""

    def __init__(self, existentes):
        self.existentes = existentes
        self.added = []
        self.commits = 0

    async def execute(self, *a, **k):
        return _FakeResult(self.existentes)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


@pytest.fixture(autouse=True)
def _sem_reload_db(monkeypatch):
    """carregar_feriados_db não deve tocar banco nos testes."""
    async def _noop():
        return 0
    import app.services.deadline_calculator as dc
    monkeypatch.setattr(dc, "carregar_feriados_db", _noop)


def _mock_brasilapi(monkeypatch, payload_por_ano: dict):
    chamadas = []

    async def fake(ano):
        chamadas.append(ano)
        resp = payload_por_ano.get(ano, [])
        if isinstance(resp, Exception):
            raise resp
        return resp

    monkeypatch.setattr(fs, "_buscar_feriados_ano", fake)
    return chamadas


async def test_merge_aditivo_preserva_existentes(monkeypatch):
    _mock_brasilapi(monkeypatch, {2026: [
        {"date": "2026-01-01", "name": "Confraternização mundial", "type": "national"},
        {"date": "2026-02-17", "name": "Carnaval", "type": "national"},
        {"date": "2026-04-21", "name": "Tiradentes", "type": "national"},
    ]})
    db = _FakeDB(existentes=[date(2026, 1, 1)])   # 01/01 já cadastrado

    r = await fs.sincronizar_feriados_nacionais(anos=[2026], db=db)

    assert r["status"] == "ok"
    assert r["inseridos"] == 2 and r["existentes"] == 1
    assert db.commits == 1
    datas = sorted(f.data for f in db.added)
    assert datas == [date(2026, 2, 17), date(2026, 4, 21)]  # 01/01 NÃO reinserido
    assert all(f.tipo == "nacional" for f in db.added)
    carnaval = next(f for f in db.added if f.data == date(2026, 2, 17))
    assert carnaval.movel is True                  # móvel marcado
    tiradentes = next(f for f in db.added if f.data == date(2026, 4, 21))
    assert tiradentes.movel is False


async def test_anos_padrao_corrente_e_proximo(monkeypatch):
    ano = date.today().year
    chamadas = _mock_brasilapi(monkeypatch, {})
    db = _FakeDB(existentes=[])
    r = await fs.sincronizar_feriados_nacionais(db=db)
    assert chamadas == [ano, ano + 1]
    assert r["status"] == "sem_dados" and r["inseridos"] == 0


async def test_brasilapi_fora_fail_safe(monkeypatch):
    _mock_brasilapi(monkeypatch, {2026: RuntimeError("503")})
    db = _FakeDB(existentes=[])
    r = await fs.sincronizar_feriados_nacionais(anos=[2026], db=db)
    assert r["status"] == "sem_dados"
    assert db.added == [] and db.commits == 0      # nada gravado


async def test_flag_desligada_e_noop(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "FERIADOS_BRASILAPI_ENABLED", False)
    chamadas = _mock_brasilapi(monkeypatch, {})
    r = await fs.sincronizar_feriados_nacionais(anos=[2026], db=_FakeDB([]))
    assert r["status"] == "desabilitado"
    assert chamadas == []                          # nem consultou a API
