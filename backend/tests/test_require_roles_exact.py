"""require_roles_exact (SYS-009) — allowlist ESTRITA sem fallback de nível.

Sem banco: exercita só o ramo de autorização por perfil (dispara antes de tocar
o banco). Contrasta com require_roles (hierárquico), provando que um papel de
nível SUPERIOR fora do conjunto NÃO atravessa um gate lateral.
"""
import pytest
from fastapi import HTTPException

from app.core.security import require_roles, require_roles_exact, exigir_papeis_estritos
from app.models.user import User, UserRole


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


async def test_exact_barra_papel_superior_fora_do_conjunto():
    # Gate lateral de área financeira: só financeiro/admin/superadmin.
    checker = require_roles_exact("financeiro", "admin", "superadmin")
    # advogado (nível 6 > financeiro 4) NÃO passa no gate estrito.
    with pytest.raises(HTTPException) as exc:
        await checker(_user(UserRole.advogado))
    assert exc.value.status_code == 403
    # sócio também é barrado (não listado), apesar do nível alto.
    with pytest.raises(HTTPException):
        await checker(_user(UserRole.socio))


async def test_exact_permite_papel_listado():
    checker = require_roles_exact("financeiro", "admin", "superadmin")
    assert (await checker(_user(UserRole.financeiro))).role == UserRole.financeiro
    assert (await checker(_user(UserRole.admin))).role == UserRole.admin


async def test_exact_barra_cliente_externo():
    checker = require_roles_exact("financeiro")
    with pytest.raises(HTTPException) as exc:
        await checker(_user(UserRole.cliente_externo))
    assert exc.value.status_code == 403


async def test_alias_portugues_equivale():
    assert exigir_papeis_estritos is require_roles_exact


async def test_contraste_com_require_roles_hierarquico():
    # Prova a diferença: require_roles (hierárquico) DEIXA o advogado passar num
    # gate ["financeiro"] pelo fallback de nível; require_roles_exact NÃO.
    hier = require_roles(["financeiro"])
    assert (await hier(_user(UserRole.advogado))).role == UserRole.advogado

    estrito = require_roles_exact("financeiro")
    with pytest.raises(HTTPException):
        await estrito(_user(UserRole.advogado))
