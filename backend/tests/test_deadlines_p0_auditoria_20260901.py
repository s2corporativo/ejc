"""Regressões P0/P1 da auditoria Agenda e Prazos de 2026-09-01.

Cobertura deliberadamente sem banco para rodar no gate rápido; os testes dblevel
continuam responsáveis pela integração PostgreSQL nos fluxos já existentes.
"""
from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.deadline import Deadline
from app.models.user import User, UserRole
from app.routers import deadlines


def _user(user_id: str, role: UserRole) -> User:
    return User(id=user_id, role=role)


def test_status_all_e_vazio_significam_sem_filtro():
    assert deadlines._normalizar_status_filtro(None) is None
    assert deadlines._normalizar_status_filtro("") is None
    assert deadlines._normalizar_status_filtro("  ALL  ") is None
    assert deadlines._normalizar_status_filtro("pendente") == "pendente"


def test_status_desconhecido_falha_antes_do_postgres():
    with pytest.raises(HTTPException) as exc:
        deadlines._normalizar_status_filtro("qualquer-coisa")
    assert exc.value.status_code == 422
    assert "status inválido" in str(exc.value.detail)


def test_regime_processual_nao_e_mais_presumido_como_civel():
    with pytest.raises(HTTPException) as exc:
        deadlines._resolver_regime_processual(None, True)
    assert exc.value.status_code == 422
    assert "regime_calculo" in str(exc.value.detail)

    assert deadlines._resolver_regime_processual("civel", True) == ("civel", False)
    assert deadlines._resolver_regime_processual("trabalhista", True) == (
        "trabalhista",
        False,
    )
    assert deadlines._resolver_regime_processual("penal", False) == ("penal", False)


def test_filtro_nao_gestao_nao_libera_todo_prazo_avulso():
    cu = _user("adv-1", UserRole.advogado)
    q = deadlines._filtro_escopo_prazos(select(Deadline), cu)
    sql = str(q.compile(compile_kwargs={"literal_binds": True}))

    assert "deadlines.responsavel_id = 'adv-1'" in sql
    # Anti-vácuo do AP-06: a versão vulnerável tinha OR case_id IS NULL.
    assert "deadlines.case_id IS NULL" not in sql


def test_filtro_gestao_preserva_visao_global():
    cu = _user("socio-1", UserRole.socio)
    original = select(Deadline)
    filtrado = deadlines._filtro_escopo_prazos(original, cu)
    assert str(filtrado) == str(original)


@pytest.mark.asyncio
async def test_prazo_avulso_de_outro_usuario_retorna_404_sem_enumerar():
    cu = _user("adv-1", UserRole.advogado)
    prazo = Deadline(id="prazo-1", titulo="Teste", responsavel_id="adv-2")

    with pytest.raises(HTTPException) as exc:
        await deadlines._verificar_acesso_prazo(None, cu, prazo)  # type: ignore[arg-type]
    assert exc.value.status_code == 404
    assert exc.value.detail == "Prazo não encontrado"


@pytest.mark.asyncio
async def test_responsavel_do_prazo_avulso_mantem_acesso():
    cu = _user("adv-1", UserRole.advogado)
    prazo = Deadline(id="prazo-1", titulo="Teste", responsavel_id="adv-1")
    await deadlines._verificar_acesso_prazo(None, cu, prazo)  # type: ignore[arg-type]


def test_patch_material_reseta_tres_flags_de_alerta():
    """Trava estrutural AP-09/10 até a cobertura dblevel da homologação H06."""
    fonte = inspect.getsource(deadlines.atualizar)
    assert "mudou_data =" in fonte
    assert "mudou_responsavel =" in fonte
    assert "d.alerta_7d_enviado = False" in fonte
    assert "d.alerta_3d_enviado = False" in fonte
    assert "d.alerta_1d_enviado = False" in fonte
    assert "PRAZO_ALERTAS_REINICIADOS" in fonte


def test_responsavel_elegivel_nao_inclui_financeiro_ou_cliente():
    assert UserRole.financeiro not in deadlines._ROLES_RESPONSAVEIS
    assert UserRole.cliente_externo not in deadlines._ROLES_RESPONSAVEIS
    assert UserRole.advogado in deadlines._ROLES_RESPONSAVEIS
    assert UserRole.advogado_auxiliar in deadlines._ROLES_RESPONSAVEIS
