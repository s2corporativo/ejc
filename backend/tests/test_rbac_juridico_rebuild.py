"""Regressões específicas do rebuild RBAC jurídico sobre a main atual."""
from __future__ import annotations

import ast
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.user import UserRole


def _u(role: UserRole):
    return SimpleNamespace(id="u-test", role=role)


@pytest.mark.asyncio
async def test_bank_analysis_gerar_peca_barra_financeiro_antes_do_db():
    from app.routers import bank_analysis

    with pytest.raises(HTTPException) as exc:
        await bank_analysis.gerar_peca(
            analysis_id="analysis-test",
            payload=None,
            db=None,
            cu=_u(UserRole.financeiro),
        )
    assert exc.value.status_code == 403
    assert "equipe jurídica" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_bank_analysis_documento_barra_financeiro_antes_do_db():
    from app.routers import bank_analysis

    with pytest.raises(HTTPException) as exc:
        await bank_analysis.documento(
            analysis_id="analysis-test",
            payload={"tipo": "peticao"},
            db=None,
            cu=_u(UserRole.financeiro),
        )
    assert exc.value.status_code == 403
    assert "equipe jurídica" in str(exc.value.detail).lower()


def test_bank_analysis_nao_reintroduz_piso_hierarquico_em_gerar_peca():
    from app.routers import bank_analysis

    fonte = inspect.getsource(bank_analysis.gerar_peca)
    assert "requer_equipe_juridica" in fonte
    assert "ROLE_LEVEL" not in fonte


def test_checklists_e_entrada_nao_reintroduzem_piso_por_nivel():
    from app.routers import checklists, entrada_universal

    fonte_ck = inspect.getsource(checklists._pode_editar)
    assert "EQUIPE_JURIDICA" in fonte_ck
    assert "ROLE_LEVEL" not in fonte_ck

    for funcao in (entrada_universal.meta, entrada_universal.processar):
        fonte = inspect.getsource(funcao)
        assert "requer_equipe_juridica" in fonte
        tree = ast.parse(fonte)
        nomes = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "ROLE_LEVEL" not in nomes
