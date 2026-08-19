from __future__ import annotations

import pytest

from app.services import diagnostico_juridico_service as svc


def test_calendario_validado(monkeypatch):
    monkeypatch.setattr(
        svc,
        "calendario_runtime_status",
        lambda: {
            "status": "validado",
            "feriados_ok": True,
            "suspensoes_ok": True,
        },
    )
    item = svc._probe_calendario_prazos()
    assert item["status"] == "ok"
    assert item["feriados_ok"] is True
    assert item["suspensoes_ok"] is True


def test_calendario_degradado_bloqueia_confianca(monkeypatch):
    monkeypatch.setattr(
        svc,
        "calendario_runtime_status",
        lambda: {
            "status": "degradado",
            "feriados_ok": False,
            "suspensoes_ok": True,
            "feriados_erro_tipo": "DatabaseError",
            "suspensoes_erro_tipo": None,
        },
    )
    item = svc._probe_calendario_prazos()
    assert item["status"] == "erro"
    assert "preliminares" in item["detalhe"]
    assert "DatabaseError" in item["detalhe"]


def test_dou_tres_falhas_consecutivas_vira_erro(monkeypatch):
    monkeypatch.setattr(
        svc,
        "status_dou",
        lambda: {
            "status": "degradado",
            "ultima_execucao": "2026-08-19T12:00:00+00:00",
            "falhas_consecutivas": 3,
            "ultimo_erro_tipo": "HTTPStatusError",
        },
    )
    item = svc._probe_dou_runtime()
    assert item["status"] == "erro"
    assert item["falhas_consecutivas"] == 3
    assert "HTTPStatusError" in item["detalhe"]
    assert "keyword" not in item


@pytest.mark.asyncio
async def test_wrapper_recalcula_status_geral(monkeypatch):
    async def base(_db=None):
        return {
            "gerado_em": "2026-08-19T12:00:00+00:00",
            "status_geral": "ok",
            "resumo": {"ok": 1, "alerta": 0, "erro": 0, "desligado": 0},
            "subsistemas": [
                {
                    "nome": "Banco de dados",
                    "status": "ok",
                    "detalhe": "ok",
                    "acao_sugerida": "",
                    "latencia_ms": 1,
                }
            ],
            "aviso": "somente leitura",
        }

    monkeypatch.setattr(svc.diagnostico_service, "diagnostico_completo", base)
    monkeypatch.setattr(
        svc,
        "calendario_runtime_status",
        lambda: {"status": "nao_inicializado", "feriados_ok": None, "suspensoes_ok": None},
    )
    monkeypatch.setattr(
        svc,
        "status_dou",
        lambda: {"status": "nunca_executado", "falhas_consecutivas": 0},
    )

    payload = await svc.diagnostico_completo_com_juridico(None)
    assert payload["status_geral"] == "alerta"
    assert payload["resumo"]["alerta"] == 1
    assert len(payload["subsistemas"]) == 3
