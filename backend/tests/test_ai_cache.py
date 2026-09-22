"""Cache de resposta do AI Gateway — chave, opt-in e proteção LGPD.

Testes sem Redis: validam estabilidade da chave, NO-OP quando desligado e o gate
que impede persistir respostas reidratadas com PII real.
"""

from types import SimpleNamespace

from app.services import ai_cache


def _msgs(txt="oi"):
    return [{"role": "system", "content": "S"}, {"role": "user", "content": txt}]


def test_chave_estavel_para_mesma_requisicao():
    a = ai_cache.chave("analise_caso", _msgs(), temperature=0.1, max_tokens=100)
    b = ai_cache.chave("analise_caso", _msgs(), temperature=0.1, max_tokens=100)
    assert a == b
    # analise_caso usa pseudonimização reversível → nunca persiste resposta.
    assert a.startswith("ai:nocache:")


def test_chave_independe_da_ordem_dos_params():
    a = ai_cache.chave("t", _msgs(), temperature=0.1, max_tokens=100)
    b = ai_cache.chave("t", _msgs(), max_tokens=100, temperature=0.1)
    assert a == b


def test_chave_muda_com_mensagem_task_ou_param():
    base = ai_cache.chave("t", _msgs("a"), temperature=0.1)
    assert ai_cache.chave("t", _msgs("b"), temperature=0.1) != base
    assert ai_cache.chave("outra", _msgs("a"), temperature=0.1) != base
    assert ai_cache.chave("t", _msgs("a"), temperature=0.9) != base


def test_tarefa_local_completo_nao_usa_cache(monkeypatch):
    """A6 (análise E2E 03/09): LOCAL_COMPLETO trafega em CLARO para o provedor
    local — a resposta pode carregar dado pessoal real e não pode ir ao Redis."""
    from app.services.ai.sanitization_policy import ModoSanitizacao

    monkeypatch.setattr(
        "app.services.ai.sanitization_policy.modo_para_task",
        lambda _task: ModoSanitizacao.LOCAL_COMPLETO,
    )
    k = ai_cache.chave("sigilo_local", _msgs())
    assert k.startswith("ai:nocache:")


def test_tarefa_mascaramento_pode_usar_cache(monkeypatch):
    """Só o mascaramento IRREVERSÍVEL continua cacheável."""
    from app.services.ai.sanitization_policy import ModoSanitizacao

    monkeypatch.setattr(
        "app.services.ai.sanitization_policy.modo_para_task",
        lambda _task: ModoSanitizacao.MASCARAMENTO,
    )
    k = ai_cache.chave("mascarada", _msgs())
    assert k.startswith("ai:resp:")


def test_ligado_por_default_g1_auditoria_20260920():
    """G1 (Auditoria Real 2026-09-20): cache IA default LIGADO — redução direta
    de custo/latência; rollback por env (AI_RESPONSE_CACHE_ENABLED=false)."""
    assert ai_cache.habilitado() is True


def test_desligado_por_env_e_no_op(monkeypatch):
    """Rollback documentado: flag OFF → habilitado() False, obter/gravar no-op."""
    monkeypatch.setattr(
        ai_cache,
        "get_settings",
        lambda: SimpleNamespace(AI_RESPONSE_CACHE_ENABLED=False),
    )
    assert ai_cache.habilitado() is False


async def test_obter_desligado_retorna_none_sem_redis():
    valor = await ai_cache.obter("ai:resp:qualquer")
    assert valor is None


async def test_nocache_nao_abre_redis_mesmo_se_flag_ligada(monkeypatch):
    chamado = False

    async def _nao_abrir():
        nonlocal chamado
        chamado = True
        raise AssertionError("Redis não deve ser aberto para resposta reidratável")

    monkeypatch.setattr(ai_cache, "habilitado", lambda: True)
    monkeypatch.setattr(ai_cache, "_cliente", _nao_abrir)
    chave = ai_cache.chave("analise_caso", _msgs("CPF 123.456.789-09"))
    assert await ai_cache.obter(chave) is None
    await ai_cache.gravar(chave, {"texto": "PII real"})
    assert chamado is False


