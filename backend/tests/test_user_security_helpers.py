"""Permissões efetivas expostas pela camada segura da conta."""

from app.models.user import UserRole
from app.routers.users import _permissoes, _role_value


def test_role_value_aceita_enum_e_string():
    assert _role_value(UserRole.advogado) == "advogado"
    assert _role_value("financeiro") == "financeiro"


def test_permissoes_reutilizam_matriz_central():
    assert "casos" in _permissoes(UserRole.advogado)
    assert "honorarios" in _permissoes(UserRole.financeiro)
    assert _permissoes(UserRole.superadmin) == ["*"]


def test_perfil_desconhecido_nao_recebe_permissao():
    assert _permissoes("perfil_inexistente") == []
