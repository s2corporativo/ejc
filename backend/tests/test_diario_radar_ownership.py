# ── tests/test_diario_radar_ownership.py ─────────────────────────────────────
# #10(b): as listagens do Diário Oficial e o feed do Radar de compliance
# retornavam TODOS os itens sem filtro de ownership. Agora: gestão (socio+) vê
# tudo; a equipe vê os itens office-wide (sem caso) OU dos casos em que é
# responsável/auxiliar. Estes testes travam essa regra.
from types import SimpleNamespace

from sqlalchemy import select

from app.routers.diario_oficial import _filtrar_por_ownership
from app.models.diario_oficial import DiarioOficialAlerta
from app.routers.compliance import _acessa_caso


def _user(role, uid="u1"):
    return SimpleNamespace(id=uid, role=SimpleNamespace(value=role))


def _caso(resp=None, aux=None):
    return SimpleNamespace(advogado_responsavel_id=resp, advogado_auxiliar_id=aux)


# ── Diário Oficial: _filtrar_por_ownership ────────────────────────────────────
def test_gestao_recebe_query_inalterada():
    q0 = select(DiarioOficialAlerta)
    assert _filtrar_por_ownership(q0, DiarioOficialAlerta.case_id, _user("socio")) is q0


def test_equipe_filtra_por_caso_preservando_office_wide():
    q = _filtrar_por_ownership(
        select(DiarioOficialAlerta), DiarioOficialAlerta.case_id, _user("advogado")
    )
    sql = str(q.compile(compile_kwargs={"literal_binds": False})).lower()
    assert "case_id is null" in sql                       # office-wide preservado
    assert "advogado_responsavel_id" in sql and "cases" in sql  # restrição por caso próprio


# ── Radar de compliance: _acessa_caso ─────────────────────────────────────────
def test_acessa_caso_gestao_ve_tudo():
    assert _acessa_caso(_user("socio"), _caso(resp="outro", aux="outro2")) is True


def test_acessa_caso_equipe_ve_proprio_e_office_wide_e_orfao():
    assert _acessa_caso(_user("advogado", "u1"), _caso(resp="u1")) is True          # próprio
    assert _acessa_caso(_user("advogado", "u1"), _caso(aux="u1")) is True           # auxiliar
    assert _acessa_caso(_user("advogado", "u1"), None) is True                      # office-wide
    assert _acessa_caso(_user("advogado", "u1"), _caso()) is True                   # órfão (legado)


def test_acessa_caso_equipe_nao_ve_caso_de_outro():
    assert _acessa_caso(_user("advogado", "u1"), _caso(resp="outro", aux="outro2")) is False
