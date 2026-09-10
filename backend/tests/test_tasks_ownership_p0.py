"""Regressões P0 de ownership para tarefas internas."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.case import Case
from app.models.task import Task
from app.routers import tasks as tasks_router


def _user(role: str = "advogado", uid: str = "u1"):
    return SimpleNamespace(id=uid, role=SimpleNamespace(value=role))


def test_listagem_nao_expoe_toda_tarefa_sem_caso_ou_caso_orfao():
    user = _user()
    q = select(Task).where(Task.deleted_at.is_(None))
    q = q.where(
        tasks_router.or_(
            Task.case_id.in_(tasks_router._ids_casos_do_usuario(user)),
            tasks_router.and_(
                Task.case_id.is_(None),
                tasks_router.or_(
                    Task.responsavel_id == user.id,
                    Task.criado_por == user.id,
                ),
            ),
        )
    )
    sql = str(q)

    assert "tasks.case_id IS NULL" in sql
    assert "tasks.responsavel_id" in sql
    assert "tasks.criado_por" in sql
    assert "cases.advogado_responsavel_id IS NULL" not in sql
    assert "cases.advogado_auxiliar_id IS NULL" not in sql


@pytest.mark.anyio
async def test_tarefa_avulsa_de_terceiro_falha_fechado():
    tarefa = SimpleNamespace(case_id=None, responsavel_id="u2", criado_por="u3")

    with pytest.raises(HTTPException) as exc:
        await tasks_router._verificar_acesso_tarefa(None, _user(uid="u1"), tarefa)

    assert exc.value.status_code == 403


@pytest.mark.anyio
async def test_tarefa_avulsa_do_responsavel_e_permitida():
    tarefa = SimpleNamespace(case_id=None, responsavel_id="u1", criado_por="u3")

    assert await tasks_router._verificar_acesso_tarefa(None, _user(uid="u1"), tarefa) is None


def test_mutacoes_reusam_gate_unico():
    source_update = inspect.getsource(tasks_router.atualizar)
    source_delete = inspect.getsource(tasks_router.remover)

    assert "_verificar_acesso_tarefa" in source_update
    assert "_verificar_acesso_tarefa" in source_delete


def test_listagem_nao_contem_escape_hatch_de_caso_orfao():
    source = inspect.getsource(tasks_router.listar)

    assert "advogado_responsavel_id.is_(None)" not in source
    assert "advogado_auxiliar_id.is_(None)" not in source
    assert "Task.case_id.is_(None)" in source
    assert "Task.responsavel_id == cu.id" in source
    assert "Task.criado_por == cu.id" in source


def test_responsavel_de_caso_precisa_ter_acesso_ao_caso():
    caso = SimpleNamespace(
        advogado_responsavel_id="adv1",
        advogado_auxiliar_id="adv2",
    )
    alvo_ok = _user(uid="adv2")
    alvo_fora = _user(uid="adv3")
    gestor = _user(role="socio", uid="socio1")

    assert tasks_router._responsavel_pode_acessar_caso(alvo_ok, caso) is True
    assert tasks_router._responsavel_pode_acessar_caso(gestor, caso) is True
    assert tasks_router._responsavel_pode_acessar_caso(alvo_fora, caso) is False


def test_notificacao_aponta_para_central_canonica():
    source = inspect.getsource(tasks_router.criar)

    assert 'link="/atividades?tipo=tarefa"' in source
