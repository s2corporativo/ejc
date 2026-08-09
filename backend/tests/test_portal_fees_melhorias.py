"""Pendências de backend do PR #274 — Portal do Cliente e Financeiro."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException

from app.models.case import Case
from app.models.fee import Fee, FeeStatus, FeeTipo
from app.models.signature import SignatureRequest, SignatureStatus
from app.models.user import User, UserRole


class _Res:
    def __init__(self, val):
        self._val = val

    def scalars(self):
        return self

    def scalar(self):
        return self._val

    def scalar_one_or_none(self):
        return self._val

    def all(self):
        return self._val if isinstance(self._val, list) else []


class _FakeDB:
    def __init__(self, resultados: list):
        self._resultados = list(resultados)
        self.queries: list[str] = []
        self.commits = 0

    async def execute(self, q, *a, **k):
        self.queries.append(str(q))
        return _Res(self._resultados.pop(0))

    async def commit(self):
        self.commits += 1


def _cliente(client_id: str = "cli1") -> User:
    return User(
        id="u-portal",
        role=UserRole.cliente_externo,
        client_id=client_id,
        email="cli@ex.com",
        full_name="Cliente Um",
    )


def _case(**kw) -> Case:
    base = dict(
        id="case1",
        titulo="Ação de Cobrança",
        client_id="cli1",
        area="civil",
        status="em_instrucao",
        numero_interno="DPT-2026-0001",
        numero_processo=None,
        comarca="Sete Lagoas",
        created_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        deleted_at=None,
    )
    base.update(kw)
    return Case(**base)


async def test_meus_casos_inclui_ultima_movimentacao_sem_n_mais_1():
    from app.routers.portal import meus_casos

    dt = datetime(2026, 7, 10, tzinfo=timezone.utc)
    db = _FakeDB(
        [
            [_case(id="case1"), _case(id="case2")],
            [("case1", dt, "Sentença publicada [dj: xyz]")],
        ]
    )
    out = await meus_casos(db=db, cu=_cliente())
    por_id = {c["id"]: c for c in out["data"]}
    assert por_id["case1"]["ultima_movimentacao"] == {
        "data": dt,
        "descricao": "Sentença publicada",
    }
    assert por_id["case2"]["ultima_movimentacao"] is None
    assert len(db.queries) == 2


async def test_meus_casos_sem_casos_nao_consulta_movimentacoes():
    from app.routers.portal import meus_casos

    db = _FakeDB([[]])
    out = await meus_casos(db=db, cu=_cliente())
    assert out == {"data": []}
    assert len(db.queries) == 1


async def test_nao_lidas_conta_sem_marcar_como_lida():
    from app.routers.portal import mensagens_nao_lidas

    db = _FakeDB([3])
    out = await mensagens_nao_lidas(db=db, cu=_cliente())
    assert out == {"nao_lidas": 3}
    assert db.commits == 0
    assert len(db.queries) == 1
    assert "UPDATE" not in db.queries[0].upper()
    assert "client_id" in db.queries[0]
    assert "autor_tipo <> 'cliente'" in db.queries[0]


async def test_nao_lidas_zero_quando_scalar_none():
    from app.routers.portal import mensagens_nao_lidas

    db = _FakeDB([None])
    out = await mensagens_nao_lidas(db=db, cu=_cliente())
    assert out == {"nao_lidas": 0}


async def test_nao_lidas_exige_cliente_externo():
    from app.routers.portal import mensagens_nao_lidas

    staff = User(id="u2", role=UserRole.advogado, client_id=None)
    with pytest.raises(HTTPException) as exc:
        await mensagens_nao_lidas(db=_FakeDB([]), cu=staff)
    assert exc.value.status_code == 403


async def test_listagem_signatures_expoe_hash_completo_e_abreviado():
    from app.routers.signatures import listar

    h = "a1b2c3d4" * 8
    sr = SignatureRequest(
        id="sig1",
        document_id="d1",
        client_id="cli1",
        hash_sha256=h,
        status=SignatureStatus.pendente,
        criado_por="adv1",
        assinado_em=None,
        created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        deleted_at=None,
    )
    db = _FakeDB(
        [
            [sr],
            [("d1", "Procuração")],
            [_cliente()],
        ]
    )
    out = await listar(db=db, cu=_cliente())
    item = out["data"][0]
    assert item["hash_completo"] == h
    assert item["hash"] == h[:16] + "…"
    assert item["documento"] == "Procuração"


async def test_portal_financeiro_inclui_pago_em():
    from app.routers.portal import financeiro

    fee = Fee(
        id="f1",
        tipo=FeeTipo.fixo,
        status=FeeStatus.pago,
        descricao="Parcela 1",
        valor=1500,
        percentual_exito=None,
        data_vencimento=date(2026, 6, 10),
        data_pagamento=date(2026, 6, 9),
        client_id="cli1",
        case_id=None,
        deleted_at=None,
    )
    # 1ª resposta: honorário; 2ª: agregação de baixas parciais (nenhuma).
    db = _FakeDB([[fee], []])
    out = await financeiro(db=db, cu=_cliente())
    assert out["data"][0]["pago_em"] == date(2026, 6, 9)
    assert out["data"][0]["vencimento"] == date(2026, 6, 10)
    assert out["data"][0]["saldo_aberto"] == 0.0


def _fee_ok(**kw) -> Fee:
    base = dict(
        id="f1",
        tipo=FeeTipo.fixo,
        status=FeeStatus.pendente,
        descricao="Honorário",
        valor=None,
        percentual_exito=None,
        data_vencimento=date(2026, 7, 10),
        data_pagamento=None,
        client_id="cli1",
        case_id=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        deleted_at=None,
    )
    base.update(kw)
    return Fee(**base)


def _socio() -> User:
    return User(id="adv1", role=UserRole.socio, client_id=None)


async def test_fees_competencia_valida_filtra_por_mes_do_vencimento():
    from app.routers.fees import listar

    db = _FakeDB([1, [_fee_ok()]])
    out = await listar(
        page=1,
        page_size=20,
        status_f=None,
        client_id=None,
        case_id=None,
        competencia="2026-07",
        db=db,
        cu=_socio(),
    )
    assert out["total"] == 1
    assert out["data"][0].id == "f1"
    assert "EXTRACT" in db.queries[0].upper()
    assert "data_vencimento" in db.queries[0]


@pytest.mark.parametrize(
    "ruim", ["2026-13", "07/2026", "2026-7", "202607", "abcd-ef"]
)
async def test_fees_competencia_invalida_responde_422(ruim):
    from app.routers.fees import listar

    db = _FakeDB([])
    with pytest.raises(HTTPException) as exc:
        await listar(
            page=1,
            page_size=20,
            status_f=None,
            client_id=None,
            case_id=None,
            competencia=ruim,
            db=db,
            cu=_socio(),
        )
    assert exc.value.status_code == 422
    assert db.queries == []


async def test_fees_sem_competencia_nao_filtra_por_mes():
    from app.routers.fees import listar

    db = _FakeDB([0, []])
    out = await listar(
        page=1,
        page_size=20,
        status_f=None,
        client_id=None,
        case_id=None,
        competencia=None,
        db=db,
        cu=_socio(),
    )
    assert out["total"] == 0
    assert "EXTRACT" not in db.queries[0].upper()
