# ── tests/test_ai_gateway_barreira.py ────────────────────────────────────────
# #39: a barreira LGPD (sanitização antes de provider EXTERNO + reidratação) foi
# consolidada em _chamar_com_barreira, fonte única de chat() e executar_tarefa_ia.
# Estes testes TRAVAM o invariante: um refactor que enfraqueça a barreira falha aqui.
import pytest

from app.services import ai_gateway as gw


async def test_provider_externo_com_pii_residual_e_pulado_sem_chamar(monkeypatch):
    """PII residual após sanitização → _ProviderPulado e o provider externo
    NUNCA é chamado (o conteúdo não vaza)."""
    chamou = {"provider": False}

    async def _fake_prov(*a, **k):
        chamou["provider"] = True
        return "resp", {"input_tokens": 1, "output_tokens": 1, "model": "x"}

    monkeypatch.setattr(gw, "_chamar_provedor", _fake_prov)
    monkeypatch.setattr(gw.settings, "AI_REQUIRE_SANITIZATION_FOR_EXTERNAL", True)
    monkeypatch.setattr(gw, "_preparar_mensagens_externo",
                        lambda m, modo, ent: (m, ["cpf"], None))

    with pytest.raises(gw._ProviderPulado):
        await gw._chamar_com_barreira(
            "anthropic", None, [{"role": "user", "content": "x"}], None, None, 0.2, 128
        )
    assert chamou["provider"] is False


async def test_provider_externo_recebe_sanitizado_e_resposta_reidratada(monkeypatch):
    """O provider externo recebe o conteúdo SANITIZADO; a resposta devolvida é
    REIDRATADA, mas o texto_para_log fica pseudonimizado (sem PII real)."""
    recebidas = {}

    async def _fake_prov(provider, model, messages_envio, temp, maxt):
        recebidas["msgs"] = messages_envio
        return "RESP_TOKEN", {"input_tokens": 1, "output_tokens": 1, "model": "x"}

    san = [{"role": "user", "content": "SANITIZADO"}]
    monkeypatch.setattr(gw, "_chamar_provedor", _fake_prov)
    monkeypatch.setattr(gw.settings, "AI_REQUIRE_SANITIZATION_FOR_EXTERNAL", True)
    monkeypatch.setattr(gw, "_preparar_mensagens_externo",
                        lambda m, modo, ent: (san, [], {"TOKEN": "REAL"}))
    monkeypatch.setattr("app.services.ai.pseudonymizer.reidratar",
                        lambda texto, mapa: texto.replace("TOKEN", "REAL"))

    texto, texto_log, usage, envio, pii = await gw._chamar_com_barreira(
        "anthropic", None, [{"role": "user", "content": "REAL"}], None, None, 0.2, 128
    )
    assert recebidas["msgs"] == san           # externo recebeu o sanitizado
    assert texto == "RESP_REAL"               # resposta reidratada p/ o chamador
    assert texto_log == "RESP_TOKEN"          # log SEM PII real
    assert pii is True


async def test_provider_local_nao_passa_pela_sanitizacao(monkeypatch):
    """Provider local (ollama) não é externo → a sanitização não roda e as
    mensagens seguem íntegras (uso interno)."""
    async def _fake_prov(provider, model, messages_envio, temp, maxt):
        return "ok", {"input_tokens": 1, "output_tokens": 1, "model": "local"}

    def _nao_deve_rodar(*a, **k):
        raise AssertionError("provider local não deve sanitizar")

    monkeypatch.setattr(gw, "_chamar_provedor", _fake_prov)
    monkeypatch.setattr(gw, "_preparar_mensagens_externo", _nao_deve_rodar)

    orig = [{"role": "user", "content": "REAL"}]
    texto, texto_log, usage, envio, pii = await gw._chamar_com_barreira(
        "ollama", None, orig, None, None, 0.2, 128
    )
    assert envio is orig and pii is False
