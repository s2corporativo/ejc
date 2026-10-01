from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.finance_governance import exigir_lock_financeiro
from app.services.finance_status import (
    APPROVAL_TRANSITIONS,
    EXPENSE_TRANSITIONS,
    WITHDRAWAL_TRANSITIONS,
    exigir_transicao,
)


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _DB:
    def __init__(self, value):
        self.value = value

    async def execute(self, *_args, **_kwargs):
        return _Result(self.value)


def test_transicoes_financeiras_canonicas():
    exigir_transicao("pendente", "aprovado", WITHDRAWAL_TRANSITIONS, entidade="retirada")
    exigir_transicao("aprovado", "pago", WITHDRAWAL_TRANSITIONS, entidade="retirada")
    exigir_transicao("pendente", "pago", EXPENSE_TRANSITIONS, entidade="despesa")
    exigir_transicao("aprovado", "consumido", APPROVAL_TRANSITIONS, entidade="aprovação")

    with pytest.raises(HTTPException) as exc:
        exigir_transicao("pago", "pendente", WITHDRAWAL_TRANSITIONS, entidade="retirada")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_lock_financeiro_fail_closed():
    await exigir_lock_financeiro(_DB(True), "finance_close", "2026-10")
    with pytest.raises(HTTPException) as exc:
        await exigir_lock_financeiro(_DB(False), "finance_close", "2026-10")
    assert exc.value.status_code == 409


def test_migration_168_unifica_comprovantes_no_ged():
    src = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "168_finance_ged_links.py"
    ).read_text(encoding="utf-8")
    assert "office_expenses" in src
    assert "bank_analyses" in src
    assert "fee_payments" in src
    assert '"documents"' in src
    assert '["id"]' in src
    assert "comprovante_doc_id" in src
    assert 'ondelete="SET NULL"' in src
