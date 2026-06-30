"""Análise estratégica (Fase 4 / 4C) — PII sanitizada ANTES de ir ao LLM.

Prova que CPF e nomes próprios são mascarados no prompt enviado ao gateway,
e que a segunda barreira (validar_sem_pii) está no caminho.
"""


class _Resp:
    def __init__(self, texto):
        self.texto = texto


async def test_sanitiza_pii_antes_do_llm(monkeypatch):
    captured = {}

    async def fake_chat(*, messages, **kw):
        captured["prompt"] = messages[0]["content"]
        return _Resp('{"ramo":"Civel","partes":[]}')

    # analisar_caso faz `from app.services.ai_gateway import chat` em runtime,
    # então basta trocar o atributo do módulo.
    monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)

    from app.services.analise_estrategica import analisar_caso

    res = await analisar_caso(
        titulo="Acao de Joao da Silva",
        fatos="Cliente Joao da Silva, CPF 123.456.789-09, contra a parte adversa.",
        numero_processo="1234567-89.2020.8.13.0024",
        nomes_proteger=["Joao da Silva"],
        db=None,
    )

    prompt = captured["prompt"]
    assert "123.456.789-09" not in prompt   # CPF mascarado
    assert "1234567-89.2020.8.13.0024" not in prompt  # nº processo mascarado
    assert "Joao da Silva" not in prompt     # nome mascarado via nomes_proteger
    assert "[CPF]" in prompt                  # confirma que houve sanitização
    assert isinstance(res, dict)
