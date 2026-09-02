from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from app.models.user import UserRole
from app.routers import checklists, prompts_juridicos


def _u(role: UserRole):
    return SimpleNamespace(role=role)


@pytest.mark.parametrize(
    "role",
    [
        UserRole.superadmin,
        UserRole.admin,
        UserRole.socio,
        UserRole.advogado,
        UserRole.advogado_auxiliar,
        UserRole.estagiario,
    ],
)
def test_checklists_preserva_equipe_juridica(role):
    assert checklists._pode_editar(_u(role)) is True


@pytest.mark.parametrize(
    "role",
    [UserRole.financeiro, UserRole.secretaria, UserRole.cliente_externo],
)
def test_checklists_barra_papeis_fora_da_equipe(role):
    assert checklists._pode_editar(_u(role)) is False


def test_prompts_financeiro_e_secretaria_so_podem_ver_publicos():
    assert prompts_juridicos._so_publicos(_u(UserRole.financeiro)) is True
    assert prompts_juridicos._so_publicos(_u(UserRole.secretaria)) is True


@pytest.mark.parametrize(
    "role",
    [
        UserRole.superadmin,
        UserRole.admin,
        UserRole.socio,
        UserRole.advogado,
        UserRole.advogado_auxiliar,
        UserRole.estagiario,
    ],
)
def test_prompts_equipe_juridica_mantem_visibilidade_privada(role):
    assert prompts_juridicos._so_publicos(_u(role)) is False


def test_detalhe_e_execucao_reusam_o_mesmo_loader_de_visibilidade():
    obter = inspect.getsource(prompts_juridicos.obter_prompt)
    executar = inspect.getsource(prompts_juridicos.executar_prompt)
    assert "_carregar_visivel" in obter
    assert "_carregar_visivel" in executar


def test_loader_privado_aplica_publico_para_papel_nao_juridico():
    fonte = inspect.getsource(prompts_juridicos._carregar_visivel)
    assert "_so_publicos(user)" in fonte
    assert "PromptJuridico.publico.is_(True)" in fonte
    assert "HTTPException(404" in fonte
