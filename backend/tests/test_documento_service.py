"""IA-01 (revisado) — importação de documento: híbrido determinístico + LLM.

Contrato (pós-correção do intake + sanitização REATIVADA na auditoria — LGPD
art. 33/46: PII não sai em claro do VPS para provedor externo):
  • O dado pessoal EXATO (CPF/nº CNJ/e-mail/...) é extraído LOCALMENTE por
    regex determinística (extracao_estruturada) — sem LLM — e devolvido em
    `dados_estruturados` em TODOS os caminhos de retorno.
  • O LLM (cadeia automática do gateway: ollama→anthropic→groq, com fallback)
    recebe o texto SANITIZADO — sanitizar_pii mascara CPF/CNPJ/nº de processo
    ([CPF]/[CNPJ]/[PROCESSO]), e o gateway ainda aplica _sanitizar_messages_
    externo como segunda barreira antes de qualquer provedor externo.
  • A flag INTAKE_EXTERNAL_FALLBACK continua decidindo SE provedores externos
    podem ser usados no intake (off = só Ollama local, fail-closed).
  • Se TODA a cadeia LLM falhar, a importação NÃO quebra: retorna ok=True com
    analise_llm_indisponivel=True + dados_estruturados + texto OCR.
Estes testes travam esses invariantes contra regressão."""


class _R:
    def __init__(self, texto, provedor="ollama", modelo="llama3"):
        self.texto, self.provedor, self.modelo = texto, provedor, modelo


_DOC = ("Cliente Maria Souza, CPF 987.654.321-00, processo "
        "1234567-89.2020.8.13.0024, em discussao contratual.")


def _mock_ocr(monkeypatch):
    monkeypatch.setattr(
        "app.services.ocr_service.extrair_texto",
        lambda *a, **k: _DOC,
    )


async def test_llm_recebe_texto_sanitizado_e_usa_cadeia_com_fallback(monkeypatch):
    """(a) Caminho feliz: sem provider_override fixo (cadeia automática do
    gateway) e o prompt chega SANITIZADO (CPF/processo mascarados)."""
    captured = {}
    _mock_ocr(monkeypatch)

    async def fake_chat(*, messages, provider_override=None, **kw):
        captured["provider_override"] = provider_override
        captured["task_type"] = kw.get("task_type")
        captured["user"] = messages[1]["content"]
        return _R('{"ok": true}')

    monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)

    from app.services.documento_service import extrair_e_analisar
    r = await extrair_e_analisar("/fake.pdf", "application/pdf", db=None, enriquecer_rag=False)

    # Cadeia automática (ollama→anthropic→groq no TASK_ROUTING) — nada fixado.
    assert captured["provider_override"] is None
    assert captured["task_type"] == "analise_juridica"
    # Sanitização reativada (LGPD): o documento vai MASCARADO ao modelo.
    assert "987.654.321-00" not in captured["user"]
    assert "1234567-89.2020.8.13.0024" not in captured["user"]
    assert "[CPF]" in captured["user"]
    assert "[PROCESSO]" in captured["user"]
    assert r["ok"] is True


async def test_fallback_externo_ve_texto_sanitizado(monkeypatch):
    """(b) Ollama cai → provedor externo assume e recebe o MESMO texto
    SANITIZADO (LGPD: PII não sai em claro para provedor externo)."""
    captured = {}
    _mock_ocr(monkeypatch)

    async def fake_chat(*, messages, provider_override=None, **kw):
        captured["provider_override"] = provider_override
        captured["user"] = messages[1]["content"]
        # Simula gateway respondendo pelo provedor externo após fallback.
        return _R('{"classificacao": {"area": "civil"}}',
                  provedor="anthropic", modelo="claude")

    monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)

    from app.services.documento_service import extrair_e_analisar
    r = await extrair_e_analisar("/fake.pdf", "application/pdf", db=None, enriquecer_rag=False)

    assert r["ok"] is True
    assert r["_modelo"] == "anthropic/claude"
    # O provedor externo recebe o texto sanitizado (CPF mascarado).
    assert captured["provider_override"] is None
    assert "987.654.321-00" not in captured["user"]
    assert "[CPF]" in captured["user"]


