"""Provedores de IA: habilitação, diagnóstico e resposta vazia.

Auditoria de provedores (18/08): as três lacunas que impediam operar o módulo
com confiança — não saber POR QUE um provedor está fora, não poder desligar o
Groq sem apagar a chave, e o Ollama tratar resposta vazia como sucesso.
"""
import pytest

from app.services.ai import provider_registry as pr


# ── diagnóstico: por que o provedor está fora ───────────────────────────────

def test_motivo_aponta_chave_ausente(override_settings):
    override_settings(ANTHROPIC_ENABLED=True, ANTHROPIC_API_KEY="",
              AI_EXTERNAL_PROVIDERS_ALLOWED=True)
    assert pr.provider_elegivel("anthropic") is False
    assert "ANTHROPIC_API_KEY ausente" in pr.motivo_inelegivel("anthropic")


def test_motivo_aponta_kill_switch_global(override_settings):
    override_settings(MARITACA_ENABLED=True, MARITACA_API_KEY="k",
              AI_EXTERNAL_PROVIDERS_ALLOWED=False)
    motivo = pr.motivo_inelegivel("maritaca")
    assert "kill-switch" in motivo and "AI_EXTERNAL_PROVIDERS_ALLOWED" in motivo


def test_motivo_acumula_faltas(override_settings):
    override_settings(GROQ_ENABLED=False, GROQ_API_KEY="",
              AI_EXTERNAL_PROVIDERS_ALLOWED=False)
    motivo = pr.motivo_inelegivel("groq")
    assert "GROQ_ENABLED=false" in motivo
    assert "GROQ_API_KEY ausente" in motivo
    assert "kill-switch" in motivo


def test_provedor_elegivel_nao_tem_motivo(override_settings):
    override_settings(OLLAMA_ENABLED=True)
    assert pr.provider_elegivel("ollama") is True
    assert pr.motivo_inelegivel("ollama") is None


def test_provedor_desconhecido_e_inelegivel():
    assert pr.provider_elegivel("openai") is False
    assert "não suportado" in pr.motivo_inelegivel("openai")


# ── simetria do kill-switch por provedor ────────────────────────────────────

def test_groq_pode_ser_desligado_sem_apagar_a_chave(override_settings):
    """Antes, desligar o Groq exigia remover GROQ_API_KEY."""
    override_settings(GROQ_ENABLED=False, GROQ_API_KEY="chave-valida",
              AI_EXTERNAL_PROVIDERS_ALLOWED=True)
    assert pr.provider_elegivel("groq") is False


def test_todo_provedor_suportado_tem_flag_de_habilitacao():
    from app.core.config import get_settings

    s = get_settings()
    for flag in ("OLLAMA_ENABLED", "ANTHROPIC_ENABLED",
                 "MARITACA_ENABLED", "GROQ_ENABLED"):
        assert hasattr(s, flag), f"{flag} ausente"


# ── resposta vazia não é sucesso ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ollama_resposta_vazia_levanta_para_acionar_fallback(monkeypatch):
    """O Ollama é o primeiro da cadeia: devolver "" como sucesso fazia a resposta
    vazia virar resposta final, sem o gateway cair para o próximo provedor."""
    import httpx

    from app.services.providers import ollama_provider

    class _Resp:
        def raise_for_status(self): ...
        def json(self):
            return {"message": {"content": "   "}, "eval_count": 0}

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **k: _Client())
    with pytest.raises(RuntimeError, match="resposta vazia"):
        await ollama_provider.chat([{"role": "user", "content": "oi"}], model="x")
