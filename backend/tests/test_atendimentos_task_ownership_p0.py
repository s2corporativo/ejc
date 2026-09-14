"""Regressões P0 de ownership no fluxo Atendimento -> Task."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
from fastapi import HTTPException

from app.models.atendimento import Atendimento, AtendimentoTipo
from app.models.task import Task, TaskStatus
from app.routers import atendimentos as router


def _user(uid: str, role: str = "advogado"):
    return SimpleNamespace(id=uid, role=SimpleNamespace(value=role))


def _atendimento(**overrides):
    data = dict(
        id="at-1",
        client_id="client-1",
        case_id="case-1",
        tipo=AtendimentoTipo.whatsapp,
        data_atendimento=datetime.now(timezone.utc),
        resumo="Resumo sintético do atendimento para teste.",
        solicitacao="Providenciar retorno ao cliente sobre o processo.",
        solicitacao_atendida=False,
        solicitacao_prazo=None,
        solicitacao_prioridade="normal",
        solicitacao_responsavel_id="adv-1",
        task_id="task-1",
        contato_status="confirmado",
        advogado_responsavel_id="adv-1",
        created_by="adv-1",
    )
    data.update(overrides)
    return Atendimento(**data)


class _FakeDB:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        del obj


@pytest.mark.asyncio
async def test_gate_case_scoped_aceita_responsavel_com_acesso(monkeypatch):
    acesso = AsyncMock(return_value=SimpleNamespace(id="case-1"))
    monkeypatch.setattr(router, "verificar_acesso_caso", acesso)
    alvo = _user("adv-2")

    await router._validar_responsavel_tarefa_no_caso(object(), alvo, "case-1")

    acesso.assert_awaited_once_with(ANY, alvo, "case-1")


@pytest.mark.asyncio
async def test_gate_case_scoped_rejeita_sem_vazar_detalhes(monkeypatch):
    acesso = AsyncMock(
        side_effect=HTTPException(status_code=403, detail="Sem permissão para este caso")
    )
    monkeypatch.setattr(router, "verificar_acesso_caso", acesso)

    with pytest.raises(HTTPException) as exc:
        await router._validar_responsavel_tarefa_no_caso(
            object(), _user("adv-fora"), "case-secreto"
        )

    assert exc.value.status_code == 422
    assert exc.value.detail == "Responsável da solicitação sem acesso ao caso"
    assert "case-secreto" not in str(exc.value.detail)


@pytest.mark.asyncio
async def test_criacao_task_valida_aplica_gate_case_scoped(monkeypatch):
    db = _FakeDB()
    cu = _user("adv-1")
    alvo = _user("adv-2")

    monkeypatch.setattr(router, "_validar_cliente", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        router,
        "verificar_acesso_caso",
        AsyncMock(return_value=SimpleNamespace(client_id="client-1")),
    )

    async def validar_responsavel(_db, uid):
        return alvo if uid == "adv-2" else cu

    monkeypatch.setattr(router, "_validar_responsavel", validar_responsavel)
    gate = AsyncMock(return_value=None)
    monkeypatch.setattr(router, "_validar_responsavel_tarefa_no_caso", gate)
    monkeypatch.setattr(router, "_notificar_nova_solicitacao", AsyncMock())
    monkeypatch.setattr(router, "registrar_acao", AsyncMock())

    req = router.AtendimentoIn(
        client_id="client-1",
        case_id="case-1",
        tipo=AtendimentoTipo.whatsapp,
        data_atendimento=datetime.now(timezone.utc),
        resumo="Resumo sintético do atendimento para teste.",
        solicitacao="Providenciar retorno ao cliente sobre o processo.",
        solicitacao_responsavel_id="adv-2",
        advogado_responsavel_id="adv-1",
        criar_tarefa=True,
    )

    await router.criar_atendimento(req, db=db, cu=cu)

    gate.assert_awaited_once_with(db, alvo, "case-1")
    tarefas = [obj for obj in db.added if isinstance(obj, Task)]
    assert len(tarefas) == 1
    assert tarefas[0].responsavel_id == "adv-2"
    assert tarefas[0].case_id == "case-1"


@pytest.mark.asyncio
async def test_criacao_task_rejeita_responsavel_fora_do_caso_antes_de_persistir(monkeypatch):
    db = _FakeDB()
    cu = _user("adv-1")
    alvo = _user("adv-fora")

    monkeypatch.setattr(router, "_validar_cliente", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        router,
        "verificar_acesso_caso",
        AsyncMock(return_value=SimpleNamespace(client_id="client-1")),
    )

    async def validar_responsavel(_db, uid):
        return alvo if uid == "adv-fora" else cu

    monkeypatch.setattr(router, "_validar_responsavel", validar_responsavel)
    monkeypatch.setattr(
        router,
        "_validar_responsavel_tarefa_no_caso",
        AsyncMock(
            side_effect=HTTPException(
                status_code=422,
                detail="Responsável da solicitação sem acesso ao caso",
            )
        ),
    )

    req = router.AtendimentoIn(
        client_id="client-1",
        case_id="case-1",
        tipo=AtendimentoTipo.whatsapp,
        data_atendimento=datetime.now(timezone.utc),
        resumo="Resumo sintético do atendimento para teste.",
        solicitacao="Providenciar retorno ao cliente sobre o processo.",
        solicitacao_responsavel_id="adv-fora",
        advogado_responsavel_id="adv-1",
        criar_tarefa=True,
    )

    with pytest.raises(HTTPException) as exc:
        await router.criar_atendimento(req, db=db, cu=cu)

    assert exc.value.status_code == 422
    assert db.added == []
    assert db.commits == 0


@pytest.mark.asyncio
async def test_patch_responsavel_fora_do_caso_falha_antes_de_mutar_task(monkeypatch):
    db = _FakeDB()
    cu = _user("adv-1")
    atendimento = _atendimento(
        solicitacao_responsavel_id="adv-1", created_by="adv-1"
    )
    tarefa = SimpleNamespace(
        titulo="Título anterior",
        descricao="Descrição anterior",
        prioridade="media",
        data_limite=None,
        case_id="case-1",
        responsavel_id="adv-1",
        status=TaskStatus.a_fazer,
        concluida_em=None,
    )
    alvo = _user("adv-fora")

    monkeypatch.setattr(router, "_obter_atendimento", AsyncMock(return_value=atendimento))
    monkeypatch.setattr(router, "_obter_tarefa_vinculada", AsyncMock(return_value=tarefa))
    monkeypatch.setattr(
        router,
        "verificar_acesso_caso",
        AsyncMock(return_value=SimpleNamespace(id="case-1")),
    )
    monkeypatch.setattr(router, "_validar_responsavel", AsyncMock(return_value=alvo))
    monkeypatch.setattr(
        router,
        "_validar_responsavel_tarefa_no_caso",
        AsyncMock(
            side_effect=HTTPException(
                status_code=422,
                detail="Responsável da solicitação sem acesso ao caso",
            )
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await router.atualizar_atendimento(
            atendimento.id,
            router.AtendimentoPatch(solicitacao_responsavel_id="adv-fora"),
            db=db,
            cu=cu,
        )

    assert exc.value.status_code == 422
    assert tarefa.responsavel_id == "adv-1"
    assert tarefa.titulo == "Título anterior"
    assert db.commits == 0


@pytest.mark.asyncio
async def test_patch_task_vinculada_rejeita_editor_sem_acesso_atual_antes_de_desatribuir(monkeypatch):
    db = _FakeDB()
    cu = _user("adv-antigo")
    atendimento = _atendimento(
        solicitacao_responsavel_id="adv-1",
        created_by="adv-antigo",
        advogado_responsavel_id="adv-antigo",
    )
    tarefa = SimpleNamespace(responsavel_id="adv-1")

    monkeypatch.setattr(router, "_obter_atendimento", AsyncMock(return_value=atendimento))
    monkeypatch.setattr(router, "_obter_tarefa_vinculada", AsyncMock(return_value=tarefa))
    acesso = AsyncMock(
        side_effect=HTTPException(status_code=403, detail="Sem permissão para este caso")
    )
    monkeypatch.setattr(router, "verificar_acesso_caso", acesso)

    with pytest.raises(HTTPException) as exc:
        await router.atualizar_atendimento(
            atendimento.id,
            router.AtendimentoPatch(solicitacao_responsavel_id=None),
            db=db,
            cu=cu,
        )

    assert exc.value.status_code == 422
    assert exc.value.detail == "Sem acesso ao caso vinculado à tarefa"
    acesso.assert_awaited_once_with(db, cu, "case-1")
    assert atendimento.solicitacao_responsavel_id == "adv-1"
    assert tarefa.responsavel_id == "adv-1"
    assert db.commits == 0


@pytest.mark.asyncio
async def test_patch_task_vinculada_permite_editor_com_acesso_atual(monkeypatch):
    db = _FakeDB()
    cu = _user("adv-1")
    atendimento = _atendimento(created_by="adv-1")

    monkeypatch.setattr(router, "_obter_atendimento", AsyncMock(return_value=atendimento))
    acesso = AsyncMock(return_value=SimpleNamespace(id="case-1"))
    monkeypatch.setattr(router, "verificar_acesso_caso", acesso)
    monkeypatch.setattr(router, "_sincronizar_tarefa", AsyncMock())
    monkeypatch.setattr(router, "_notificar_nova_solicitacao", AsyncMock())
    monkeypatch.setattr(router, "registrar_acao", AsyncMock())

    await router.atualizar_atendimento(
        atendimento.id,
        router.AtendimentoPatch(resumo="Resumo atualizado com acesso ao caso."),
        db=db,
        cu=cu,
    )

    acesso.assert_awaited_once_with(db, cu, "case-1")
    assert atendimento.resumo == "Resumo atualizado com acesso ao caso."
    assert db.commits == 1
