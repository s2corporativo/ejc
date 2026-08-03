"""Cache HIT em executar_tarefa_ia grava AILog (IA-007).

Antes, um cache hit devolvia a resposta com tokens/custo zerados e NENHUM
AILog — correto o custo zero (não houve chamada real), mas a lacuna de
auditoria era total: "quantas vezes a tarefa X rodou" subcontava exatamente
as chamadas mais REPETIDAS, que são as que o cache existe para servir.

Sem banco: `db`/`registrar_ai_log` são dublês; o que se prova é que a função
TENTA gravar o log, com os campos certos, e nunca deixa uma falha de log
quebrar a resposta do cache (que já está pronta e não deveria bater no
provedor de novo por causa disso).
"""

from __future__ import annotations

from app.services import ai_gateway as gw
from app.services.system_prompts.router import TarefaIA


def _cached_payload():
    return {"texto": "resposta cacheada", "modelo": "anthropic/claude", "provedor": "anthropic"}


async def test_cache_hit_grava_ailog_com_tokens_e_custo_zerados(monkeypatch):
    chamadas = []

    async def _fake_registrar(db, **kw):
        chamadas.append(kw)
        return "log-id"

    async def _fake_obter(_chave):
        return _cached_payload()

    monkeypatch.setattr("app.services.ai_cache.obter", _fake_obter)
    monkeypatch.setattr("app.services.ai_guard.registrar_ai_log", _fake_registrar)

    resultado = await gw.executar_tarefa_ia(
        TarefaIA.ANALISE_CASO, "mensagem do advogado",
        case_id="caso-1", user_id="user-1", db=object(),
    )

    assert resultado["cache_hit"] is True
    assert resultado["conteudo"] == "resposta cacheada"
    assert len(chamadas) == 1
    kw = chamadas[0]
    assert kw["tokens_input"] == 0 and kw["tokens_output"] == 0
    assert kw["custo_estimado"] == 0.0
    assert kw["case_id"] == "caso-1"
    assert "cache_hit" in kw["fontes_rag"]
    assert kw["resposta"] == "resposta cacheada"


async def test_cache_hit_sem_db_ou_user_id_nao_tenta_gravar(monkeypatch):
    """Mesma guarda do caminho sem cache (`if db is not None and user_id`):
    chamador que não informa os dois não pode estourar aqui."""
    chamou = {"registrar": False}

    async def _fake_registrar(db, **kw):
        chamou["registrar"] = True
        return "log-id"

    async def _fake_obter(_chave):
        return _cached_payload()

    monkeypatch.setattr("app.services.ai_cache.obter", _fake_obter)
    monkeypatch.setattr("app.services.ai_guard.registrar_ai_log", _fake_registrar)

    resultado = await gw.executar_tarefa_ia(TarefaIA.ANALISE_CASO, "mensagem sem contexto de auditoria")

    assert resultado["cache_hit"] is True
    assert chamou["registrar"] is False


async def test_falha_ao_gravar_ailog_nao_derruba_a_resposta_do_cache(monkeypatch):
    """A resposta já está pronta (veio do cache); falha de log é best-effort
    aqui — bater no provedor de novo por causa disso seria pior que a lacuna
    de auditoria que esta correção resolve."""
    async def _fake_registrar_quebrado(db, **kw):
        raise RuntimeError("banco fora do ar")

    async def _fake_obter(_chave):
        return _cached_payload()

    monkeypatch.setattr("app.services.ai_cache.obter", _fake_obter)
    monkeypatch.setattr("app.services.ai_guard.registrar_ai_log", _fake_registrar_quebrado)

    resultado = await gw.executar_tarefa_ia(
        TarefaIA.ANALISE_CASO, "mensagem", case_id="c1", user_id="u1", db=object(),
    )
    assert resultado["cache_hit"] is True
    assert resultado["conteudo"] == "resposta cacheada"
