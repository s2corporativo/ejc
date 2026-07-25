"""Integração dos modos controlados no endpoint canônico /pecas/gerar.

Os bloqueios de preparar_modo_producao viram 409 ANTES de abrir o stream
(sem IA, sem banco — geração avulsa não toca db no caminho bloqueado).
Contrato do frontend: o modal envia `modo_producao` estruturado e não usa
mais tags [modo_producao=...] dentro do prompt.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.routers import peca_geracao


def _app() -> TestClient:
    app = FastAPI()
    app.include_router(peca_geracao.router)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="u1", role=SimpleNamespace(value="advogado")
    )
    return TestClient(app)


_BASE = {
    "tipo_peca": "contestacao",
    "area_direito": "civil",
    "descricao_fatos": "F" * 60,
    "pedidos": "Pedido de improcedência dos pedidos autorais.",
}


def test_agente_sem_aprovacao_do_plano_e_409():
    resp = _app().post("/pecas/gerar", json={
        **_BASE,
        "modo_producao": {
            "modo": "agente",
            "tipo_peca": "contestacao",
            "area_direito": "civil",
            "aprovado_para_redacao": False,
        },
    })
    assert resp.status_code == 409
    corpo = resp.json()["detail"]
    assert corpo["modo"] == "agente"
    assert corpo["bloqueios"]


def test_molde_sem_versao_e_hash_e_409():
    resp = _app().post("/pecas/gerar", json={
        **_BASE,
        "modo_producao": {
            "modo": "molde",
            "tipo_peca": "contestacao",
            "area_direito": "civil",
            "molde": {"referencia": {"documento_id": "doc-1"}},
        },
    })
    assert resp.status_code == 409
    assert resp.json()["detail"]["bloqueios"]


def test_molde_campo_preservado_e_substituido_e_409():
    resp = _app().post("/pecas/gerar", json={
        **_BASE,
        "modo_producao": {
            "modo": "molde",
            "tipo_peca": "contestacao",
            "area_direito": "civil",
            "molde": {
                "referencia": {
                    "documento_id": "doc-1",
                    "versao": 2,
                    "hash_conteudo": "abc123def456",
                },
                "preservar": ["estilo"],
                "substituir": ["estilo"],
            },
        },
    })
    assert resp.status_code == 409
    assert resp.json()["detail"]["bloqueios"]


def test_guiado_com_campos_obrigatorios_vazios_e_409():
    resp = _app().post("/pecas/gerar", json={
        **_BASE,
        "modo_producao": {
            "modo": "guiado",
            "tipo_peca": "contestacao",
            "area_direito": "civil",
            "respostas_guiadas": {},
        },
    })
    assert resp.status_code == 409
    assert resp.json()["detail"]["bloqueios"]


def test_contrato_frontend_envia_modo_estruturado():
    fonte = (
        Path(__file__).resolve().parents[2]
        / "frontend" / "src" / "components" / "PecaGeneratorModal.tsx"
    ).read_text(encoding="utf-8")
    assert "modo_producao: modoProducao" in fonte
    assert "[modo_producao=" not in fonte          # fim das tags no prompt
    assert "aprovado_para_redacao" in fonte
    assert "bloqueios" in fonte                    # trata o 409 do contrato
