"""Regressão da Issue #696 (Defeito 2).

`fees.criar` buscava o `Case` de `payload.case_id` apenas para provar que
existe — nunca comparava `caso.client_id` com `payload.client_id`. Como os
dois campos são obrigatórios e independentes em `FeeCreate`, era possível
criar um honorário vinculado ao caso do cliente A mas cobrado do cliente B:
o valor vazava para o financeiro/relatórios de B e para o Portal do Cliente
de B (que filtra por `Fee.client_id`).

Decisão registrada no PR: RECUSAR com 422 (não derivar silenciosamente) —
mais explícito, e nenhum caller hoje envia `case_id` no `POST /fees`
(o formulário de Honorários.tsx não expõe esse campo), então a checagem é
puramente defensiva e não altera o fluxo legítimo existente.

Padrão do repo: sem banco real — fake de sessão local (mesmo desenho de
`test_portal_fees_melhorias.py`), handler chamado diretamente.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.models.case import Case
from app.models.user import User, UserRole
from app.schemas.fee import FeeCreate


class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val


class _FakeDB:
    """Fila de resultados para execute(); registra add()/commit()/refresh()."""

    def __init__(self, resultados: list):
        self._resultados = list(resultados)
        self.added: list = []
        self.commits = 0
        self.refreshed: list = []

    async def execute(self, q, *a, **k):
        return _Res(self._resultados.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)


def _case(**kw) -> Case:
    base = dict(
        id="case1", titulo="Ação de Cobrança", client_id="cliente-A",
        area="civil", status="em_instrucao", numero_interno="DPT-2026-0001",
        numero_processo=None, comarca="Sete Lagoas",
        created_at=datetime(2026, 1, 5, tzinfo=timezone.utc), deleted_at=None,
    )
    base.update(kw)
    return Case(**base)


def _socio() -> User:
    return User(id="adv1", role=UserRole.socio, client_id=None)


def _payload(**kw) -> FeeCreate:
    base = dict(
        tipo="fixo", descricao="Honorário contratual", valor="1500.00",
        client_id="cliente-A", case_id="case1",
    )
    base.update(kw)
    return FeeCreate(**base)


# ── negação: caso do cliente A, client_id do cliente B ───────────────────────

async def test_criar_com_case_id_de_um_cliente_e_client_id_de_outro_e_422():
    from app.routers.fees import criar

    db = _FakeDB([_case(id="case1", client_id="cliente-A")])
    payload = _payload(case_id="case1", client_id="cliente-B")

    with pytest.raises(HTTPException) as ei:
        await criar(payload, db=db, cu=_socio())

    assert ei.value.status_code == 422
    # Nada pode ser persistido quando a divergência é detectada.
    assert db.added == []
    assert db.commits == 0


# ── fluxo legítimo: sem case_id ───────────────────────────────────────────────

async def test_criar_sem_case_id_nao_consulta_caso_e_cria_normalmente():
    from app.routers.fees import criar

    db = _FakeDB([])  # nenhuma query de Case esperada
    payload = _payload(case_id=None, client_id="cliente-A")

    fee = await criar(payload, db=db, cu=_socio())

    assert fee.client_id == "cliente-A"
    assert fee.case_id is None
    assert db.commits == 1
    assert len(db.added) == 2  # Fee + AuditLog


# ── fluxo legítimo: case_id e client_id coerentes ─────────────────────────────

async def test_criar_com_case_id_e_client_id_coerentes_cria_normalmente():
    from app.routers.fees import criar

    db = _FakeDB([_case(id="case1", client_id="cliente-A")])
    payload = _payload(case_id="case1", client_id="cliente-A")

    fee = await criar(payload, db=db, cu=_socio())

    assert fee.client_id == "cliente-A"
    assert fee.case_id == "case1"
    assert db.commits == 1
    assert len(db.added) == 2  # Fee + AuditLog


# ── caso inexistente continua 404 (comportamento preexistente preservado) ────

async def test_criar_com_case_id_inexistente_continua_404():
    from app.routers.fees import criar

    db = _FakeDB([None])
    payload = _payload(case_id="case-fantasma", client_id="cliente-A")

    with pytest.raises(HTTPException) as ei:
        await criar(payload, db=db, cu=_socio())

    assert ei.value.status_code == 404
    assert db.added == []
