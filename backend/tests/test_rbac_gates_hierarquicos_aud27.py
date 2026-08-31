# -*- coding: utf-8 -*-
"""Gates que ficaram no piso hierárquico depois da migração do Issue #694.

`AUD27-P1-1` (`POST /cases/`) e `AUD27-P2-2` (`qualidade.py`): os routers
irmãos migraram para allowlist EXATA em `4ab8618`, estes dois não. Como
`require_roles` toma o MENOR nível da lista como piso e promove qualquer papel
acima dele, `financeiro` (nível 4) entrava em superfície jurídica sem pertencer
à equipe — reproduzido ao vivo em 30/08/2026:

    POST /qualidade/verificar-citacoes  como financeiro → 422 (passou do gate)
    POST /cases/                        como financeiro → 404 do handler
                                        (o gate deixou entrar; barrou o sigilo)

A correção migra os dois para `require_roles_exact`, preservando quem já
usava — inclusive o estagiário, que criava caso pelo piso e é equipe jurídica.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import EQUIPE_JURIDICA, ROLE_LEVEL, get_current_user
from app.models.user import User, UserRole


def _u(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role, full_name="Fulano de Teste")


# ── AUD27-P1-1 — POST /cases/ ────────────────────────────────────────────────

def test_criar_caso_usa_allowlist_exata_sem_financeiro():
    from app.routers.cases import _PODE_CRIAR_CASO

    assert "financeiro" not in _PODE_CRIAR_CASO
    # A causa-raiz: o piso da lista antiga era `secretaria` (nível 2), abaixo
    # de financeiro — por isso a promoção acontecia.
    assert ROLE_LEVEL["financeiro"] > ROLE_LEVEL["secretaria"]


def test_criar_caso_preserva_quem_ja_criava():
    """A correção não pode tirar acesso de quem legitimamente abre caso."""
    from app.routers.cases import _PODE_CRIAR_CASO

    assert EQUIPE_JURIDICA <= _PODE_CRIAR_CASO      # inclui estagiário
    assert "secretaria" in _PODE_CRIAR_CASO          # intake


@pytest.mark.parametrize("role", [UserRole.financeiro, UserRole.cliente_externo])
def test_criar_caso_barra_papel_fora_da_allowlist(role):
    from app.core.security import require_roles_exact
    from app.routers.cases import _PODE_CRIAR_CASO

    checker = require_roles_exact(_PODE_CRIAR_CASO)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(checker(_u(role)))
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "role",
    [UserRole.superadmin, UserRole.admin, UserRole.socio, UserRole.advogado,
     UserRole.advogado_auxiliar, UserRole.estagiario, UserRole.secretaria],
)
def test_criar_caso_permite_equipe_e_intake(role):
    from app.core.security import require_roles_exact
    from app.routers.cases import _PODE_CRIAR_CASO

    checker = require_roles_exact(_PODE_CRIAR_CASO)
    assert asyncio.run(checker(_u(role))) is not None  # não levanta


# ── AUD27-P2-2 — qualidade.py (endpoints reais) ──────────────────────────────

_ROTAS_QUALIDADE = [
    "/qualidade/verificar-citacoes",
    "/qualidade/consistencia",
    "/qualidade/simular-adversario",
]


def _client_qualidade(role: UserRole) -> TestClient:
    from app.routers import qualidade as qualidade_router

    app = FastAPI()
    app.include_router(qualidade_router.router)
    app.dependency_overrides[get_current_user] = lambda: _u(role)
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


@pytest.mark.parametrize("rota", _ROTAS_QUALIDADE)
def test_qualidade_barra_financeiro(rota):
    """403 do gate — antes vinha 422, prova de que o corpo chegou a ser lido."""
    resp = _client_qualidade(UserRole.financeiro).post(rota, json={})
    assert resp.status_code == 403


@pytest.mark.parametrize("rota", _ROTAS_QUALIDADE)
def test_qualidade_permite_estagiario(rota):
    """Equipe jurídica segue passando: 422 do corpo vazio, nunca 403."""
    resp = _client_qualidade(UserRole.estagiario).post(rota, json={})
    assert resp.status_code != 403
