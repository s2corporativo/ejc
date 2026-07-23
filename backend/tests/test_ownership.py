"""Ownership de caso — Fase 3A (correção de IDOR).

Valida o gate canônico core.ownership.verificar_acesso_caso com um fake de
sessão (sem banco real): gestão passa, equipe passa, anti-lockout passa,
estranho 403, caso inexistente 404.
"""
import pytest
from fastapi import HTTPException

from app.core.ownership import is_gestao, verificar_acesso_caso
from app.models.user import User, UserRole
from app.models.case import Case


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val


class _FakeDB:
    def __init__(self, case):
        self._case = case

    async def execute(self, *a, **k):
        return _Res(self._case)


def test_is_gestao():
    assert is_gestao(_user(UserRole.socio))
    assert is_gestao(_user(UserRole.admin))
    assert is_gestao(_user(UserRole.superadmin))
    assert not is_gestao(_user(UserRole.advogado))
    assert not is_gestao(_user(UserRole.estagiario))


async def test_caso_inexistente_404():
    with pytest.raises(HTTPException) as exc:
        await verificar_acesso_caso(_FakeDB(None), _user(UserRole.advogado), "c1")
    assert exc.value.status_code == 404


async def test_gestao_passa_mesmo_sem_ser_dono():
    case = Case(id="c1", advogado_responsavel_id="outro", advogado_auxiliar_id=None)
    assert await verificar_acesso_caso(_FakeDB(case), _user(UserRole.socio), "c1") is case


async def test_responsavel_passa():
    case = Case(id="c1", advogado_responsavel_id="u1", advogado_auxiliar_id=None)
    assert await verificar_acesso_caso(_FakeDB(case), _user(UserRole.advogado, "u1"), "c1") is case


async def test_auxiliar_passa():
    case = Case(id="c1", advogado_responsavel_id="x", advogado_auxiliar_id="u1")
    assert await verificar_acesso_caso(_FakeDB(case), _user(UserRole.advogado, "u1"), "c1") is case


async def test_caso_sem_dono_so_gestao_acessa():
    # Hardening (auditoria de melhoria): caso ÓRFÃO (sem responsável NEM
    # auxiliar) NÃO libera mais qualquer usuário interno. Só a gestão (socio+)
    # acessa — ela é o escape-hatch legítimo (assume/reatribui o caso); perfis
    # baixos passam a receber 403.
    case = Case(id="c1", advogado_responsavel_id=None, advogado_auxiliar_id=None)
    assert await verificar_acesso_caso(_FakeDB(case), _user(UserRole.socio, "u1"), "c1") is case
    with pytest.raises(HTTPException) as exc:
        await verificar_acesso_caso(_FakeDB(case), _user(UserRole.estagiario, "u1"), "c1")
    assert exc.value.status_code == 403


async def test_estranho_403():
    case = Case(id="c1", advogado_responsavel_id="x", advogado_auxiliar_id="y")
    with pytest.raises(HTTPException) as exc:
        await verificar_acesso_caso(_FakeDB(case), _user(UserRole.advogado, "u1"), "c1")
    assert exc.value.status_code == 403
