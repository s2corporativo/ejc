# ── tests/test_ai_killswitch_gateway.py ──────────────────────────────────────
# P1-3 da auditoria integral (docs/auditoria-ejc/06-ia-rag-grafo-juridico.md §1.1).
#
# `AI_ENABLED` é o kill-switch de IA declarado na governança, mas o gateway só o
# consultava em `transcrever_audio()` e em `ia_disponivel()` — um HELPER que cada
# router precisava lembrar de chamar. A cobertura era parcial: `provas.py`,
# `teses.py`, `jurisprudencia_interna.py`, `prompts_juridicos.py` e `ia_saude.py`
# importam o gateway e não checavam nada. Com AI_ENABLED=false esses endpoints
# seguiam gerando e cobrando IA — o kill-switch não desligava a IA.
#
# O gate agora está nas TRÊS entradas de texto do gateway. Estes testes são
# COMPORTAMENTAIS de propósito: exercitam a chamada e provam que o provedor não
# é alcançado. Um teste de `inspect.getsource` provaria só que a linha existe.
import pytest
from fastapi import HTTPException

from app.services import ai_gateway as gw


@pytest.fixture
def ia_desligada(monkeypatch):
    """Desliga o kill-switch no SINGLETON de settings (mutação in-place, que é
    como a governança faz em runtime — nunca via get_settings.cache_clear)."""
    monkeypatch.setattr(gw.settings, "AI_ENABLED", False)


@pytest.fixture
def provedor_espiao(monkeypatch):
    """Registra qualquer tentativa de alcançar um provedor de IA."""
    chamou = {"provider": False}

    async def _nunca(*a, **k):
        chamou["provider"] = True
        raise AssertionError("provedor chamado com AI_ENABLED=false")

    monkeypatch.setattr(gw, "_chamar_provedor", _nunca)
    monkeypatch.setattr(gw, "_chamar_com_barreira", _nunca)
    return chamou


async def test_chat_bloqueado_com_ia_desligada(ia_desligada, provedor_espiao):
    with pytest.raises(HTTPException) as exc:
        await gw.chat([{"role": "user", "content": "oi"}])
    assert exc.value.status_code == 503
    assert "AI_ENABLED" in exc.value.detail
    assert provedor_espiao["provider"] is False


async def test_executar_tarefa_ia_bloqueado_com_ia_desligada(ia_desligada, provedor_espiao):
    """Entrada usada pelos routers de peça, triagem e análise de caso."""
    with pytest.raises(HTTPException) as exc:
        await gw.executar_tarefa_ia("analise_juridica", "resuma o caso")
    assert exc.value.status_code == 503
    assert provedor_espiao["provider"] is False


async def test_chat_agentico_bloqueado_com_ia_desligada(ia_desligada, provedor_espiao):
    """O caminho agêntico (tool-use) é o mais caro — e era o menos coberto."""
    with pytest.raises(HTTPException) as exc:
        await gw.chat_agentico([{"role": "user", "content": "oi"}], tools=[])
    assert exc.value.status_code == 503
    assert provedor_espiao["provider"] is False


async def test_gate_nao_dispara_com_ia_ligada(monkeypatch):
    """Guarda contra o erro oposto: o gate não pode barrar a operação normal.

    Com AI_ENABLED=true a chamada tem de PASSAR do gate — o que se prova
    alcançando o provedor falso. Sem isto, um `if` invertido passaria despercebido.
    """
    monkeypatch.setattr(gw.settings, "AI_ENABLED", True)
    alcancou = {"barreira": False}

    async def _fake_barreira(*a, **k):
        alcancou["barreira"] = True
        return "resp", "resp", {"input_tokens": 1, "output_tokens": 1, "model": "x"}, [], False

    monkeypatch.setattr(gw, "_chamar_com_barreira", _fake_barreira)
    await gw.chat([{"role": "user", "content": "oi"}])
    assert alcancou["barreira"] is True, "gate barrou com AI_ENABLED=true"


def test_pseudonimizacao_agentica_nao_carrega_o_gate():
    """O gate pertence à ENTRADA, não ao helper de sanitização.

    `_pseudonimizar_agentico` é uma primitiva da barreira LGPD, chamada de dentro
    do fluxo e reutilizável; colocar o kill-switch nela acopla duas políticas
    distintas (disponibilidade × privacidade) e deixa `chat_agentico` sem gate
    quando o helper não é acionado. Este teste trava a separação.
    """
    import inspect

    fonte = inspect.getsource(gw._pseudonimizar_agentico)
    assert "_exigir_ia_ligada" not in fonte
    assert "_exigir_ia_ligada" in inspect.getsource(gw.chat_agentico)
