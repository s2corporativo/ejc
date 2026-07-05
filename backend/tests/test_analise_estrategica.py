"""Análise estratégica (Fase 4 / 4C) — prompt vai ao LLM SEM mascaramento.

Sanitização de PII desativada (decisão do titular, 2026-07-05): o prompt
enviado ao gateway carrega CPF, número de processo e nomes como digitados,
para a IA trabalhar o caso com os dados reais.
"""


class _Resp:
    def __init__(self, texto):
        self.texto = texto


async def test_prompt_vai_ao_llm_sem_mascaramento(monkeypatch):
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
    assert "123.456.789-09" in prompt          # CPF em claro
    assert "1234567-89.2020.8.13.0024" in prompt  # nº processo em claro
    assert "Joao da Silva" in prompt           # nome em claro
    assert "[CPF]" not in prompt               # nenhum placeholder de máscara
    assert isinstance(res, dict)