async def test_cache_hit_zera_tokens_e_custo(monkeypatch):
    # Simula tarefa MASCARAMENTO (cacheável) e uma cadeia ELEGÍVEL (A6: o cache
    # só é consultado depois de confirmada a cadeia) para exercitar o hit.
    from app.services import ai_gateway
    from app.services import ai_cache as _c
    from app.services.ai.sanitization_policy import ModoSanitizacao

    monkeypatch.setattr(
        "app.services.ai.sanitization_policy.modo_para_task",
        lambda _task: ModoSanitizacao.MASCARAMENTO,
    )
    monkeypatch.setattr(ai_gateway.settings, "AI_ENABLED", True)
    monkeypatch.setattr(ai_gateway.settings, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(ai_gateway.settings, "AI_PROVIDER", "auto")

    async def _fake_obter(_key):
        return {
            "texto": "resposta cacheada",
            "modelo": "m",
            "provedor": "ollama",
            "input_tokens": 500,
            "output_tokens": 800,
            "custo_estimado_brl": 1.23,
            "fallback_ativado": True,
            "fallback_motivo": "groq: RuntimeError",
        }

    monkeypatch.setattr(_c, "obter", _fake_obter)
    resp = await ai_gateway.chat(
        messages=[{"role": "user", "content": "oi"}],
        task_type="chat_rapido",
    )
    assert resp.cache_hit is True
    assert resp.texto == "resposta cacheada"
    assert resp.input_tokens == 0 and resp.output_tokens == 0
    assert resp.custo_estimado_brl == 0.0
    assert resp.fallback_ativado is True
    assert resp.fallback_motivo == "groq: RuntimeError"



async def test_cache_write_preserva_metadados_de_fallback_chat(monkeypatch):
    from app.services import ai_gateway
    from app.services import ai_cache as _c
    from app.services.ai.sanitization_policy import ModoSanitizacao

    monkeypatch.setattr(
        "app.services.ai.sanitization_policy.modo_para_task",
        lambda _task: ModoSanitizacao.MASCARAMENTO,
    )
    s = ai_gateway.settings
    monkeypatch.setattr(s, "AI_ENABLED", True)
    monkeypatch.setattr(s, "AI_PROVIDER", "auto")
    monkeypatch.setattr(s, "AI_PROVIDER_PRIORITY", "groq,ollama")
    monkeypatch.setattr(s, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(s, "GROQ_ENABLED", True)
    monkeypatch.setattr(s, "GROQ_API_KEY", "gk")
    monkeypatch.setattr(s, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(s, "ANTHROPIC_AUTO_ROUTING_ENABLED", False)

    chamadas = []

    async def fake_provider(provider, model, messages, temperature, max_tokens):
        chamadas.append(provider)
        if provider == "groq":
            raise RuntimeError("falha simulada")
        return "ok", {"model": model or provider, "input_tokens": 1, "output_tokens": 1}

    gravado = {}

    async def fake_obter(_key):
        return None

    async def fake_gravar(_key, dados):
        gravado.update(dados)

    monkeypatch.setattr(ai_gateway, "_chamar_provedor", fake_provider)
    monkeypatch.setattr(_c, "obter", fake_obter)
    monkeypatch.setattr(_c, "gravar", fake_gravar)

    resp = await ai_gateway.chat(
        [{"role": "user", "content": "resuma"}],
        task_type="resumo",
    )
    assert chamadas[:2] == ["groq", "ollama"]
    assert resp.fallback_ativado is True
    assert gravado["fallback_ativado"] is True
    assert gravado["fallback_motivo"].startswith("groq:")


async def test_cache_write_preserva_metadados_de_fallback_executar_tarefa(monkeypatch):
    from app.services import ai_gateway
    from app.services import ai_cache as _c
    from app.services.ai.sanitization_policy import ModoSanitizacao
    from app.services.system_prompts import TarefaIA

    monkeypatch.setattr(
        "app.services.ai.sanitization_policy.modo_para_task",
        lambda _task: ModoSanitizacao.MASCARAMENTO,
    )
    st = ai_gateway.settings
    monkeypatch.setattr(st, "AI_ENABLED", True)
    monkeypatch.setattr(st, "AI_PROVIDER", "auto")
    monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(st, "GROQ_ENABLED", True)
    monkeypatch.setattr(st, "GROQ_API_KEY", "gk")
    monkeypatch.setattr(st, "OLLAMA_ENABLED", True)

    chamadas = []
    gravado = {}

    async def fake_provider(provider, model, messages, temperature, max_tokens):
        chamadas.append(provider)
        if provider == "groq":
            raise RuntimeError("falha simulada")
        return "ok", {"model": model or provider, "input_tokens": 1, "output_tokens": 1}

    async def fake_obter(_key):
        return None

    async def fake_gravar(_key, dados):
        gravado.update(dados)

    monkeypatch.setattr(ai_gateway, "_chamar_provedor", fake_provider)
    monkeypatch.setattr(_c, "obter", fake_obter)
    monkeypatch.setattr(_c, "gravar", fake_gravar)

    out = await ai_gateway.executar_tarefa_ia(TarefaIA.RESUMO, "resuma este andamento")
    assert chamadas[:2] == ["groq", "ollama"]
    assert out["fallback_ativado"] is True
    assert out["fallback_motivo"].startswith("groq:")
    assert gravado["fallback_ativado"] is True
    assert gravado["fallback_motivo"].startswith("groq:")


async def test_cache_hit_preserva_metadados_de_fallback_executar_tarefa(monkeypatch):
    from app.services import ai_gateway
    from app.services import ai_cache as _c
    from app.services.ai.sanitization_policy import ModoSanitizacao
    from app.services.system_prompts import TarefaIA

    monkeypatch.setattr(
        "app.services.ai.sanitization_policy.modo_para_task",
        lambda _task: ModoSanitizacao.MASCARAMENTO,
    )
    st = ai_gateway.settings
    monkeypatch.setattr(st, "AI_ENABLED", True)
    monkeypatch.setattr(st, "AI_PROVIDER", "auto")
    monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(st, "GROQ_ENABLED", True)
    monkeypatch.setattr(st, "GROQ_API_KEY", "gk")
    monkeypatch.setattr(st, "OLLAMA_ENABLED", True)

    async def fake_obter(_key):
        return {
            "texto": "resposta cacheada",
            "modelo": "ollama/modelo-local",
            "provedor": "ollama",
            "fallback_ativado": True,
            "fallback_motivo": "groq: RuntimeError",
        }

    monkeypatch.setattr(_c, "obter", fake_obter)

    out = await ai_gateway.executar_tarefa_ia(TarefaIA.RESUMO, "resuma este andamento")
    assert out["cache_hit"] is True
    assert out["provider"] == "ollama"
    assert out["fallback_ativado"] is True
    assert out["fallback_motivo"] == "groq: RuntimeError"
