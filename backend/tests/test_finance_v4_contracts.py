from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.finance_governance import (
    exigir_lock_financeiro,
    permitir_correcao_competencia_fechada,
    construir_snapshot_referencia,
)
from app.schemas.fee import FeeUpdate
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

    def scalar_one_or_none(self):
        return self.value

    def mappings(self):
        return self

    def one(self):
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


class _SeqDB:
    def __init__(self, values):
        self.values = list(values)

    async def execute(self, *_args, **_kwargs):
        return _Result(self.values.pop(0))


@pytest.mark.asyncio
async def test_correcao_mes_fechado_exige_motivo_e_permite_com_auditoria():
    with pytest.raises(HTTPException) as exc:
        await permitir_correcao_competencia_fechada(
            _DB('closing-id'), '2026-09', None, 'Alterar despesa'
        )
    assert exc.value.status_code == 422
    assert await permitir_correcao_competencia_fechada(
        _DB('closing-id'), '2026-09', 'Correção documental', 'Alterar despesa'
    ) is True
    assert await permitir_correcao_competencia_fechada(
        _DB(None), '2026-10', None, 'Alterar despesa'
    ) is False


@pytest.mark.asyncio
async def test_snapshot_referencia_primeiro_fechamento_integro():
    totals = {
        'receitas': 1000, 'estornos': 0, 'despesas_escritorio': 200,
        'despesas_casos': 100, 'comissoes_geradas': 250,
        'comissoes_pagas': 250, 'documentos_vinculados': 3,
    }
    db = _SeqDB([totals, 0])
    snap = await construir_snapshot_referencia(
        db, '2026-09',
        pre_fechamento={'total_bloqueios': 0, 'total_revisoes': 0, 'score_integridade': 100},
        rentabilidade={'resumo': {'resultado_escritorio': 450}},
    )
    assert snap['is_baseline'] is True
    assert snap['immutable'] is True
    assert snap['resultado_escritorio'] == 450.0
    assert snap['documentos_vinculados'] == 3
    assert len(snap['sha256']) == 64


def test_fee_update_expoe_campos_de_negocio_editaveis():
    esperados = {
        'tipo', 'descricao', 'valor', 'percentual_exito', 'status',
        'data_vencimento', 'client_id', 'case_id', 'observacoes', 'motivo_correcao',
    }
    assert esperados <= set(FeeUpdate.model_fields)
