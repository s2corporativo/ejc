"""IA-01 — a extração de documento com PII roda SÓ no modelo local (Ollama),
nunca em provedor de nuvem (Groq/EUA).

Contrato atual (Fase 3B, LGPD): o texto passa por sanitizar_pii ANTES de
qualquer chamada de IA — mesmo a local. CPF/nº de processo/e-mail viram
marcadores ([CPF], [PROCESSO], ...). Defesa em profundidade: além da
sanitização, a chamada permanece FIXADA no modelo local via
provider_override="ollama", SEM fallback para a nuvem: se o Ollama cair,
a extração falha FECHADA. Este teste trava esses invariantes contra regressão."""


class _R:
    def __init__(self, texto):
        self.texto, self.provedor, self.modelo = texto, "ollama", "llama3"


_DOC = ("Cliente Maria Souza, CPF 987.654.321-00, processo "
        "1234567-89.2020.8.13.0024, em discussao contratual.")


async def test_extracao_pii_fixada_no_modelo_local(monkeypatch):
    """A extração de PII só pode ser roteada para o modelo local (Ollama)."""
    captured = {}

    # OCR falso devolve um documento com PII estruturada.
    monkeypatch.setattr(
        "app.services.ocr_service.extrair_texto",
        lambda *a, **k: _DOC,
    )

    async def fake_chat(*, messages, provider_override=None, **kw):
        captured["provider_override"] = provider_override
        captured["user"] = messages[1]["content"]   # mensagem do usuário (documento)
        return _R('{"ok": true}')

    monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)

    from app.services.documento_service import extrair_e_analisar
    await extrair_e_analisar("/fake.pdf", "application/pdf", db=None, enriquecer_rag=False)

    # Invariante LGPD: a chamada é FIXADA no modelo local — o PII nunca vai à nuvem.
    assert captured["provider_override"] == "ollama"
    # Fase 3B: o texto é SANITIZADO antes de qualquer IA (mesmo a local) —
    # CPF e nº de processo viram marcadores; a PII crua não aparece no prompt.
    assert "987.654.321-00" not in captured["user"]
    assert "1234567-89.2020.8.13.0024" not in captured["user"]
    assert "[CPF]" in captured["user"]
    assert "[PROCESSO]" in captured["user"]


async def test_extracao_falha_fechado_sem_ollama(monkeypatch):
    """Se o modelo local cair, a extração falha FECHADA — nunca cai para a nuvem."""
    monkeypatch.setattr(
        "app.services.ocr_service.extrair_texto",
        lambda *a, **k: _DOC,
    )

    async def fake_chat(*, provider_override=None, **kw):
        # Só o provedor local pode ser chamado; e ele está indisponível.
        assert provider_override == "ollama"
        raise RuntimeError("ollama indisponível")

    monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)

    from app.services.documento_service import extrair_e_analisar
    r = await extrair_e_analisar("/fake.pdf", "application/pdf", db=None, enriquecer_rag=False)

    assert r["ok"] is False
    assert "local" in r["erro"].lower()   # mensagem explica o fail-closed local
