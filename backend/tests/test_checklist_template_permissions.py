"""Regressão de autorização na remoção de templates de checklist."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.checklist import ChecklistTemplate
from app.routers.checklists import remover_template


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _DB:
    def __init__(self, value):
        self.value = value
        self.statement = None
        self.committed = False

    async def execute(self, statement):
        self.statement = statement
        return _Result(self.value)

    async def commit(self):
        self.committed = True


def _user(user_id: str, role: str):
    return SimpleNamespace(id=user_id, role=SimpleNamespace(value=role))


def _template(created_by: str):
    return ChecklistTemplate(
        id="template-1",
        nome="Checklist contratual",
        created_by=created_by,
    )


@pytest.mark.asyncio
async def test_advogado_autor_remove_template_por_soft_delete():
    template = _template("adv-autor")
    db = _DB(template)

    await remover_template(
        "template-1",
        db=db,
        cu=_user("adv-autor", "advogado"),
    )

    assert template.deleted_at is not None
    assert db.committed is True
    assert "deleted_at IS NULL" in str(db.statement)


@pytest.mark.asyncio
async def test_advogado_nao_autor_nao_remove_template():
    template = _template("outro-advogado")
    db = _DB(template)

    with pytest.raises(HTTPException) as exc:
        await remover_template(
            "template-1",
            db=db,
            cu=_user("adv-sem-autoria", "advogado"),
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == (
        "Apenas o autor do template ou um sócio pode removê-lo"
    )
    assert template.deleted_at is None
    assert db.committed is False


@pytest.mark.asyncio
async def test_socio_remove_template_de_outro_autor():
    template = _template("adv-autor")
    db = _DB(template)

    await remover_template(
        "template-1",
        db=db,
        cu=_user("socio-1", "socio"),
    )

    assert template.deleted_at is not None
    assert db.committed is True


@pytest.mark.asyncio
async def test_estagiario_permanece_bloqueado_sem_consultar_template():
    db = _DB(_template("estagiario-1"))

    with pytest.raises(HTTPException) as exc:
        await remover_template(
            "template-1",
            db=db,
            cu=_user("estagiario-1", "estagiario"),
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == (
        "Apenas advogado ou perfil superior pode remover templates"
    )
    assert db.statement is None
    assert db.committed is False


@pytest.mark.asyncio
async def test_template_ausente_ou_ja_removido_retorna_404():
    db = _DB(None)

    with pytest.raises(HTTPException) as exc:
        await remover_template(
            "template-inexistente",
            db=db,
            cu=_user("socio-1", "socio"),
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Template não encontrado"
    assert db.committed is False
