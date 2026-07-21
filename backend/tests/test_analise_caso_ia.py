"""Testes do módulo Análise de Caso IA (chat multi-turno).

Padrão local-fake (vizinho: test_ia_endpoints_payload.py): endpoints REAIS via
TestClient com get_db/get_current_user substituídos. Aqui, porém, o get_db usa
um SQLite async (aiosqlite in-memory) com as tabelas do módulo + ai_logs criadas
a partir da própria metadata — assim a persistência (sessão, mensagens, AILog) é
exercitada de verdade. NENHUMA chamada real de IA acontece: ai_gateway.chat e
citation_gate.validar_citacoes são monkeypatchados.

Cobre: criar sessão, listar, fluxo de mensagem (grava AILog + mensagem assistant
rascunho + emite SSE), ownership (403 em sessão de outro usuário) e bloqueio de
cliente_externo.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import get_current_user
from app.models.ai_log import AILog
from app.models.analise_caso_ia import AnaliseCasoMensagem, AnaliseCasoSessao
from app.models.user import UserRole
from app.routers import analise_caso_ia
from app.services.ai_gateway import GatewayResponse
from app.services.citation_gate import RelatorioCitacoes


class _FakeUser:
    def __init__(self, uid: str = "user-A", role=UserRole.advogado):
        self.id = uid
        self.role = role
        self.full_name = "Advogado Teste"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture()
def ambiente():
    """Engine SQLite in-memory (StaticPool = conexão única persistente) + app com
    o router montado e overrides de get_db/get_current_user."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    async def _criar_schema():
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda c: Base.metadata.create_all(
                    c,
                    tables=[
                        AnaliseCasoSessao.__table__,
                        AnaliseCasoMensagem.__table__,
                        AILog.__table__,
                    ],
                )
            )

    _run(_criar_schema())
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_db():
        async with Session() as s:
            yield s

    app = FastAPI()
    app.include_router(analise_caso_ia.router)
    estado = {"user": _FakeUser()}
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: estado["user"]

    client = TestClient(app)
    try:
        yield client, estado, Session
    finally:
        client.close()
        _run(engine.dispose())


# ── Monkeypatch dos serviços de IA ────────────────────────────────────────────
@pytest.fixture()
def mock_ia(monkeypatch):
    async def _fake_chat(messages, *args, **kwargs):
        return GatewayResponse(
            texto="Análise (rascunho): FATOS, QUESTÃO, REGRA (verificar fonte), "
                  "APLICAÇÃO e CONCLUSÃO com nível de confiança.",
            modelo="modelo-teste",
            provedor="ollama",
            task_type="analise_juridica",
            input_tokens=120,
            output_tokens=64,
            custo_estimado_brl=0.0,
        )

    async def _fake_valida(db, texto, **kwargs):
        return RelatorioCitacoes(politica="desligado", total=0)

    monkeypatch.setattr(analise_caso_ia.ai_gateway, "chat", _fake_chat)
    monkeypatch.setattr(analise_caso_ia.citation_gate, "validar_citacoes", _fake_valida)
    return monkeypatch


