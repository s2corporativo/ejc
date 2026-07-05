"""Análise estratégica (Fase 4 / 4C) — prompt vai ao LLM SANITIZADO.

Sanitização de PII reativada (auditoria — LGPD art. 33/46): o prompt enviado
ao gateway tem CPF/nº de processo/nome mascarados ([CPF]/[PROCESSO]/[PARTE_1])
antes de qualquer provedor externo. O escritório trabalha o dado exato pela
extração local; a IA raciocina sobre a versão mascarada.
"""


class _Resp:
    def __init__(self, texto):
        self.texto = texto


async def test_prompt_vai_ao_llm_sanitizado(monkeypatch):
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
    assert "123.456.789-09" not in prompt          # CPF mascarado
    assert "1234567-89.2020.8.13.0024" not in prompt  # nº processo mascarado
    assert "Joao da Silva" not in prompt           # nome mascarado
    assert "[CPF]" in prompt                        # placeholders de máscara
    assert "[PROCESSO]" in prompt
    assert "[PARTE_1]" in prompt
    assert isinstance(res, dict)
