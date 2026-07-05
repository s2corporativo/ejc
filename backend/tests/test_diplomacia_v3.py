# ── tests/test_diplomacia_v3.py ──────────────────────────────────────────────
# P1 (2026-07-05) — Diplomacia Digital:
#   1. /calcular-acordo usa a Selic REAL do BCB quando o caller não informa
#      (fallback 10,75% encapsulado em bcb_service.selic_anualizada).
#   2. gerar_dossie_pressao chama o gateway central (task "estrategia") em vez
#      de retornar string fixa; endpoint /dossie-pressao registra AILog e
#      devolve rascunho (HITL).
# Unitários sem Postgres/HTTP: handlers chamados direto (padrão dos vizinhos).
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.ai_log import AILog, AITipoUso
from app.routers import diplomacia_v3
from app.services.ai_gateway import GatewayResponse
from app.services.diplomacia_digital import DiplomaciaDigital, diplomacia


class _FakeDB:
    def __init__(self):
        self.added: list = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _fake_chat(texto="Acordo hoje é a decisão racional.", capturado=None):
    async def chat(messages, task_type="", **kw):
        if capturado is not None:
            capturado["messages"] = messages
            capturado["task_type"] = task_type
        return GatewayResponse(
            texto=texto, modelo="modelo-x", provedor="ollama",
            task_type=task_type, input_tokens=10, output_tokens=20,
        )
    return chat


# ── Selic real no /calcular-acordo ────────────────────────────────────────────
async def test_calcular_acordo_busca_selic_real_quando_nao_informada(monkeypatch):
    async def fake_selic():
        return {"selic_anual": 0.15, "fonte": "bcb", "meses_compostos": 12}
    monkeypatch.setattr(diplomacia_v3.bcb_service, "selic_anualizada", fake_selic)

    r = await diplomacia_v3.calcular_acordo(
        {"valor_causa": 100_000.0, "prob_exito": 0.7, "tempo_anos": 2.0}, cu=None,
    )
    assert r["selic_anual"] == 0.15
    assert r["selic_fonte"] == "bcb"
    assert r["valor_presente_liquido"] == pytest.approx(
        70_000.0 / (1.15 ** 2), abs=0.01)


async def test_calcular_acordo_respeita_selic_informada(monkeypatch):
    async def bcb_nao_deve_ser_chamado():
        raise AssertionError("BCB não deve ser consultado com selic informada")
    monkeypatch.setattr(
        diplomacia_v3.bcb_service, "selic_anualizada", bcb_nao_deve_ser_chamado)

    r = await diplomacia_v3.calcular_acordo(
        {"valor_causa": 100_000.0, "prob_exito": 0.7, "tempo_anos": 2.0,
         "selic_anual": 0.10}, cu=None,
    )
    assert r["selic_anual"] == 0.10
    assert r["selic_fonte"] == "informada"


async def test_calcular_acordo_dados_insuficientes_400():
    with pytest.raises(HTTPException) as exc:
        await diplomacia_v3.calcular_acordo({"valor_causa": 100.0}, cu=None)
    assert exc.value.status_code == 400


# ── Dossiê de Pressão (serviço) ───────────────────────────────────────────────
async def test_gerar_dossie_pressao_chama_gateway_estrategia(monkeypatch):
    from app.services import ai_gateway
    capturado: dict = {}
    monkeypatch.setattr(ai_gateway, "chat", _fake_chat(capturado=capturado))

    dados = DiplomaciaDigital().calcular_ponto_equilibrio(100_000.0, 0.7, 2.0)
    r = await diplomacia.gerar_dossie_pressao(dados)

    assert r["argumentacao"] == "Acordo hoje é a decisão racional."
    assert r["modelo"] == "modelo-x" and r["provedor"] == "ollama"
    assert capturado["task_type"] == "estrategia"
    prompt = capturado["messages"][0]["content"]
    assert "100000.0" in prompt and "0.7" in prompt  # dados numéricos, sem PII
    assert r["prompt"]  # prompt exposto para o AILog do router


# ── Endpoint /dossie-pressao ──────────────────────────────────────────────────
async def test_dossie_pressao_endpoint_gera_rascunho_com_ailog(monkeypatch):
    from app.services import ai_gateway
    monkeypatch.setattr(ai_gateway, "chat", _fake_chat())

    db = _FakeDB()
    cu = SimpleNamespace(id="user-1")
    # selic_anual informada → não depende do BCB no teste
    r = await diplomacia_v3.dossie_pressao(
        {"valor_causa": 100_000.0, "prob_exito": 0.7, "tempo_anos": 2.0,
         "selic_anual": 0.1075},
        db=db, cu=cu,
    )

    assert r["is_rascunho"] is True
    assert "HITL" in r["aviso_hitl"]
    assert r["argumentacao"] == "Acordo hoje é a decisão racional."
    assert r["dados_acordo"]["selic_fonte"] == "informada"
    assert r["log_id"]

    # AILog registrado (rastro HITL/LGPD obrigatório)
    logs = [o for o in db.added if isinstance(o, AILog)]
    assert len(logs) == 1
    log = logs[0]
    assert log.user_id == "user-1"
    assert log.tipo_uso == AITipoUso.analise_caso
    assert log.resposta == "Acordo hoje é a decisão racional."
    assert log.modelo == "ollama/modelo-x"
    assert db.commits >= 1


async def test_dossie_pressao_endpoint_valida_payload():
    with pytest.raises(HTTPException) as exc:
        await diplomacia_v3.dossie_pressao(
            {"prob_exito": 0.7}, db=_FakeDB(), cu=SimpleNamespace(id="u"))
    assert exc.value.status_code == 400
