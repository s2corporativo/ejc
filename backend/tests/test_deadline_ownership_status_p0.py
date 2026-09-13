"""Regressões AP-06/AP-07/AP-11 da Central de Prazos."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.deadline import Deadline
from app.routers import deadlines


def _user(user_id: str = "u1", role: str = "advogado"):
    return SimpleNamespace(id=user_id, role=role)


def test_status_all_e_normalizado_antes_do_enum_postgres():
    assert deadlines._normalizar_status_filtro(None) is None
    assert deadlines._normalizar_status_filtro("") is None
    assert deadlines._normalizar_status_filtro("all") is None
    assert deadlines._normalizar_status_filtro(" ALL ") is None
    assert deadlines._normalizar_status_filtro("PENDENTE") == "pendente"

    with pytest.raises(HTTPException) as exc:
        deadlines._normalizar_status_filtro("qualquer")
    assert exc.value.status_code == 422


def test_prazo_avulso_nao_fica_visivel_para_todo_usuario_interno():
    query = deadlines._filtro_escopo_prazos(select(Deadline), _user())
    sql = str(query).lower()

    assert "deadlines.responsavel_id" in sql
    assert "deadlines.case_id is null" not in sql


@pytest.mark.asyncio
async def test_prazo_avulso_so_responsavel_ou_gestao_pode_acessar():
    prazo_alheio = SimpleNamespace(case_id=None, responsavel_id="u2")
    with pytest.raises(HTTPException) as exc:
        await deadlines._verificar_acesso_prazo(object(), _user("u1"), prazo_alheio)
    # Consolidado com #1412: 404 anti-enumeração (README §Segurança).
    assert exc.value.status_code == 404

    prazo_proprio = SimpleNamespace(case_id=None, responsavel_id="u1")
    await deadlines._verificar_acesso_prazo(object(), _user("u1"), prazo_proprio)
    await deadlines._verificar_acesso_prazo(
        object(), _user("gestao", "socio"), prazo_alheio
    )


@pytest.mark.asyncio
async def test_nao_gestao_nao_pode_atribuir_prazo_a_terceiro_sem_oraculo():
    class DBQueNaoPodeSerConsultado:
        async def execute(self, _query):
            raise AssertionError("não deve consultar usuário antes do gate de gestão")

    with pytest.raises(HTTPException) as exc:
        await deadlines._validar_responsavel_prazo(
            DBQueNaoPodeSerConsultado(), _user("u1"), "u2"
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_gestao_nao_pode_atribuir_prazo_interno_a_cliente_externo():
    class Resultado:
        def scalar_one_or_none(self):
            return _user("cliente", "cliente_externo")

    class DB:
        async def execute(self, _query):
            return Resultado()

    with pytest.raises(HTTPException) as exc:
        await deadlines._validar_responsavel_prazo(
            DB(), _user("gestao", "socio"), "cliente", case_id="caso-1"
        )
    assert exc.value.status_code == 422
    assert "cliente externo" in exc.value.detail


@pytest.mark.asyncio
async def test_atribuicao_de_prazo_de_caso_revalida_acesso_do_alvo(monkeypatch):
    alvo = _user("u2", "advogado")

    class Resultado:
        def scalar_one_or_none(self):
            return alvo

    class DB:
        async def execute(self, _query):
            return Resultado()

    chamados = []

    async def acesso(_db, user, case_id):
        chamados.append((user.id, case_id))
        raise HTTPException(status_code=403, detail="caso fora da carteira")

    monkeypatch.setattr(deadlines, "verificar_acesso_caso", acesso)

    with pytest.raises(HTTPException) as exc:
        await deadlines._validar_responsavel_prazo(
            DB(), _user("gestao", "socio"), "u2", case_id="caso-1"
        )
    assert exc.value.status_code == 422
    assert chamados == [("u2", "caso-1")]


def test_criacao_e_patch_passam_case_id_ao_gate_do_responsavel():
    fonte_criar = inspect.getsource(deadlines.criar)
    fonte_atualizar = inspect.getsource(deadlines.atualizar)

    assert "case_id=payload.case_id" in fonte_criar
    assert "case_id=d.case_id" in fonte_atualizar


def test_mutacoes_usam_gate_unico_de_ownership():
    for handler in (
        deadlines.atualizar,
        deadlines.confirmar,
        deadlines.confirmar_ciencia,
        deadlines.cancelar,
    ):
        fonte = inspect.getsource(handler)
        assert "_verificar_acesso_prazo" in fonte, handler.__name__


def test_listagem_e_csv_usam_normalizacao_unica_de_status():
    assert "_normalizar_status_filtro" in inspect.getsource(deadlines.listar)
    assert "_normalizar_status_filtro" in inspect.getsource(deadlines.exportar_csv)
