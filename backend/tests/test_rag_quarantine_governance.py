import pytest
from fastapi import HTTPException

from app.routers.rag_governance import (
    _deve_retirar_quarentena,
    _registrar_decisao_revisao,
    _retirar_quarentena,
)


AGORA = "2026-08-14T23:30:00+00:00"


def test_conferir_fonte_agora_solicita_retirada_quando_quarentena_ativa():
    assert _deve_retirar_quarentena(
        {"quarantine_active": True},
        confirmar_fonte_agora=True,
        retirar_explicito=False,
    ) is True


def test_conferir_fonte_fora_de_quarentena_nao_cria_retirada_artificial():
    assert _deve_retirar_quarentena(
        {"quarantine_active": False},
        confirmar_fonte_agora=True,
        retirar_explicito=False,
    ) is False


def test_flag_explicita_ainda_exige_confirmacao_da_fonte_na_retirada_real():
    assert _deve_retirar_quarentena(
        {"quarantine_active": True},
        confirmar_fonte_agora=False,
        retirar_explicito=True,
    ) is True
    with pytest.raises(HTTPException) as exc:
        _retirar_quarentena(
            {"quarantine_active": True, "rag_status": "pendente"},
            user_id="revisor-1",
            confirmar_fonte_agora=False,
            agora=AGORA,
        )
    assert exc.value.status_code == 422
    assert "confirmar_fonte_agora=true" in str(exc.value.detail)


def test_retirada_de_quarentena_nao_aprova_documento():
    extra = _retirar_quarentena(
        {
            "quarantine_active": True,
            "quarantine_reason": "revalidar fonte",
            "rag_status": "aprovado",
            "human_reviewed": True,
        },
        user_id="revisor-1",
        confirmar_fonte_agora=True,
        agora=AGORA,
    )
    assert extra["quarantine_active"] is False
    assert extra["rag_status"] == "pendente"
    assert extra["requires_human_review"] is True
    assert extra["human_reviewed"] is False
    assert extra["quarantine_released_by"] == "revisor-1"
    assert extra["quarantine_released_at"] == AGORA
    assert extra["quarantine_reason"] == "revalidar fonte"


def test_aprovacao_direta_de_documento_em_quarentena_e_bloqueada():
    with pytest.raises(HTTPException) as exc:
        _registrar_decisao_revisao(
            {"quarantine_active": True, "rag_status": "pendente"},
            aprovado=True,
            user_id="revisor-1",
            agora=AGORA,
        )
    assert exc.value.status_code == 422
    assert "quarentena" in str(exc.value.detail).lower()


def test_recusa_humana_e_permitida_mesmo_durante_quarentena():
    extra = _registrar_decisao_revisao(
        {"quarantine_active": True, "rag_status": "pendente"},
        aprovado=False,
        user_id="revisor-1",
        agora=AGORA,
    )
    assert extra["quarantine_active"] is True
    assert extra["rag_status"] == "recusado"
    assert extra["human_reviewed"] is True
    assert extra["human_reviewed_by"] == "revisor-1"


def test_aprovacao_apos_retirada_de_quarentena_grava_contrato_rag():
    liberado = _retirar_quarentena(
        {"quarantine_active": True, "rag_status": "pendente"},
        user_id="revisor-1",
        confirmar_fonte_agora=True,
        agora=AGORA,
    )
    aprovado = _registrar_decisao_revisao(
        liberado,
        aprovado=True,
        user_id="revisor-1",
        agora=AGORA,
    )
    assert aprovado["quarantine_active"] is False
    assert aprovado["rag_status"] == "aprovado"
    assert aprovado["requires_human_review"] is True
    assert aprovado["human_reviewed"] is True
    assert aprovado["human_reviewed_by"] == "revisor-1"
