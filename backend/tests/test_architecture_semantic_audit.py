from __future__ import annotations

from fastapi import FastAPI

from app.core.route_registry import auditar_semantica


def _app_com_rotas(*paths: str) -> FastAPI:
    app = FastAPI()
    for i, path in enumerate(paths):
        async def endpoint(i=i):
            return {"i": i}
        app.add_api_route(path, endpoint, methods=["GET"], name=f"r{i}")
    return app


def test_prefixos_parecidos_mas_contratos_distintos_nao_sao_duplicidade():
    app = _app_com_rotas(
        "/ai/analisar-caso",
        "/ia/status",
        "/conhecimento/importar-jurisprudencia",
        "/rag/query",
    )

    auditoria = auditar_semantica(app)

    assert auditoria["ok"] is True
    assert auditoria["violacoes"] == []
    assert auditoria["duplicatas_literais"] == []


def test_familia_ja_consolidada_reintroduzida_falha_auditoria():
    app = _app_com_rotas("/teses/listar", "/teses-v4/listar")

    auditoria = auditar_semantica(app)

    assert auditoria["ok"] is False
    assert auditoria["resolvidos_reintroduzidos"] == [
        {
            "prefixo_a": "/teses",
            "prefixo_b": "/teses-v4",
            "motivo": "Motor de teses com versão paralela.",
        }
    ]


def test_duplicata_literal_falha_auditoria():
    app = FastAPI()

    async def a():
        return {"a": 1}

    async def b():
        return {"b": 1}

    app.add_api_route("/mesma", a, methods=["GET"])
    app.add_api_route("/mesma", b, methods=["GET"])

    auditoria = auditar_semantica(app)

    assert auditoria["ok"] is False
    assert "GET /mesma" in auditoria["duplicatas_literais"]
