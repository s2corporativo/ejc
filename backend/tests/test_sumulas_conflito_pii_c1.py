"""Regressão C1 (auditoria 01/10/2026): POST /sumulas/verificar-conflito
exigia só login e devolvia CPF/CNPJ em claro. Agora: RBAC de CRM, rate limit
e documento mascarado na origem."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.routers import sumulas


def _user(role: str):
    return SimpleNamespace(id="u1", role=SimpleNamespace(value=role))


@pytest.mark.parametrize("role", ["estagiario", "financeiro", "advogado_auxiliar"])
def test_perfis_sem_crm_recebem_403(role):
    with pytest.raises(HTTPException) as exc:
        sumulas._req_conflito(_user(role))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["superadmin", "admin", "socio", "advogado", "secretaria"])
def test_perfis_de_crm_passam(role):
    assert sumulas._req_conflito(_user(role)).role.value == role


def test_rota_tem_rate_limit_e_gate():
    from app.main import app

    rota = next(
        r for r in app.routes
        if getattr(r, "path", None) == "/api/sumulas/verificar-conflito"
        and "POST" in (getattr(r, "methods", None) or set())
    )
    assert rota.dependencies, "rate_limit ausente"
    nomes = {getattr(d.call, "__name__", "") for d in rota.dependant.dependencies}
    assert "_req_conflito" in nomes


def test_documento_do_achado_sai_mascarado():
    from app.services import conflito_interesses, conflito_service

    cliente = SimpleNamespace(
        nome="Fulano de Tal", razao_social=None, documento_plain="12345678901"
    )

    async def _por_doc(db, docs):
        return [cliente]

    with patch.object(conflito_service, "_clientes_por_documentos", _por_doc):
        res = asyncio.run(conflito_interesses.verificar_conflito(
            db=AsyncMock(), parte_contraria_nome=None,
            parte_contraria_doc="12345678901", user_id="u1", case_id=None,
        ))
    docs = [m.get("documento") for m in res["matches"]]
    assert docs and all(d and "12345678901" not in d for d in docs)
