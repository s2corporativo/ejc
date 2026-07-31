"""Regressão de autorização na remoção de prompts jurídicos."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.prompt_juridico import PromptJuridico
from app.routers.prompts_juridicos import remover_prompt


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


def _prompt(created_by: str):
    return PromptJuridico(
        id="prompt-1",
        titulo="Análise contratual",
        conteudo="Analise o contrato informado e sinalize pontos de revisão.",
        created_by=created_by,
    )


@pytest.mark.asyncio
async def test_advogado_autor_remove_prompt_por_soft_delete():
    prompt = _prompt("adv-autor")
    db = _DB(prompt)

    await remover_prompt(
        "prompt-1",
        db=db,
        cu=_user("adv-autor", "advogado"),
    )

    assert prompt.deleted_at is not None
    assert db.committed is True
    assert "deleted_at IS NULL" in str(db.statement)


@pytest.mark.asyncio
async def test_advogado_nao_autor_nao_remove_prompt():
    prompt = _prompt("outro-advogado")
    db = _DB(prompt)

    with pytest.raises(HTTPException) as exc:
        await remover_prompt(
            "prompt-1",
            db=db,
            cu=_user("adv-sem-autoria", "advogado"),
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == (
        "Apenas o autor do prompt ou um sócio pode removê-lo"
    )
    assert prompt.deleted_at is None
    assert db.committed is False


@pytest.mark.asyncio
async def test_socio_remove_prompt_de_outro_autor():
    prompt = _prompt("adv-autor")
    db = _DB(prompt)

    await remover_prompt(
        "prompt-1",
        db=db,
        cu=_user("socio-1", "socio"),
    )

    assert prompt.deleted_at is not None
    assert db.committed is True


@pytest.mark.asyncio
async def test_estagiario_permanece_bloqueado_sem_consultar_prompt():
    db = _DB(_prompt("estagiario-1"))

    with pytest.raises(HTTPException) as exc:
        await remover_prompt(
            "prompt-1",
            db=db,
            cu=_user("estagiario-1", "estagiario"),
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == (
        "Apenas advogado ou perfil superior pode remover prompts"
    )
    assert db.statement is None
    assert db.committed is False


@pytest.mark.asyncio
async def test_prompt_ausente_ou_ja_removido_retorna_404():
    db = _DB(None)

    with pytest.raises(HTTPException) as exc:
        await remover_prompt(
            "prompt-inexistente",
            db=db,
            cu=_user("socio-1", "socio"),
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Prompt não encontrado"
    assert db.committed is False
