"""IA-01 — análise de documento sanitiza PII ANTES de enviar ao LLM (Groq=EUA)."""


class _R:
    def __init__(self, texto):
        self.texto, self.provedor, self.modelo = texto, "groq", "llama"


async def test_documento_sanitiza_pii_antes_do_llm(monkeypatch):
    captured = {}

    # OCR falso devolve um documento com PII estruturada.
    monkeypatch.setattr(
        "app.services.ocr_service.extrair_texto",
        lambda *a, **k: ("Cliente Maria Souza, CPF 987.654.321-00, processo "
                         "1234567-89.2020.8.13.0024, em discussao contratual."),
    )

    async def fake_chat(*, messages, **kw):
        captured["user"] = messages[1]["content"]   # mensagem do usuário (documento)
        return _R('{"ok": true}')

    monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)

    from app.services.documento_service import extrair_e_analisar
    await extrair_e_analisar("/fake.pdf", "application/pdf", db=None, enriquecer_rag=False)

    prompt = captured["user"]
    assert "987.654.321-00" not in prompt              # CPF mascarado
    assert "1234567-89.2020.8.13.0024" not in prompt   # nº processo mascarado
    assert "[CPF]" in prompt                            # confirma sanitização
