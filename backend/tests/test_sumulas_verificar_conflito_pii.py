"""Regressão C1 (auditoria Clientes): /sumulas/verificar-conflito vazava
CPF/CNPJ em claro a qualquer usuário autenticado."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

CPF = "39053344705"


class _DB:
    def __init__(self):
        self.sqls = []

    async def execute(self, stmt, params=None):
        self.sqls.append((str(stmt), params))

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _cli():
    return SimpleNamespace(nome="Fulano de Tal", razao_social=None, documento_plain=CPF)


@pytest.fixture
def _patch(monkeypatch):
    import app.services.conflito_service as cs

    async def por_doc(db, docs):
        return [_cli()]

    async def por_nome(db, nome):
        return [_cli()]

    async def casos(*a, **k):
        return []

    monkeypatch.setattr(cs, "_clientes_por_documentos", por_doc)
    monkeypatch.setattr(cs, "_clientes_por_nome", por_nome)
    monkeypatch.setattr(cs, "_casos_por_parte_contraria", casos)


@pytest.mark.asyncio
@pytest.mark.parametrize("kw", [{"parte_contraria_doc": CPF}, {"parte_contraria_nome": "Fulano de Tal"}])
async def test_match_nao_devolve_documento_em_claro(_patch, kw):
    from app.services.conflito_interesses import verificar_conflito

    db = _DB()
    res = await verificar_conflito(db, **kw)
    assert res["matches"]
    for m in res["matches"]:
        assert m["documento"] != CPF
        assert m["documento"] == "***.533.447-**"
    # a trilha WORM também não pode reter nome/documento da parte
    for _, params in db.sqls:
        assert CPF not in str(params)
        assert "Fulano" not in str(params)


@pytest.mark.asyncio
@pytest.mark.parametrize("role,ok", [("estagiario", False), ("financeiro", False),
                                      ("advogado_auxiliar", False), ("advogado", True)])
async def test_rota_exige_perfil_de_clientes(_patch, role, ok):
    from app.routers.sumulas import ConflitoRequest, verificar_conflito

    cu = SimpleNamespace(id="u1", role=SimpleNamespace(value=role))
    req = ConflitoRequest(parte_contraria_doc=CPF)
    if ok:
        res = await verificar_conflito(req, _DB(), cu)
        assert res["matches"][0]["documento"] != CPF
    else:
        with pytest.raises(HTTPException) as e:
            await verificar_conflito(req, _DB(), cu)
        assert e.value.status_code == 403


def test_mascara_cnpj_e_valores_invalidos():
    from app.services.pii_crypto import mascarar_documento

    assert mascarar_documento("11222333000181") == "**.222.333/****-**"
    assert mascarar_documento(None) is None
    assert mascarar_documento("123") is None
