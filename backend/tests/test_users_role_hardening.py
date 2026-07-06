"""Anti-escalonamento de privilégio em /users (achado de auditoria).

Um admin (nível 8) NÃO pode conceder/gerenciar perfil de nível superior
(superadmin=9). Testa as guardas puras de users.py sem tocar no banco.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.users import _validar_atribuicao_role, _validar_alvo, _nivel


def _u(role: str):
    return SimpleNamespace(role=role)


def test_admin_nao_concede_superadmin():
    admin = _u("admin")
    with pytest.raises(HTTPException) as exc:
        _validar_atribuicao_role(admin, "superadmin")
    assert exc.value.status_code == 403


def test_admin_concede_perfis_ate_o_proprio_nivel():
    admin = _u("admin")
    for role in ("advogado", "socio", "financeiro", "admin"):
        _validar_atribuicao_role(admin, role)  # não levanta


def test_superadmin_concede_qualquer():
    sa = _u("superadmin")
    _validar_atribuicao_role(sa, "superadmin")  # não levanta


def test_role_desconhecido_e_422():
    with pytest.raises(HTTPException) as exc:
        _validar_atribuicao_role(_u("admin"), "root")
    assert exc.value.status_code == 422


def test_role_none_e_noop():
    _validar_atribuicao_role(_u("admin"), None)  # não levanta


def test_admin_nao_gerencia_superadmin():
    with pytest.raises(HTTPException) as exc:
        _validar_alvo(_u("admin"), _u("superadmin"))
    assert exc.value.status_code == 403


def test_admin_gerencia_pares_e_inferiores():
    admin = _u("admin")
    _validar_alvo(admin, _u("admin"))
    _validar_alvo(admin, _u("advogado"))


def test_niveis_conhecidos():
    assert _nivel("superadmin") > _nivel("admin") > _nivel("advogado") > _nivel("secretaria")
    assert _nivel("desconhecido") == 0
