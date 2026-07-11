"""Etapa 13 — andamentos oficiais via API Pública do DataJud (sem rede).

Cobre: parsing/normalização da resposta Elasticsearch do DataJud (fixture com
a estrutura documentada na wiki oficial), derivação do alias do tribunal a
partir do segmento J.TR do número CNJ, idempotência do upsert em
case_movimentos (fakes, padrão test_sociedades_cliente) e os gates do
endpoint (503 flag desligada, 422 caso sem número CNJ).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.models.case import Case, CaseMovimento
from app.models.user import User, UserRole
from app.services import datajud_service
from app.services.datajud_service import (
    DataJudDesabilitadoError,
    TribunalNaoMapeadoError,
    alias_do_numero,
    consultar_movimentos,
    upsert_movimentos_no_caso,
)

# ── Fixture: resposta real documentada da API Pública do DataJud ──────────────
# Estrutura conforme wiki/tutorial oficial do CNJ (datajud-wiki.cnj.jus.br):
# hits.hits[]._source com numeroProcesso, tribunal, classe{codigo,nome} e
# movimentos[]{codigo, nome, dataHora}. Movimentos propositalmente FORA de
# ordem cronológica para exercitar a ordenação.
RESPOSTA_DATAJUD = {
    "took": 5,
    "timed_out": False,
    "hits": {
        "total": {"value": 1, "relation": "eq"},
        "max_score": 2.0,
        "hits": [
            {
                "_index": "api_publica_tjmg",
                "_source": {
                    "numeroProcesso": "00000010220208130000",
                    "tribunal": "TJMG",
                    "grau": "G1",
                    "classe": {"codigo": 1116, "nome": "Execução Fiscal"},
                    "orgaoJulgador": {"nome": "1ª Vara Cível"},
                    "dataHoraUltimaAtualizacao": "2022-09-06T12:03:20.257Z",
                    "movimentos": [
                        {
                            "codigo": 11382,
                            "nome": "Bloqueio/penhora on line",
                            "dataHora": "2022-07-13T07:25:59.000Z",
                        },
                        {
                            "codigo": 26,
                            "nome": "Distribuição",
                            "dataHora": "2020-03-01T10:00:00.000Z",
                        },
                        {"codigo": 999, "nome": "", "dataHora": "2022-08-01"},
                    ],
                },
            }
        ],
    },
}

NUMERO_TJMG = "0000001-02.2020.8.13.0000"


@pytest.fixture()
def datajud_ligado(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "DATAJUD_ENABLED", True)
    monkeypatch.setattr(s, "DATAJUD_API_KEY", "chave-publica-cnj-teste")
    return s


# ── Fakes (sem banco) — padrão test_sociedades_cliente ────────────────────────

class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val

    def scalars(self):
        return self

    def all(self):
        return self._val


class _FakeDB:
    def __init__(self, resultados: list):
        self._resultados = list(resultados)
        self.added: list = []
        self.commits = 0

    async def execute(self, *a, **k):
        return _Res(self._resultados.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _caso(numero: str | None) -> Case:
    return Case(id="caso1", titulo="Caso DJ", client_id="cli1",
                numero_processo=numero, deleted_at=None,
                advogado_responsavel_id="u1", advogado_auxiliar_id=None)


def _socio() -> User:
    return User(id="u1", role=UserRole.socio)


# ── Rotas montadas ─────────────────────────────────────────────────────────────

def test_rotas_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/casos/{case_id}/andamentos/sincronizar") for p in paths)
    assert any(p.endswith("/casos/{case_id}/andamentos/status") for p in paths)


# ── Derivação do alias pelo número CNJ (J.TR) ─────────────────────────────────

def test_alias_do_numero_principais_tribunais():
    assert alias_do_numero("0000001-02.2020.8.13.0000") == "api_publica_tjmg"
    assert alias_do_numero("0000001-02.2020.8.26.0100") == "api_publica_tjsp"
    assert alias_do_numero("0000001-02.2020.8.19.0001") == "api_publica_tjrj"
    assert alias_do_numero("0000001-02.2020.4.01.3800") == "api_publica_trf1"
    assert alias_do_numero("0000001-02.2020.4.04.7000") == "api_publica_trf4"
    assert alias_do_numero("0000001-02.2020.4.06.3800") == "api_publica_trf6"
    assert alias_do_numero("0000001-02.2020.5.00.0000") == "api_publica_tst"
    assert alias_do_numero("0000001-02.2020.5.03.0001") == "api_publica_trt3"
    assert alias_do_numero("0000001-02.2020.3.00.0000") == "api_publica_stj"


def test_alias_do_numero_fallback_claro():
    # Só dígitos (sem máscara) também resolve.
    assert alias_do_numero("00000010220208130000") == "api_publica_tjmg"
    # Tribunal fora do mapa (TJDFT = 8.07) → None, nunca chute.
    assert alias_do_numero("0722391-40.2017.8.07.0001") is None
    # Número inválido/curto → None.
    assert alias_do_numero("123") is None
    assert alias_do_numero("") is None


# ── Parsing/normalização da resposta ──────────────────────────────────────────

async def test_consultar_movimentos_normaliza_e_ordena(datajud_ligado, monkeypatch):
    chamadas = {}

    async def _fake_search(alias, payload, headers):
        chamadas["alias"] = alias
        chamadas["payload"] = payload
        chamadas["headers"] = headers
        return RESPOSTA_DATAJUD

    monkeypatch.setattr(datajud_service, "_datajud_search", _fake_search)

    movs = await consultar_movimentos(NUMERO_TJMG)

    # Endpoint do tribunal derivado do número; consulta sem máscara.
    assert chamadas["alias"] == "api_publica_tjmg"
    assert chamadas["payload"]["query"]["match"]["numeroProcesso"] == "00000010220208130000"
    assert chamadas["headers"]["Authorization"].startswith("APIKey ")

    # Movimento sem nome é descartado; restam 2, ordenados do mais antigo.
    assert [m["codigo"] for m in movs] == [26, 11382]
    assert movs[0] == {
        "data": "2020-03-01T10:00:00.000Z",
        "codigo": 26,
        "descricao": "Distribuição",
    }


async def test_consultar_movimentos_processo_nao_localizado(datajud_ligado, monkeypatch):
    async def _fake_search(alias, payload, headers):
        return {"hits": {"total": {"value": 0}, "hits": []}}

    monkeypatch.setattr(datajud_service, "_datajud_search", _fake_search)
    assert await consultar_movimentos(NUMERO_TJMG) == []


async def test_consultar_movimentos_gate_flag_desligada(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "DATAJUD_ENABLED", False)
    with pytest.raises(DataJudDesabilitadoError):
        await consultar_movimentos(NUMERO_TJMG)


async def test_consultar_movimentos_tribunal_nao_mapeado(datajud_ligado):
    with pytest.raises(TribunalNaoMapeadoError):
        await consultar_movimentos("0722391-40.2017.8.07.0001")  # TJDFT fora do mapa


# ── Upsert idempotente em case_movimentos ─────────────────────────────────────

MOVS_NORMALIZADOS = [
    {"data": "2020-03-01T10:00:00.000Z", "codigo": 26, "descricao": "Distribuição"},
    {"data": "2022-07-13T07:25:59.000Z", "codigo": 11382,
     "descricao": "Bloqueio/penhora on line"},
]


async def test_upsert_movimentos_idempotente():
    case = _caso(NUMERO_TJMG)

    # 1ª sincronização: caso sem movimentos → insere os 2.
    db1 = _FakeDB([[]])
    novos, total = await upsert_movimentos_no_caso(db1, case, MOVS_NORMALIZADOS)
    assert (novos, total) == (2, 2)
    assert all(isinstance(m, CaseMovimento) for m in db1.added)
    assert all(m.tipo == "andamento_oficial" for m in db1.added)
    assert all("[dj:" in m.descricao for m in db1.added)

    # 2ª sincronização: mesmos movimentos já importados → 0 novos.
    descricoes_existentes = [m.descricao for m in db1.added]
    db2 = _FakeDB([descricoes_existentes])
    novos2, total2 = await upsert_movimentos_no_caso(db2, case, MOVS_NORMALIZADOS)
    assert (novos2, total2) == (0, 2)
    assert db2.added == []


async def test_upsert_dedup_dentro_do_mesmo_lote():
    case = _caso(NUMERO_TJMG)
    duplicado = [MOVS_NORMALIZADOS[0], dict(MOVS_NORMALIZADOS[0])]
    db = _FakeDB([[]])
    novos, total = await upsert_movimentos_no_caso(db, case, duplicado)
    assert (novos, total) == (1, 2)


# ── Endpoint: gates de flag e de número CNJ ───────────────────────────────────

async def test_endpoint_503_com_flag_desligada(monkeypatch):
    from app.routers.andamentos import sincronizar_andamentos

    s = get_settings()
    monkeypatch.setattr(s, "DATAJUD_ENABLED", False)
    with pytest.raises(HTTPException) as exc:
        await sincronizar_andamentos("caso1", db=_FakeDB([]), cu=_socio())
    assert exc.value.status_code == 503
    assert "DATAJUD_ENABLED" in exc.value.detail


async def test_endpoint_503_sem_chave(monkeypatch):
    from app.routers.andamentos import sincronizar_andamentos

    s = get_settings()
    monkeypatch.setattr(s, "DATAJUD_ENABLED", True)
    monkeypatch.setattr(s, "DATAJUD_API_KEY", "")
    with pytest.raises(HTTPException) as exc:
        await sincronizar_andamentos("caso1", db=_FakeDB([]), cu=_socio())
    assert exc.value.status_code == 503


async def test_endpoint_422_caso_sem_numero_cnj(datajud_ligado):
    from app.routers.andamentos import sincronizar_andamentos

    db = _FakeDB([_caso(None)])  # verificar_acesso_caso carrega o caso
    with pytest.raises(HTTPException) as exc:
        await sincronizar_andamentos("caso1", db=db, cu=_socio())
    assert exc.value.status_code == 422


async def test_endpoint_sincroniza_e_audita(datajud_ligado, monkeypatch):
    from app.routers import andamentos as router_mod

    async def _fake_consulta(numero, tribunal_alias=None):
        return MOVS_NORMALIZADOS

    monkeypatch.setattr(
        router_mod.datajud_service, "consultar_movimentos", _fake_consulta
    )

    # execute(): 1º carrega o caso (ownership), 2º lista descricoes (upsert).
    db = _FakeDB([_caso(NUMERO_TJMG), []])
    resp = await router_mod.sincronizar_andamentos("caso1", db=db, cu=_socio())

    assert resp == {"novos": 2, "total": 2}
    assert db.commits == 1
    movimentos = [m for m in db.added if isinstance(m, CaseMovimento)]
    assert len(movimentos) == 2
    # Audit log gravado na mesma transação, sem segredos.
    audits = [a for a in db.added if a.__class__.__name__ == "AuditLog"]
    assert len(audits) == 1 and audits[0].acao == "SYNC"


async def test_endpoint_status_sem_segredos(datajud_ligado):
    from app.routers.andamentos import status_andamentos

    db = _FakeDB([_caso(NUMERO_TJMG)])
    resp = await status_andamentos("caso1", db=db, cu=_socio())
    assert resp == {
        "enabled": True,
        "configured": True,
        "numero_processo": NUMERO_TJMG,
        "tribunal_alias": "api_publica_tjmg",
    }
    # Nunca vazar a chave no payload de status.
    assert "chave" not in str(resp).lower()
    assert get_settings().DATAJUD_API_KEY not in str(resp)
