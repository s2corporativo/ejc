from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import peca_modos
from app.schemas.peca_workflow import ModoProducao, ProducaoModoRequest


def _user(role: str = "estagiario"):
    return SimpleNamespace(id="user-1", role=SimpleNamespace(value=role))


@pytest.mark.asyncio
async def test_meta_expoe_quatro_modos_e_campos_guiados():
    resposta = await peca_modos.meta_modos(cu=_user())

    assert [modo["value"] for modo in resposta["modos"]] == [
        "livre",
        "guiado",
        "molde",
        "agente",
    ]
    contestacao = next(
        tipo for tipo in resposta["tipos"] if tipo["value"] == "contestacao"
    )
    assert "fatos_impugnados" in contestacao["campos_guiados"]
    assert resposta["endpoint_redacao"] == "/api/pecas/gerar"
    assert resposta["hitl_obrigatorio"] is True


@pytest.mark.asyncio
async def test_meta_recusa_perfil_abaixo_do_piso():
    with pytest.raises(HTTPException) as exc:
        await peca_modos.meta_modos(cu=_user("cliente_externo"))

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_preparar_recusa_tipo_invalido():
    req = ProducaoModoRequest(
        modo=ModoProducao.LIVRE,
        tipo_peca="tipo_inexistente",
        area_direito="civil",
    )

    with pytest.raises(HTTPException) as exc:
        await peca_modos.preparar_modo(req, db=SimpleNamespace(), cu=_user())

    assert exc.value.status_code == 422
    assert "Tipo inválido" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_preparar_recusa_area_invalida():
    req = ProducaoModoRequest(
        modo=ModoProducao.LIVRE,
        tipo_peca="contestacao",
        area_direito="area_inexistente",
    )

    with pytest.raises(HTTPException) as exc:
        await peca_modos.preparar_modo(req, db=SimpleNamespace(), cu=_user())

    assert exc.value.status_code == 422
    assert "Área inválida" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_preparar_valida_acesso_ao_caso_antes_do_plano(monkeypatch):
    chamadas = []

    async def _verificar(db, cu, case_id):
        chamadas.append((db, cu, case_id))

    monkeypatch.setattr(peca_modos, "verificar_acesso_caso", _verificar)
    db = SimpleNamespace()
    cu = _user("advogado")
    req = ProducaoModoRequest(
        modo=ModoProducao.AGENTE,
        case_id="caso-1",
        tipo_peca="contestacao",
        area_direito="civil",
        documentos_considerados=[{"documento_id": "doc-1"}],
        aprovado_para_redacao=False,
    )

    resposta = await peca_modos.preparar_modo(req, db=db, cu=cu)

    assert chamadas == [(db, cu, "caso-1")]
    assert resposta.modo is ModoProducao.AGENTE
    assert resposta.pronto_para_redacao is False
    assert any("aprovadas" in item or "aprovada" in item for item in resposta.bloqueios)


@pytest.mark.asyncio
async def test_preparacao_livre_nao_persiste_nem_chama_ia():
    req = ProducaoModoRequest(
        modo=ModoProducao.LIVRE,
        tipo_peca="contestacao",
        area_direito="civil",
        instrucao_livre="Impugnar especificamente os fatos e manter linguagem objetiva.",
    )

    resposta = await peca_modos.preparar_modo(
        req,
        db=SimpleNamespace(),
        cu=_user(),
    )

    assert resposta.pronto_para_redacao is True
    assert "Impugnar especificamente" in resposta.instrucoes_pipeline