async def test_cadeia_toda_falha_degrada_com_extracao_deterministica(monkeypatch):
    """(c) TODA a cadeia LLM falha → ok=True com dados_estruturados + aviso.
    A importação nunca mais retorna erro seco por indisponibilidade de IA."""
    _mock_ocr(monkeypatch)

    async def fake_chat(**kw):
        raise RuntimeError("Todos os provedores falharam para task=analise_juridica")

    monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)

    from app.services.documento_service import extrair_e_analisar
    r = await extrair_e_analisar("/fake.pdf", "application/pdf", db=None, enriquecer_rag=False)

    assert r["ok"] is True
    assert r["analise_llm_indisponivel"] is True
    assert "indispon" in r["aviso_llm"].lower()
    # Extração determinística local presente com o dado EXATO (regex, sem IA).
    de = r["dados_estruturados"]
    assert de["cpfs"][0]["valor"] == "987.654.321-00"
    assert de["processos_cnj"][0]["valor"] == "1234567-89.2020.8.13.0024"
    # Texto devolvido à IA é o SANITIZADO (o exato vive em dados_estruturados).
    assert "987.654.321-00" not in r["texto_extraido"]
    assert "[CPF]" in r["texto_extraido"]


async def test_dados_estruturados_presentes_em_todos_os_retornos(monkeypatch):
    """(d) dados_estruturados aparece no sucesso pleno E no parcial (JSON da
    IA ilegível), sempre com os valores exatos extraídos localmente."""
    _mock_ocr(monkeypatch)
    from app.services.documento_service import extrair_e_analisar

    async def chat_ok(**kw):
        return _R('{"classificacao": {"area": "civil"}}')

    monkeypatch.setattr("app.services.ai_gateway.chat", chat_ok)
    r_ok = await extrair_e_analisar("/fake.pdf", "application/pdf", db=None, enriquecer_rag=False)
    assert r_ok["ok"] is True
    assert r_ok["dados_estruturados"]["cpfs"][0]["valor"] == "987.654.321-00"

    async def chat_ruido(**kw):
        return _R("resposta sem JSON algum")

    monkeypatch.setattr("app.services.ai_gateway.chat", chat_ruido)
    r_parcial = await extrair_e_analisar("/fake.pdf", "application/pdf", db=None, enriquecer_rag=False)
    assert r_parcial["ok"] is True and r_parcial.get("parcial") is True
    assert r_parcial["dados_estruturados"]["processos_cnj"][0]["valor"] == \
        "1234567-89.2020.8.13.0024"


# ── Mitigações LGPD (PR #55): barreira REAL, flag INTAKE_EXTERNAL_FALLBACK ──


def _settings():
    from app.services import ai_gateway
    return ai_gateway.settings  # mesmo objeto cacheado de get_settings()


