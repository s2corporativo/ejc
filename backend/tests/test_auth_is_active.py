# ── tests/test_auth_is_active.py ─────────────────────────────────────────────
# #3: get_current_user é o ÚNICO gate de runtime que barra um usuário
# desativado/removido no caminho JWT (o AuthMiddleware não checa is_active).
# Sem teste, um refactor que largasse o predicado is_active/deleted_at daria a
# um funcionário demitido acesso total por até 8h com a suíte ainda verde.
#
# Além de exercitar o 401, o DB fake TRAVA o invariante: inspeciona a SQL e
# exige que is_active e deleted_at continuem no filtro.
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.security import get_current_user, create_access_token


class _FakeResult:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class _FakeDB:
    def __init__(self, user):
        self._user = user

    async def execute(self, stmt):
        sql = str(stmt)
        assert "is_active" in sql, "get_current_user deixou de filtrar is_active"
        assert "deleted_at" in sql, "get_current_user deixou de filtrar deleted_at"
        return _FakeResult(self._user)


def _cred(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_usuario_desativado_ou_removido_recebe_401():
    # Token bem assinado, mas o filtro is_active=True/deleted_at IS NULL não
    # retorna ninguém (usuário desativado ou soft-deletado) → 401.
    token = create_access_token("user-1", "advogado")
    with pytest.raises(HTTPException) as exc:
        await get_current_user(_cred(token), _FakeDB(None))
    assert exc.value.status_code == 401


async def test_usuario_ativo_passa():
    token = create_access_token("user-1", "advogado")
    user = SimpleNamespace(id="user-1", is_active=True, deleted_at=None, role="advogado")
    result = await get_current_user(_cred(token), _FakeDB(user))
    assert result is user
