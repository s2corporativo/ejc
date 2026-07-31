# Testes de escopo de permissão por perfil (visibilidade de dados).
from types import SimpleNamespace
from app.models.user import UserRole
from app.core.security import ROLE_LEVEL
from app.services.jurimetria import pode_ver_todos as pvt_jurimetria
from app.services.case_health import pode_ver_todos as pvt_case_health
from app.services.taskscore import pode_ver_todos as pvt_taskscore
from app.services.rentabilidade import pode_ver_todos as pvt_rentabilidade

TODOS = (pvt_jurimetria, pvt_case_health, pvt_taskscore, pvt_rentabilidade)


def _user(role: UserRole):
    return SimpleNamespace(id="u1", role=role)


def test_admin_e_superadmin_veem_tudo():
    for pode_ver in TODOS:
        assert pode_ver(_user(UserRole.superadmin)) is True
        assert pode_ver(_user(UserRole.admin)) is True


def test_socio_e_advogados_nao_veem_tudo():
    # pode_ver_todos é gated em "admin" (nível 8); sócio(7) e abaixo não veem tudo.
    for pode_ver in TODOS:
        assert pode_ver(_user(UserRole.socio)) is False
        assert pode_ver(_user(UserRole.advogado)) is False
        assert pode_ver(_user(UserRole.advogado_auxiliar)) is False


def test_hierarquia_de_roles_consistente():
    assert (ROLE_LEVEL["superadmin"] > ROLE_LEVEL["admin"]
            > ROLE_LEVEL["socio"] > ROLE_LEVEL["advogado"]
            > ROLE_LEVEL["advogado_auxiliar"])
    assert ROLE_LEVEL["advogado"] > ROLE_LEVEL["cliente_externo"]