async def test_gateway_real_provider_externo_recebe_texto_sanitizado(monkeypatch):
    """(e) Integração com o gateway REAL (sem mock do chat), Ollama
    desabilitado → cadeia cai no Anthropic; mockamos APENAS
    anthropic_provider.chat. Com a sanitização reativada, o conteúdo chega
    MASCARADO ao provider externo (sanitizar_pii no intake +
    _sanitizar_messages_externo como segunda barreira, LGPD art. 33/46)."""
    _mock_ocr(monkeypatch)
    s = _settings()
    monkeypatch.setattr(s, "INTAKE_EXTERNAL_FALLBACK", True)
    monkeypatch.setattr(s, "OLLAMA_ENABLED", False)
    monkeypatch.setattr(s, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(s, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(s, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(s, "AI_REQUIRE_SANITIZATION_FOR_EXTERNAL", True)
    monkeypatch.setattr(s, "GROQ_API_KEY", "")
    monkeypatch.setattr(s, "ROTEAMENTO_INTELIGENTE_ENABLED", False)

    captured = {}

    # `timeout_s` (orçamento restante da cadeia) é kwarg novo do provider —
    # `**kw` mantém o fake compatível com futuras extensões da assinatura.
    async def fake_anthropic_chat(messages, model, temperature, max_tokens, **kw):
        captured["messages"] = messages
        return ('{"classificacao": {"area": "civil"}}',
                {"model": "claude-opus-4-8", "input_tokens": 11, "output_tokens": 7})

    from app.services.providers import anthropic_provider
    monkeypatch.setattr(anthropic_provider, "chat", fake_anthropic_chat)

    from app.services.documento_service import extrair_e_analisar
    r = await extrair_e_analisar("/fake.pdf", "application/pdf", db=None, enriquecer_rag=False)

    assert r["ok"] is True
    assert r["_modelo"] == "anthropic/claude-opus-4-8"
    # O que o provider EXTERNO recebeu (pós-cadeia + barreira real):
    todo = "\n".join((m.get("content") or "") for m in captured["messages"])
    assert "987.654.321-00" not in todo
    assert "1234567-89.2020.8.13.0024" not in todo
    assert "[CPF]" in todo
    # Dado exato continua vindo da extração determinística LOCAL.
    assert r["dados_estruturados"]["cpfs"][0]["valor"] == "987.654.321-00"


async def test_flag_false_volta_ao_fail_closed_com_erro_claro(monkeypatch):
    """(f) INTAKE_EXTERNAL_FALLBACK=false → só Ollama local; Ollama caiu →
    ok=False com mensagem citando a flag; NENHUM provedor externo é tocado."""
    _mock_ocr(monkeypatch)
    s = _settings()
    monkeypatch.setattr(s, "INTAKE_EXTERNAL_FALLBACK", False)
    monkeypatch.setattr(s, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(s, "ROTEAMENTO_INTELIGENTE_ENABLED", False)

    async def ollama_caiu(*a, **k):
        raise RuntimeError("connection refused")

    async def externo_proibido(*a, **k):
        raise AssertionError("provedor externo NÃO pode ser chamado com a flag off")

    from app.services.providers import ollama_provider, anthropic_provider, groq_provider
    monkeypatch.setattr(ollama_provider, "chat", ollama_caiu)
    monkeypatch.setattr(anthropic_provider, "chat", externo_proibido)
    monkeypatch.setattr(groq_provider, "chat", externo_proibido)

    from app.services.documento_service import extrair_e_analisar
    r = await extrair_e_analisar("/fake.pdf", "application/pdf", db=None, enriquecer_rag=False)

    assert r["ok"] is False
    assert "INTAKE_EXTERNAL_FALLBACK" in r["erro"]


async def test_flag_false_sem_ollama_habilitado_erra_antes_do_gateway(monkeypatch):
    """(g) Flag off + OLLAMA_ENABLED=false → erro imediato (o gateway trataria
    o override inelegível caindo na cadeia automática EXTERNA — proibido)."""
    _mock_ocr(monkeypatch)
    s = _settings()
    monkeypatch.setattr(s, "INTAKE_EXTERNAL_FALLBACK", False)
    monkeypatch.setattr(s, "OLLAMA_ENABLED", False)

    async def gateway_nao_chamado(**kw):
        raise AssertionError("ai_gateway.chat não deveria ser chamado")

    monkeypatch.setattr("app.services.ai_gateway.chat", gateway_nao_chamado)

    from app.services.documento_service import extrair_e_analisar
    r = await extrair_e_analisar("/fake.pdf", "application/pdf", db=None, enriquecer_rag=False)
    assert r["ok"] is False
    assert "INTAKE_EXTERNAL_FALLBACK" in r["erro"]


async def test_ailog_da_chamada_principal_do_intake(monkeypatch):
    """(h) Art. 37 LGPD: com db+user_id, o intake grava AILog com provedor,
    modelo, tokens e o prompt REAL enviado (já sanitizado)."""
    _mock_ocr(monkeypatch)

    class _RTok(_R):
        input_tokens = 42
        output_tokens = 17
        custo_estimado_brl = 0.0

    async def fake_chat(**kw):
        return _RTok('{"classificacao": {"area": "civil"}}',
                     provedor="anthropic", modelo="claude-opus-4-8")

    monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)

    class _FakeDB:
        def __init__(self):
            self.added = []

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            pass

    db = _FakeDB()
    from app.services.documento_service import extrair_e_analisar
    r = await extrair_e_analisar("/fake.pdf", "application/pdf", db=db,
                                 enriquecer_rag=False, user_id="u-1")

    assert r["ok"] is True
    assert len(db.added) == 1
    log = db.added[0]
    assert r["intake_log_id"] == log.id
    assert log.user_id == "u-1"
    assert log.modelo == "anthropic/claude-opus-4-8"
    assert log.tokens_input == 42 and log.tokens_output == 17
    # Prompt persistido é o REAL enviado (sanitizado — CPF mascarado).
    assert "987.654.321-00" not in log.prompt_sanitizado
    assert "[CPF]" in log.prompt_sanitizado
    assert log.pii_removida is True


async def test_ocr_roda_fora_da_thread_do_event_loop(monkeypatch):
    """Pente fino E2E 30/08 §5.4: a extração de texto (PyMuPDF/pytesseract,
    CPU-bound) NÃO pode rodar na thread do event loop — com worker único ela
    congelava o sistema inteiro durante uma análise. O contrato aqui é que
    `extrair_e_analisar` despacha o OCR via thread (asyncio.to_thread)."""
    import threading

    visto = {}

    def fake_ocr(*a, **k):
        visto["thread"] = threading.current_thread()
        return _DOC

    monkeypatch.setattr("app.services.ocr_service.extrair_texto", fake_ocr)

    async def fake_chat(**kw):
        return _R('{"classificacao": {"area": "civil"}}')

    monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)

    from app.services.documento_service import extrair_e_analisar
    r = await extrair_e_analisar("/fake.pdf", "application/pdf", db=None, enriquecer_rag=False)

    assert r["ok"] is True
    assert visto["thread"] is not threading.main_thread(), (
        "extração de texto executou na thread do event loop — deve ir para "
        "thread worker (asyncio.to_thread)"
    )
