"""Testes de integração HTTP para o router /pecas/modos."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserRole
from app.routers import peca_modos

# ── Helpers ──────────────────────────────────────────────────────────────────


class _FakeUser:
    id = "user-teste-modos"
    role = UserRole.advogado
    full_name = "Advogado Teste"


class _FakeEstagiario:
    id = "user-estag"
    role = UserRole.estagiario
    full_name = "Estagiario Teste"


class _FakeClienteExterno:
    id = "user-cliente"
    role = UserRole.cliente_externo
    full_name = "Cliente Teste"


async def _fake_db():
    yield None


def _montar(user=None):
    app = FastAPI()
    app.include_router(peca_modos.router)
    app.dependency_overrides[get_current_user] = lambda: (user or _FakeUser())
    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


# ── GET /meta ────────────────────────────────────────────────────────────────


def test_meta_retorna_modos_e_tipos():
    cli = _montar()
    r = cli.get("/pecas/modos/meta")
    assert r.status_code == 200
    body = r.json()
    assert "modos" in body
    assert len(body["modos"]) == 4
    assert body["hitl_obrigatorio"] is True
    assert body["endpoint_redacao"] == "/api/pecas/gerar"


def test_meta_tipos_contem_campos_guiados():
    cli = _montar()
    r = cli.get("/pecas/modos/meta")
    body = r.json()
    peticao = next(t for t in body["tipos"] if t["value"] == "peticao_inicial")
    assert "partes" in peticao["campos_guiados"]
    assert "fatos" in peticao["campos_guiados"]


def test_meta_bloqueia_cliente_externo():
    cli = _montar(_FakeClienteExterno())
    r = cli.get("/pecas/modos/meta")
    assert r.status_code == 403


# ── POST /preparar — modo livre ─────────────────────────────────────────────


def test_livre_sem_case_id():
    cli = _montar()
    r = cli.post("/pecas/modos/preparar", json={
        "modo": "livre",
        "tipo_peca": "contestacao",
        "area_direito": "civil",
        "instrucao_livre": "Impugnar os fatos e pedidos.",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["pronto_para_redacao"] is True
    assert body["exige_aprovacao"] is False
    assert body["bloqueios"] == []
    assert "[MODO DE PRODUÇÃO CONTROLADO]" in body["instrucoes_pipeline"]
    assert "contestacao" in body["instrucoes_pipeline"]


def test_estagiario_pode_acessar():
    cli = _montar(_FakeEstagiario())
    r = cli.post("/pecas/modos/preparar", json={
        "modo": "livre",
        "tipo_peca": "peticao_inicial",
        "area_direito": "trabalhista",
        "instrucao_livre": "test",
    })
    assert r.status_code == 200


# ── POST /preparar — modo guiado ────────────────────────────────────────────


def test_guiado_campos_completos():
    cli = _montar()
    r = cli.post("/pecas/modos/preparar", json={
        "modo": "guiado",
        "tipo_peca": "peticao_inicial",
        "area_direito": "civil",
        "respostas_guiadas": {
            "partes": "Autor vs Reu",
            "fatos": "Fato X",
            "pretensao": "Indenizacao",
            "competencia": "Justica Estadual",
            "provas": "Documento Y",
            "pedidos": "Condenacao do Reu",
        },
    })
    assert r.status_code == 200
    body = r.json()
    assert body["pronto_para_redacao"] is True
    assert body["bloqueios"] == []


def test_guiado_campos_ausentes_bloqueia():
    cli = _montar()
    r = cli.post("/pecas/modos/preparar", json={
        "modo": "guiado",
        "tipo_peca": "peticao_inicial",
        "area_direito": "civil",
        "respostas_guiadas": {"partes": "A vs R"},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["pronto_para_redacao"] is False
    assert len(body["bloqueios"]) > 0


# ── POST /preparar — modo molde ─────────────────────────────────────────────


def test_molde_exige_versao_e_hash():
    cli = _montar()
    r = cli.post("/pecas/modos/preparar", json={
        "modo": "molde",
        "tipo_peca": "peticao_inicial",
        "area_direito": "civil",
        "molde": {
            "referencia": {
                "documento_id": "doc-001",
                "versao": 1,
                "hash_conteudo": "abc123def456",
            },
        },
    })
    body = r.json()
    assert body["pronto_para_redacao"] is True
    assert "[MOLDE CONTROLADO]" in body["instrucoes_pipeline"]


def test_molde_sem_versao_bloqueia():
    cli = _montar()
    r = cli.post("/pecas/modos/preparar", json={
        "modo": "molde",
        "tipo_peca": "peticao_inicial",
        "area_direito": "civil",
        "molde": {
            "referencia": {
                "documento_id": "doc-001",
            },
        },
    })
    body = r.json()
    assert body["pronto_para_redacao"] is False
    assert len(body["bloqueios"]) >= 2


# ── POST /preparar — modo agente ────────────────────────────────────────────


def test_agente_exige_case_id_e_docs_e_aprovacao():
    cli = _montar()
    r = cli.post("/pecas/modos/preparar", json={
        "modo": "agente",
        "tipo_peca": "peticao_inicial",
        "area_direito": "civil",
    })
    body = r.json()
    assert body["pronto_para_redacao"] is False
    bloqueios_juntos = " ".join(body["bloqueios"]).lower()
    assert "caso" in bloqueios_juntos or "autorizado" in bloqueios_juntos or "documentos" in bloqueios_juntos
    assert body["exige_aprovacao"] is True
    assert len(body["etapas"]) == 10


# ── Validação de entrada ────────────────────────────────────────────────────


def test_modo_invalido_rejeitado():
    cli = _montar()
    r = cli.post("/pecas/modos/preparar", json={
        "modo": "desconhecido",
        "tipo_peca": "peticao_inicial",
        "area_direito": "civil",
    })
    assert r.status_code == 422


def test_tipo_invalido_rejeitado():
    cli = _montar()
    r = cli.post("/pecas/modos/preparar", json={
        "modo": "livre",
        "tipo_peca": "tipo_que_nao_existe",
        "area_direito": "civil",
        "instrucao_livre": "x",
    })
    assert r.status_code == 422


def test_area_invalida_rejeitada():
    cli = _montar()
    r = cli.post("/pecas/modos/preparar", json={
        "modo": "livre",
        "tipo_peca": "peticao_inicial",
        "area_direito": "area_que_nao_existe",
        "instrucao_livre": "x",
    })
    assert r.status_code == 422


def test_cliente_externo_bloqueado_no_preparar():
    cli = _montar(_FakeClienteExterno())
    r = cli.post("/pecas/modos/preparar", json={
        "modo": "livre",
        "tipo_peca": "peticao_inicial",
        "area_direito": "civil",
        "instrucao_livre": "x",
    })
    assert r.status_code == 403


# ── Verificar_acesso_caso (ownership) ───────────────────────────────────────


@patch("app.routers.peca_modos.verificar_acesso_caso")
def test_case_id_aciona_verificar_acesso(mock_acesso):
    cli = _montar()
    r = cli.post("/pecas/modos/preparar", json={
        "modo": "livre",
        "case_id": "case-123",
        "tipo_peca": "peticao_inicial",
        "area_direito": "civil",
        "instrucao_livre": "test",
    })
    assert r.status_code == 200
    mock_acesso.assert_called_once()
