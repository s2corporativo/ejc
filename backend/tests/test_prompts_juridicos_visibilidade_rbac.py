"""Regressão RBAC da biblioteca de prompts jurídicos (Issue #694)."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from app.models.user import UserRole
from app.routers import prompts_juridicos as prompts


def _user(role: UserRole, uid: str = "u1"):
    return SimpleNamespace(id=uid, role=role)


def test_financeiro_so_recebe_clausula_de_prompt_publico():
    sql = str(prompts._visivel_para(_user(UserRole.financeiro)))
    assert "publico" in sql
    assert "created_by" not in sql


def test_advogado_pode_ver_publico_e_proprio_privado():
    sql = str(prompts._visivel_para(_user(UserRole.advogado)))
    assert "publico" in sql
    assert "created_by" in sql
    assert "IS NULL" not in sql.upper()


def test_socio_pode_recuperar_prompt_orfao_sem_abrir_para_financeiro():
    sql = str(prompts._visivel_para(_user(UserRole.socio)))
    assert "publico" in sql
    assert "created_by" in sql
    assert "IS NULL" in sql.upper()


def test_listagem_nao_usa_piso_hierarquico_de_estagiario():
    fonte = inspect.getsource(prompts.listar_prompts)
    assert "ROLE_LEVEL" not in fonte
    assert "_visivel_para(cu)" in fonte
