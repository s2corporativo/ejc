from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.ai import provider_metrics_runtime as metrics


@pytest.mark.asyncio
async def test_instrumentacao_agrupa_falha_e_sucesso_no_mesmo_request(monkeypatch):
    gravados: list[dict] = []

    async def persistir_fake(**dados):
        gravados.append(dados)

    async def barreira(provider, model, messages, modo, entidades, temperature, max_tokens):
        if provider == "anthropic":
            raise TimeoutError("conteúdo sensível que não pode ser persistido")
        return (
            "ok",
            "ok",
            {"model": "sabia-4", "input_tokens": 10, "output_tokens": 5},
            messages,
            False,
        )

    def resolver(task_type, *args, **kwargs):
        return [("anthropic", None), ("maritaca", "sabia-4")]

    async def tarefa(*args, **kwargs):
        return {"ok": True}

    gateway = SimpleNamespace(
        _resolver_cadeia=resolver,
        _chamar_com_barreira=barreira,
        executar_tarefa_ia=tarefa,
    )
    monkeypatch.setattr(metrics, "_persistir", persistir_fake)
    monkeypatch.setattr(metrics, "estimar_custo_brl", lambda *args: 0.0123)

    metrics._instalar_instrumentacao(gateway)
    cadeia = gateway._resolver_cadeia("elaboracao_peca", None, None)

    with pytest.raises(TimeoutError):
        await gateway._chamar_com_barreira(
            cadeia[0][0], cadeia[0][1], [], None, None, 0.2, 100
        )
    resultado = await gateway._chamar_com_barreira(
        cadeia[1][0], cadeia[1][1], [], None, None, 0.2, 100
    )

    assert resultado[0] == "ok"
    assert len(gravados) == 2
    assert gravados[0]["request_id"] == gravados[1]["request_id"]
    assert gravados[0]["status"] == "erro"
    assert gravados[0]["fallback_reason"] == "TimeoutError"
    assert "sensível" not in gravados[0]["fallback_reason"]
    assert gravados[1]["status"] == "sucesso"
    assert gravados[1]["fallback_triggered"] is True
    assert gravados[1]["task_type"] == "elaboracao_peca"
    assert gravados[1]["input_tokens"] == 10
    assert gravados[1]["output_tokens"] == 5
    assert float(gravados[1]["estimated_cost_brl"]) == 0.0123


@pytest.mark.asyncio
async def test_caminho_profissional_preserva_tipo_da_tarefa(monkeypatch):
    gravados: list[dict] = []

    async def persistir_fake(**dados):
        gravados.append(dados)

    async def barreira(provider, model, messages, modo, entidades, temperature, max_tokens):
        return (
            "ok",
            "ok",
            {"model": "sabia-4", "input_tokens": 1, "output_tokens": 2},
            messages,
            False,
        )

    gateway = SimpleNamespace()
    gateway._resolver_cadeia = lambda *args, **kwargs: [("maritaca", "sabia-4")]
    gateway._chamar_com_barreira = barreira

    async def tarefa(tarefa, *args, **kwargs):
        await gateway._chamar_com_barreira(
            "maritaca", "sabia-4", [], None, None, 0.1, 50
        )
        return {"ok": True}

    gateway.executar_tarefa_ia = tarefa
    monkeypatch.setattr(metrics, "_persistir", persistir_fake)
    monkeypatch.setattr(metrics, "estimar_custo_brl", lambda *args: 0)

    metrics._instalar_instrumentacao(gateway)
    await gateway.executar_tarefa_ia("resumo_processual")

    assert len(gravados) == 1
    assert gravados[0]["task_type"] == "resumo_processual"
    assert gravados[0]["provider"] == "maritaca"
