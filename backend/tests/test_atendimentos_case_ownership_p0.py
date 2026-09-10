"""P0: solicitação/tarefa de atendimento não pode conceder acesso a caso."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.atendimento import Atendimento, AtendimentoTipo
from app.models.user import User, UserRole
from app.routers import atendimentos
from app.routers.atendimentos import AtendimentoIn, AtendimentoPatch


def _user(uid: str, role: UserRole = UserRole.advogado) -> User:
    return User(id=uid, role=role, is_active=True)


def _caso():
    return SimpleNamespace(
        id="case-1",
        client_id="client-1",
        advogado_responsavel_id="adv-dono",
        advogado_auxiliar_id="adv-aux",
    )


def test_responsavel_de_solicitacao_precisa_ter_acesso_real_ao_caso():
    caso = _caso()
    atendimentos._validar_responsavel_no_caso(_user("adv-dono"), caso)
    atendimentos._validar_responsavel_no_caso(_user("adv-aux"), caso)
    atendimentos._validar_responsavel_no_caso(_user("gestao", UserRole.socio), caso)

    with pytest.raises(HTTPException) as exc:
        atendimentos._validar_responsavel_no_caso(_user("adv-fora"), caso)
    assert exc.value.status_code == 422
    assert "sem acesso ao caso" in exc.value.detail


def test_listagem_com_caso_filtra_pela_carteira_do_proprio_caso():
    q = atendimentos._filtro_visibilidade_atendimento(
        select(Atendimento), _user("adv-dono")
    )
    sql = str(q).lower()

    assert "atendimentos.case_id" in sql
    assert "cases.advogado_responsavel_id" in sql
    assert "cases.advogado_auxiliar_id" in sql
    assert "atendimentos.case_id is null" in sql



@pytest.mark.asyncio
async def test_ser_responsavel_da_solicitacao_nao_abre_caso_alheio(monkeypatch):
    atendimento = SimpleNamespace(
        case_id="case-1",
        client_id="client-1",
        created_by="outro",
        advogado_responsavel_id="outro",
        solicitacao_responsavel_id="adv-fora",
    )

    async def _nega_caso(_db, _cu, _case_id):
        raise HTTPException(status_code=403, detail="caso fora da carteira")

    monkeypatch.setattr(atendimentos, "verificar_acesso_caso", _nega_caso)

    assert await atendimentos._pode_ver_atendimento(
        object(), _user("adv-fora"), atendimento
    ) is False


@pytest.mark.asyncio
async def test_criacao_bloqueia_tarefa_de_caso_para_destinatario_sem_carteira(monkeypatch):
    caso = _caso()
    criador = _user("adv-dono")
    alvo = _user("adv-fora")

    async def _validar_cliente(_db, _client_id):
        return SimpleNamespace(id="client-1")

    async def _acesso_caso(_db, _cu, _case_id):
        return caso

    async def _responsavel(_db, uid):
        if uid == alvo.id:
            return alvo
        if uid == criador.id:
            return criador
        return None

    monkeypatch.setattr(atendimentos, "_validar_cliente", _validar_cliente)
    monkeypatch.setattr(atendimentos, "verificar_acesso_caso", _acesso_caso)
    monkeypatch.setattr(atendimentos, "_validar_responsavel", _responsavel)

    req = AtendimentoIn(
        client_id="client-1",
        case_id="case-1",
        tipo=AtendimentoTipo.email,
        data_atendimento=datetime.now(timezone.utc),
        resumo="Atendimento registrado para teste de ownership.",
        solicitacao="Preparar retorno ao cliente.",
        solicitacao_responsavel_id="adv-fora",
        criar_tarefa=True,
    )

    with pytest.raises(HTTPException) as exc:
        await atendimentos.criar_atendimento(req, db=object(), cu=criador)
    assert exc.value.status_code == 422
    assert "sem acesso ao caso" in exc.value.detail


@pytest.mark.asyncio
async def test_patch_bloqueia_reatribuicao_da_solicitacao_para_usuario_fora_do_caso(monkeypatch):
    caso = _caso()
    atendimento = SimpleNamespace(
        id="at-1",
        case_id="case-1",
        client_id="client-1",
        created_by="adv-dono",
        advogado_responsavel_id="adv-dono",
        solicitacao_responsavel_id="adv-dono",
    )
    alvo = _user("adv-fora")

    async def _obter(_id, _db):
        return atendimento

    async def _pode_ver(_db, _cu, _a):
        return True

    async def _responsavel(_db, _uid):
        return alvo

    class _Result:
        def scalar_one_or_none(self):
            return caso

    class _DB:
        async def execute(self, _stmt):
            return _Result()

    monkeypatch.setattr(atendimentos, "_obter_atendimento", _obter)
    monkeypatch.setattr(atendimentos, "_pode_ver_atendimento", _pode_ver)
    monkeypatch.setattr(atendimentos, "_pode_editar_atendimento", lambda _a, _u: True)
    monkeypatch.setattr(atendimentos, "_validar_responsavel", _responsavel)

    with pytest.raises(HTTPException) as exc:
        await atendimentos.atualizar_atendimento(
            "at-1",
            AtendimentoPatch(solicitacao_responsavel_id="adv-fora"),
            db=_DB(),
            cu=_user("adv-dono"),
        )
    assert exc.value.status_code == 422
    assert "sem acesso ao caso" in exc.value.detail
