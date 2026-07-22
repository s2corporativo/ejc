"""Núcleo operacional do caso — contratos e estados puros, sem banco."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.case import CaseStatus
from app.schemas.case_next_action import (
    CaseNextActionComplete,
    CaseNextActionCreate,
    CaseNextActionWaiverCreate,
)
from app.services.case_next_action import derive_operational_state


OWNER_ID = "11111111-1111-1111-1111-111111111111"
ORIGIN_ID = "22222222-2222-2222-2222-222222222222"


def _action_payload(**overrides):
    data = {
        "title": "Revisar contestação",
        "owner_id": OWNER_ID,
        "due_at": datetime.now(timezone.utc) + timedelta(days=2),
        "urgency": "media",
        "blocked": False,
        "waiting_on": "ninguem",
        "origin_type": "manual",
    }
    data.update(overrides)
    return data


def _case(status=CaseStatus.ativo):
    return SimpleNamespace(status=status)


def _action(**overrides):
    data = {
        "title": "Revisar contestação",
        "due_at": datetime.now(timezone.utc) + timedelta(days=10),
        "urgency": "media",
        "blocked": False,
        "waiting_on": "ninguem",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_next_action_requires_timezone_and_future_date():
    with pytest.raises(ValidationError, match="fuso horário"):
        CaseNextActionCreate(
            **_action_payload(due_at=datetime.now() + timedelta(days=1))
        )

    with pytest.raises(ValidationError, match="deve estar no futuro"):
        CaseNextActionCreate(
            **_action_payload(
                due_at=datetime.now(timezone.utc) - timedelta(minutes=1)
            )
        )


def test_next_action_block_requires_reason():
    with pytest.raises(ValidationError, match="blocked_reason"):
        CaseNextActionCreate(
            **_action_payload(blocked=True, waiting_on="cliente")
        )


def test_next_action_waiting_requires_block():
    with pytest.raises(ValidationError, match="exige blocked=true"):
        CaseNextActionCreate(
            **_action_payload(waiting_on="cliente")
        )


def test_next_action_origin_is_traceable():
    with pytest.raises(ValidationError, match="origin_id é obrigatório"):
        CaseNextActionCreate(
            **_action_payload(origin_type="documento")
        )

    valid = CaseNextActionCreate(
        **_action_payload(origin_type="documento", origin_id=ORIGIN_ID)
    )
    assert valid.origin_id == ORIGIN_ID


def test_manual_origin_rejects_foreign_id():
    with pytest.raises(ValidationError, match="origem manual"):
        CaseNextActionCreate(
            **_action_payload(origin_id=ORIGIN_ID)
        )


def test_waiver_is_temporary_and_bounded():
    with pytest.raises(ValidationError, match="no futuro"):
        CaseNextActionWaiverCreate(
            reason="Aguardando evento externo verificável",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

    with pytest.raises(ValidationError, match="90 dias"):
        CaseNextActionWaiverCreate(
            reason="Aguardando evento externo verificável",
            expires_at=datetime.now(timezone.utc) + timedelta(days=91),
        )


def test_completion_has_single_destination():
    replacement = CaseNextActionCreate(**_action_payload())
    waiver = CaseNextActionWaiverCreate(
        reason="Aguardando evento externo verificável",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    with pytest.raises(ValidationError, match="nunca ambos"):
        CaseNextActionComplete(replacement=replacement, waiver=waiver)


@pytest.mark.parametrize(
    "case_status,action,expected",
    [
        (CaseStatus.triagem, None, "onboarding"),
        (CaseStatus.ativo, None, "planejamento"),
        (CaseStatus.acordo, None, "negociacao"),
        (CaseStatus.encerrado, None, "encerrado"),
        (
            CaseStatus.ativo,
            _action(blocked=True, waiting_on="cliente"),
            "aguardando_cliente",
        ),
        (
            CaseStatus.ativo,
            _action(blocked=True, waiting_on="tribunal"),
            "aguardando_terceiro",
        ),
        (
            CaseStatus.ativo,
            _action(
                urgency="critica",
                due_at=datetime.now(timezone.utc) + timedelta(days=20),
            ),
            "providencia_urgente",
        ),
        (
            CaseStatus.ativo,
            _action(due_at=datetime.now(timezone.utc) + timedelta(days=2)),
            "providencia_urgente",
        ),
        (CaseStatus.ativo, _action(), "em_andamento"),
    ],
)
def test_operational_state_is_deterministic(case_status, action, expected):
    assert derive_operational_state(_case(case_status), action, None) == expected
