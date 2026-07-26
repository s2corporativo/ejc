"""Integridade contábil de honorários/pagamentos (SYS-082/083/084).

Sem Postgres real (padrão test_portal_fees_melhorias.py / test_nfse_manual.py):
handlers chamados diretamente com fake de sessão. Cobre:
  - SYS-082: pagamento com valor <= 0 rejeitado (schema E handler).
  - SYS-083: FeeUpdate.valor negativo rejeitado; 0 passa (update parcial).
  - SYS-084: criar honorário deriva client_id do caso; rejeita client_id
    divergente (422) e cliente inexistente (404).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.case import Case
from app.models.client import Client
from app.models.user import User, UserRole
from app.schemas.fee import FeeCreate, FeePaymentCreate, FeeUpdate


# ── Fakes ─────────────────────────────────────────────────────────────────────

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
    """Fila de resultados para execute(); registra add/flush/commit/refresh."""

    def __init__(self, resultados: list | None = None):
        self._resultados = list(resultados or [])
        self.added: list = []
        self.commits = 0

    async def execute(self, *a, **k):
        return _Res(self._resultados.pop(0) if self._resultados else None)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass


def _financeiro() -> User:
    return User(id="u-fin", role=UserRole.financeiro, email="fin@ex.com",
                full_name="Financeiro")


def _caso(client_id: str = "cli1") -> Case:
    return Case(id="case1", titulo="Caso", client_id=client_id, area="civil",
                status="ativo", deleted_at=None)


def _cliente(client_id: str = "cli1") -> Client:
    return Client(id=client_id, nome="Fulano", deleted_at=None)


# ── SYS-082: pagamento estritamente positivo ─────────────────────────────────

@pytest.mark.parametrize("valor", [Decimal("0"), Decimal("-10.00")])
def test_pagamento_valor_nao_positivo_rejeitado_no_schema(valor):
    with pytest.raises(ValidationError):
        FeePaymentCreate(valor=valor, data_pagamento=date(2026, 7, 1))


def test_pagamento_valor_positivo_passa_no_schema():
    p = FeePaymentCreate(valor=Decimal("0.01"), data_pagamento=date(2026, 7, 1))
    assert p.valor == Decimal("0.01")


@pytest.mark.parametrize("valor", [Decimal("0"), Decimal("-5")])
async def test_pagamento_handler_rejeita_valor_nao_positivo(valor):
    from app.routers.fees import registrar_pagamento

    # model_construct burla o schema para provar a barreira em profundidade
    # do handler (não depende só do condecimal).
    payload = FeePaymentCreate.model_construct(
        valor=valor, data_pagamento=date(2026, 7, 1), forma=None
    )
    with pytest.raises(HTTPException) as exc:
        await registrar_pagamento("f1", payload, db=_FakeDB(), cu=_financeiro())
    assert exc.value.status_code == 422


# ── SYS-083: FeeUpdate.valor nunca negativo ──────────────────────────────────

def test_fee_update_valor_negativo_rejeitado():
    with pytest.raises(ValidationError):
        FeeUpdate(valor=Decimal("-1"))


def test_fee_update_valor_zero_passa():
    assert FeeUpdate(valor=Decimal("0")).valor == Decimal("0")


# ── SYS-084: honorário herda client_id do caso ───────────────────────────────

async def test_criar_deriva_client_id_do_caso():
    from app.routers.fees import criar

    db = _FakeDB([_caso(client_id="cliX"), _cliente(client_id="cliX")])
    payload = FeeCreate(descricao="Honorário", client_id="cliX", case_id="case1")
    fee = await criar(payload, db=db, cu=_financeiro())
    assert fee.client_id == "cliX"
    assert fee.case_id == "case1"


async def test_criar_client_id_divergente_do_caso_422():
    from app.routers.fees import criar

    # payload traz cliente B, mas o caso pertence ao cliente A.
    db = _FakeDB([_caso(client_id="cliA")])
    payload = FeeCreate(descricao="Honorário", client_id="cliB", case_id="case1")
    with pytest.raises(HTTPException) as exc:
        await criar(payload, db=db, cu=_financeiro())
    assert exc.value.status_code == 422


async def test_criar_caso_inexistente_404():
    from app.routers.fees import criar

    db = _FakeDB([None])  # caso não encontrado
    payload = FeeCreate(descricao="Honorário", client_id="cliX", case_id="case1")
    with pytest.raises(HTTPException) as exc:
        await criar(payload, db=db, cu=_financeiro())
    assert exc.value.status_code == 404


async def test_criar_cliente_inexistente_404():
    from app.routers.fees import criar

    # sem case_id: valida direto o client_id do payload → não existe.
    db = _FakeDB([None])
    payload = FeeCreate(descricao="Honorário", client_id="cli-fantasma")
    with pytest.raises(HTTPException) as exc:
        await criar(payload, db=db, cu=_financeiro())
    assert exc.value.status_code == 404


async def test_criar_sem_caso_valida_cliente_e_persiste():
    from app.routers.fees import criar

    db = _FakeDB([_cliente(client_id="cliZ")])
    payload = FeeCreate(descricao="Honorário", client_id="cliZ")
    fee = await criar(payload, db=db, cu=_financeiro())
    assert fee.client_id == "cliZ"
    assert db.commits == 1