# ── Criar / listar sessão ─────────────────────────────────────────────────────
def test_criar_e_listar_sessao(ambiente):
    client, _estado, _Session = ambiente

    r = client.post("/analise-caso-ia/sessoes", json={"nivel": "maximo", "area": "Cível"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["titulo"] == "Nova análise"
    assert body["nivel"] == "maximo"
    assert body["area"] == "Cível"
    assert body["arquivada"] is False
    sid = body["id"]

    r = client.get("/analise-caso-ia/sessoes")
    assert r.status_code == 200, r.text
    lista = r.json()
    assert len(lista) == 1
    assert lista[0]["id"] == sid
    assert lista[0]["total_mensagens"] == 0
    assert lista[0]["ultima_mensagem_preview"] is None


def test_nivel_invalido_422(ambiente):
    client, _estado, _Session = ambiente
    r = client.post("/analise-caso-ia/sessoes", json={"nivel": "turbo"})
    assert r.status_code == 422, r.text


# ── Fluxo de mensagem (SSE) — grava AILog + assistant rascunho ────────────────
def test_fluxo_mensagem_grava_ailog_e_assistant(ambiente, mock_ia):
    client, _estado, Session = ambiente

    sid = client.post("/analise-caso-ia/sessoes", json={}).json()["id"]

    r = client.post(
        f"/analise-caso-ia/sessoes/{sid}/mensagem",
        json={"conteudo": "Analise a viabilidade da minha ação de cobrança."},
    )
    assert r.status_code == 200, r.text
    corpo = r.text
    assert "event: inicio" in corpo
    assert "event: chunk" in corpo
    assert "event: concluido" in corpo

    # Extrai o payload do evento 'concluido'.
    concluido = None
    for bloco in corpo.split("\n\n"):
        if "event: concluido" in bloco:
            linha = [l for l in bloco.splitlines() if l.startswith("data:")][0]
            concluido = json.loads(linha[len("data:"):].strip())
    assert concluido is not None
    assert concluido["is_rascunho"] is True
    assert concluido["provedor"] == "ollama"
    assert concluido["ai_log_id"]
    assert "citacoes" in concluido

    # A sessão agora tem user + assistant; título derivado da 1ª mensagem.
    det = client.get(f"/analise-caso-ia/sessoes/{sid}").json()
    papeis = [m["papel"] for m in det["mensagens"]]
    assert papeis == ["user", "assistant"]
    assistant = det["mensagens"][1]
    assert assistant["is_rascunho"] is True
    assert assistant["ai_log_id"] == concluido["ai_log_id"]
    assert det["titulo"].startswith("Analise a viabilidade")

    # AILog persistido (rastro de auditoria obrigatório).
    async def _contar_logs():
        from sqlalchemy import select, func as safunc
        async with Session() as db:
            return (await db.execute(select(safunc.count(AILog.id)))).scalar_one()

    assert _run(_contar_logs()) == 1


# ── Ownership: 404 ao acessar sessão de outro usuário (não vaza existência) ───
def test_ownership_404_sessao_de_outro_usuario(ambiente):
    client, estado, _Session = ambiente

    estado["user"] = _FakeUser(uid="user-A")
    sid = client.post("/analise-caso-ia/sessoes", json={}).json()["id"]

    # Sessão alheia responde 404 (mesmo status de inexistente) — sem oráculo 403/404.
    estado["user"] = _FakeUser(uid="user-B")
    r = client.get(f"/analise-caso-ia/sessoes/{sid}")
    assert r.status_code == 404, r.text

    # E não enxerga a sessão do outro na listagem.
    assert client.get("/analise-caso-ia/sessoes").json() == []


# ── Bloqueio de cliente_externo (defesa em profundidade) ──────────────────────
def test_cliente_externo_bloqueado(ambiente):
    client, estado, _Session = ambiente
    estado["user"] = _FakeUser(uid="cli-1", role=UserRole.cliente_externo)

    r = client.post("/analise-caso-ia/sessoes", json={})
    assert r.status_code == 403, r.text

    r = client.get("/analise-caso-ia/sessoes")
    assert r.status_code == 403, r.text


# ── Anexo de documento com OCR (mock do extrator) ─────────────────────────────
def test_anexar_documento_cria_mensagem_com_contexto(ambiente, monkeypatch):
    client, _estado, _Session = ambiente
    # Neutraliza o gate de magic bytes (bytes de teste falsos) — validado à parte.
    monkeypatch.setattr(
        "app.routers.documents._validar_conteudo",
        lambda ext, b: "application/pdf",
    )
    monkeypatch.setattr(
        analise_caso_ia.ocr_service, "extrair_texto",
        lambda filepath, mimetype: "TEXTO EXTRAÍDO DO PDF DE TESTE",
    )

    sid = client.post("/analise-caso-ia/sessoes", json={}).json()["id"]
    r = client.post(
        f"/analise-caso-ia/sessoes/{sid}/documento",
        files={"file": ("peticao.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert r.status_code == 200, r.text
    msg = r.json()
    assert msg["papel"] == "user"
    assert msg["anexo_nome"] == "peticao.pdf"
    assert "Documento anexado" in msg["conteudo"]


def test_anexar_documento_ocr_vazio_422(ambiente, monkeypatch):
    client, _estado, _Session = ambiente
    # Passa o gate de magic bytes; o 422 vem do OCR vazio, não do gate.
    monkeypatch.setattr(
        "app.routers.documents._validar_conteudo",
        lambda ext, b: "application/pdf",
    )
    monkeypatch.setattr(
        analise_caso_ia.ocr_service, "extrair_texto",
        lambda filepath, mimetype: "",
    )
    sid = client.post("/analise-caso-ia/sessoes", json={}).json()["id"]
    r = client.post(
        f"/analise-caso-ia/sessoes/{sid}/documento",
        files={"file": ("vazio.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert r.status_code == 422, r.text
