from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole
from app.routers import ai, rag
from app.schemas.ai import VerificarCitacoesRequest


def _u(role: UserRole, uid: str = "u-inteligencia") -> User:
    return User(id=uid, role=role, full_name="Usuário de teste")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [UserRole.financeiro, UserRole.secretaria, UserRole.cliente_externo],
)
async def test_pesquisa_rag_barra_perfil_fora_da_equipe_juridica(role):
    with pytest.raises(HTTPException) as exc:
        await rag.buscar(
            q="dano moral",
            limite=6,
            categorias=None,
            incluir_historico=False,
            db=None,
            cu=_u(role),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [UserRole.financeiro, UserRole.secretaria, UserRole.cliente_externo],
)
async def test_verificador_citacoes_barra_perfil_fora_da_equipe_juridica(role):
    req = VerificarCitacoesRequest(
        texto="Conforme Súmula 1 do STJ.",
        consultar_datajud=False,
    )
    with pytest.raises(HTTPException) as exc:
        await ai.verificar_citacoes_juris(req=req, db=None, cu=_u(role))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_pesquisa_rag_advogado_continua_autorizado(monkeypatch):
    async def _buscar(*args, **kwargs):
        return []

    monkeypatch.setattr(rag, "buscar_contexto_rag", _buscar)
    monkeypatch.setattr(rag, "emb_disponivel", lambda: False)

    result = await rag.buscar(
        q="dano moral",
        limite=6,
        categorias=None,
        incluir_historico=False,
        db=None,
        cu=_u(UserRole.advogado),
    )
    assert result["pipeline"] == "hibrida_governada"
    assert result["resultados"] == []


@pytest.mark.asyncio
async def test_verificador_citacoes_advogado_continua_autorizado(monkeypatch):
    from app.services import verificador_jurisprudencia

    async def _verificar(*args, **kwargs):
        return {
            "total": 0,
            "confirmadas": 0,
            "nao_encontradas": 0,
            "citacoes": [],
            "aviso": "teste",
            "score": None,
            "avisos": [],
        }

    monkeypatch.setattr(
        verificador_jurisprudencia,
        "verificar_jurisprudencia",
        _verificar,
    )
    req = VerificarCitacoesRequest(
        texto="Sem citação estruturada.",
        consultar_datajud=False,
    )
    result = await ai.verificar_citacoes_juris(
        req=req,
        db=None,
        cu=_u(UserRole.advogado),
    )
    assert result["total"] == 0
