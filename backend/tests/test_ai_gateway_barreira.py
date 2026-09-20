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


# ── Defesa em profundidade: resposta vazia nunca é "sucesso" (18/08) ────────
# Cada provider já levanta RuntimeError em resposta vazia (Ollama/Groq/
# Maritaca/Anthropic, corrigidos individualmente). _chamar_com_barreira é a
# FONTE ÚNICA que toda chamada atravessa — esta guarda pega qualquer provider,
# atual ou futuro, cujo caminho de resposta escape à checagem individual.

async def test_resposta_vazia_do_provider_levanta_em_vez_de_virar_sucesso(monkeypatch):
    async def _fake_vazio(*a, **k):
        return "", {"input_tokens": 1, "output_tokens": 0, "model": "x"}

    monkeypatch.setattr(gw, "_chamar_provedor", _fake_vazio)
    with pytest.raises(RuntimeError, match="resposta vazia"):
        await gw._chamar_com_barreira(
            "ollama", None, [{"role": "user", "content": "x"}], None, None, 0.2, 128
        )


async def test_resposta_so_com_espacos_tambem_e_barrada(monkeypatch):
    """Espaço/quebra de linha não é conteúdo — mesma guarda, .strip() cobre."""
    async def _fake_espacos(*a, **k):
        return "   \n  ", {"input_tokens": 1, "output_tokens": 0, "model": "x"}

    monkeypatch.setattr(gw, "_chamar_provedor", _fake_espacos)
    with pytest.raises(RuntimeError, match="resposta vazia"):
        await gw._chamar_com_barreira(
            "ollama", None, [{"role": "user", "content": "x"}], None, None, 0.2, 128
        )


async def test_a_barreira_de_resposta_vazia_aciona_o_fallback_da_cadeia(monkeypatch):
    """A guarda não é só um raise isolado: precisa reaproveitar o mecanismo de
    fallback já existente em chat() — provider vazio some, o próximo responde."""
    chamadas = {"n": 0}

    async def _fake_prov(provider, model, messages, temp, maxt):
        chamadas["n"] += 1
        if provider == "ollama":
            return "", {"input_tokens": 1, "output_tokens": 0, "model": "vazio"}
        return "resposta real", {"input_tokens": 1, "output_tokens": 5, "model": "bom"}

    monkeypatch.setattr(gw, "_chamar_provedor", _fake_prov)
    monkeypatch.setattr(gw, "_resolver_cadeia",
                        lambda *a, **k: [("ollama", None), ("groq", None)])
    monkeypatch.setattr(gw.settings, "AI_REQUIRE_SANITIZATION_FOR_EXTERNAL", False)

    resp = await gw.chat([{"role": "user", "content": "oi"}], task_type="resumo")
    assert resp.texto == "resposta real"
    assert resp.fallback_ativado is True
    assert chamadas["n"] == 2


# ── Auditoria 1-A achado #3: RuntimeError não ecoa str(e) cru com PII ──────
# Em LOCAL_COMPLETO (Ollama recebe PII real), exceções de SDK podem carregar
# trecho do request body no str(e). Truncar [:200] não sanitiza. O gateway
# deve construir RuntimeError só com `type(e).__name__` (+ HTTP status).
async def test_runtime_error_nao_ecoa_str_e_cru_com_pii(monkeypatch):
    """Simula exceção de SDK carregando PII no str(e) e verifica que o
    RuntimeError propagado pelo gateway NÃO contém o PII."""
    PII_NO_ERRO = "joão da silva cpf 123.456.789-00"

    async def _fake_prov_raises(provider, model, messages_envio, temp, maxt):
        # Em produção, SDKs podem ecoar trecho do request body na mensagem
        # de erro (ex.: timeout com payload, 4xx com echo). Simulamos aqui.
        raise RuntimeError(f"SDK error: request body was: {PII_NO_ERRO}")

    monkeypatch.setattr(gw, "_chamar_provedor", _fake_prov_raises)
    monkeypatch.setattr(gw, "_resolver_cadeia",
                        lambda *a, **k: [("anthropic", None), ("groq", None)])
    monkeypatch.setattr(gw.settings, "AI_REQUIRE_SANITIZATION_FOR_EXTERNAL", False)
    # Garante que o deadline da cadeia não dispara antes de todos os providers falharem
    monkeypatch.setattr(gw.settings, "AI_CHAIN_DEADLINE_SECONDS", 30)

    with pytest.raises(RuntimeError) as exc_info:
        await gw.chat([{"role": "user", "content": "oi"}], task_type="resumo")

    msg = str(exc_info.value)
    # O PII crú NÃO pode aparecer na mensagem que sobe ao chamador (e
    # eventualmente ao usuário via ai_service.py).
    assert PII_NO_ERRO not in msg, (
        f"RuntimeError vazou str(e) cru com PII: {msg!r}"
    )
    # Sanity: a mensagem ainda é útil para diagnóstico (contém a classe do erro)
    assert "RuntimeError" in msg or "erro" in msg.lower(), (
        f"RuntimeError sem informação de diagnóstico: {msg!r}"
    )
