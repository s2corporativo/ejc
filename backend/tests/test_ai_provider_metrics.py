from __future__ import annotations

from app.services.ai.provider_metrics_runtime import _tipo_erro_seguro, normalizar_erro


class _Resposta:
    status_code = 429


class ErroComSegredo(RuntimeError):
    def __init__(self):
        super().__init__("CPF 123.456.789-00 e chave secreta sk-nao-persistir")
        self.response = _Resposta()


class _ProviderPulado(RuntimeError):
    pass


def test_normalizar_erro_nao_persiste_mensagem_ou_pii():
    status, http_status, motivo = normalizar_erro(ErroComSegredo())

    assert status == "erro"
    assert http_status == 429
    assert motivo == "ErroComSegredo (HTTP 429)"
    assert "123.456" not in motivo
    assert "sk-nao-persistir" not in motivo


def test_bloqueio_lgpd_tem_motivo_seguro_e_explicito():
    status, http_status, motivo = normalizar_erro(
        _ProviderPulado("PII residual encontrada: CPF real")
    )

    assert status == "bloqueado_lgpd"
    assert http_status is None
    assert motivo == "Bloqueio preventivo de PII (LGPD)"
    assert "CPF real" not in motivo


def test_modelo_de_telemetria_nao_possui_prompt_ou_resposta():
    from app.models.ai_provider_metric import AIProviderMetric

    colunas = set(AIProviderMetric.__table__.columns.keys())
    assert {"provider", "model", "duration_ms", "estimated_cost_brl"} <= colunas
    assert "prompt" not in colunas
    assert "prompt_sanitizado" not in colunas
    assert "resposta" not in colunas
    assert "conteudo" not in colunas


def test_normalizar_erro_preserva_metadado_estruturado_sem_ler_mensagem():
    from app.core.ai_errors import SafeAIError

    pii = "CPF 123.456.789-09"
    exc = SafeAIError(
        f"mensagem interna que não deve ser usada: {pii}",
        code="provider_failure",
        technical_type="RateLimitError",
        status_code=429,
    )

    status, http_status, reason = normalizar_erro(exc)

    assert status == "erro"
    assert http_status == 429
    assert reason == "RateLimitError (HTTP 429)"
    assert pii not in reason


def test_tipo_erro_seguro_preserva_subtipo_estruturado_sem_ler_mensagem():
    from app.core.ai_errors import SafeAIError

    exc = SafeAIError(
        "CPF 123.456.789-09 não pode aparecer",
        code="provider_failure",
        technical_type="RateLimitError",
        status_code=429,
    )

    assert _tipo_erro_seguro(exc) == "RateLimitError"
