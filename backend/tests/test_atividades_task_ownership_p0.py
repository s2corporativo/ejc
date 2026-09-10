"""Regressão P0: a Central não usa responsabilidade como atalho de acesso ao caso."""
from __future__ import annotations

from app.models.user import User, UserRole
from app.routers.atividades import listar_atividades


class _Rows:
    def mappings(self):
        return self

    def all(self):
        return []


class _DB:
    def __init__(self):
        self.executed: list[tuple[str, dict | None]] = []

    async def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        return _Rows()


def _advogado() -> User:
    return User(id="u1", role=UserRole.advogado)


async def test_tarefa_com_caso_exige_carteira_na_fonte_canonica():
    db = _DB()

    await listar_atividades(apenas_pendentes=False, db=db, cu=_advogado())

    sql, params = db.executed[0]
    assert params == {"uid": "u1"}
    assert "v.tipo = 'tarefa'" in sql
    assert "v.case_id IS NULL AND v.responsavel_id = :uid" in sql
    assert "v.case_id IS NOT NULL" in sql
    assert "cc.id = v.case_id" in sql
    assert "cc.deleted_at IS NULL" in sql
    assert "cc.advogado_responsavel_id = :uid" in sql
    assert "cc.advogado_auxiliar_id = :uid" in sql


async def test_demais_tipos_preservam_contrato_de_responsabilidade_ou_carteira():
    db = _DB()

    await listar_atividades(apenas_pendentes=False, db=db, cu=_advogado())

    sql, _ = db.executed[0]
    assert "v.tipo <> 'tarefa'" in sql
    assert "v.responsavel_id = :uid" in sql
    assert "EXISTS" in sql
