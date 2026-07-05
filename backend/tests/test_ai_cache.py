"""Cache de resposta do AI Gateway (IA-04 Fase 5) — chave e opt-in.

Testes sem Redis: validam a estabilidade da chave e que o cache é NO-OP quando
desligado (default), garantindo zero mudança de comportamento fora do opt-in.
"""
from app.services import ai_cache


def _msgs(txt="oi"):
    return [{"role": "system", "content": "S"}, {"role": "user", "content": txt}]


def test_chave_estavel_para_mesma_requisicao():
    a = ai_cache.chave("analise_caso", _msgs(), temperature=0.1, max_tokens=100)
    b = ai_cache.chave("analise_caso", _msgs(), temperature=0.1, max_tokens=100)
    assert a == b
    assert a.startswith("ai:resp:")


def test_chave_independe_da_ordem_dos_params():
    a = ai_cache.chave("t", _msgs(), temperature=0.1, max_tokens=100)
    b = ai_cache.chave("t", _msgs(), max_tokens=100, temperature=0.1)
    assert a == b


def test_chave_muda_com_mensagem_task_ou_param():
    base = ai_cache.chave("t", _msgs("a"), temperature=0.1)
    assert ai_cache.chave("t", _msgs("b"), temperature=0.1) != base   # mensagem
    assert ai_cache.chave("outra", _msgs("a"), temperature=0.1) != base  # task
    assert ai_cache.chave("t", _msgs("a"), temperature=0.9) != base   # param


def test_desligado_por_default_e_no_op(monkeypatch):
    # Com o cache desligado (default), habilitado() é False e obter() não toca
    # Redis — retorna None sem exigir conexão.
    assert ai_cache.habilitado() is False


async def test_obter_desligado_retorna_none_sem_redis():
    valor = await ai_cache.obter("ai:resp:qualquer")
    assert valor is None


async def test_cache_hit_zera_tokens_e_custo(monkeypatch):
    # Um hit não gastou provedor: tokens/custo devem vir zerados (evita dupla
    # contagem no AILog/dashboards), com cache_hit=True e o texto cacheado.
    from app.services import ai_gateway
    from app.services import ai_cache as _c

    async def _fake_obter(_key):
        return {"texto": "resposta cacheada", "modelo": "m", "provedor": "groq",
                "input_tokens": 500, "output_tokens": 800, "custo_estimado_brl": 1.23}

    monkeypatch.setattr(_c, "obter", _fake_obter)
    resp = await ai_gateway.chat(
        messages=[{"role": "user", "content": "oi"}], task_type="chat_rapido",
    )
    assert resp.cache_hit is True
    assert resp.texto == "resposta cacheada"
    assert resp.input_tokens == 0 and resp.output_tokens == 0
    assert resp.custo_estimado_brl == 0.0
