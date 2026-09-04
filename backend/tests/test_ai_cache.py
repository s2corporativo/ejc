"""Cache de resposta do AI Gateway — chave, opt-in e proteção LGPD.

Testes sem Redis: validam estabilidade da chave, NO-OP quando desligado e o gate
que impede persistir respostas reidratadas com PII real.
"""
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


def test_desligado_por_default_e_no_op():
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
        return {"texto": "resposta cacheada", "modelo": "m", "provedor": "ollama",
                "input_tokens": 500, "output_tokens": 800, "custo_estimado_brl": 1.23}

    monkeypatch.setattr(_c, "obter", _fake_obter)
    resp = await ai_gateway.chat(
        messages=[{"role": "user", "content": "oi"}], task_type="chat_rapido",
    )
    assert resp.cache_hit is True
    assert resp.texto == "resposta cacheada"
    assert resp.input_tokens == 0 and resp.output_tokens == 0
    assert resp.custo_estimado_brl == 0.0
