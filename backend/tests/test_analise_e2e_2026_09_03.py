"""Regressões da análise ponta a ponta de 03/09/2026 (IA, rotas, ligações).

1. `credential_testers.testar_anthropic` deve ler a chave SÓ de Settings —
   o `or os.getenv(...)` fazia o Cofre reportar "configurada" com a chave
   antiga do `.env` depois de a credencial ter sido revogada (Settings="").
2. `GET /ai/status` (routers/ai_tools.py) deve refletir Settings e a fonte
   única de elegibilidade (`provider_registry`), não `os.getenv`: o painel
   ignorava o Cofre, os kill-switches por provedor e afirmava
   `modelo_complexo="(=rapido)"` fora do container.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.routers import ai_tools
from app.services import credential_testers as ct


def _run(coro):
    return asyncio.run(coro)


def test_testar_anthropic_ignora_env_apos_revogacao(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-chave-antiga-do-env")

    async def _nunca(*a, **k):  # pragma: no cover — não pode chegar à rede
        raise AssertionError("probe de rede não deveria ser chamado sem chave em Settings")

    monkeypatch.setattr(ct, "_probe", _nunca)
    estado, _msg = _run(ct.testar_anthropic())
    assert estado == ct.AUSENTE


def test_ai_status_le_settings_e_registry(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "AI_ENABLED", True)
    monkeypatch.setattr(s, "ANTHROPIC_MODEL_RAPIDO", "modelo-rapido-teste")
    monkeypatch.setattr(s, "ANTHROPIC_MODEL_COMPLEXO", "modelo-complexo-teste")
    # Ambiente contaminado: o painel antigo leria estes valores.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-so-no-env")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-so-no-env")
    monkeypatch.setenv("ANTHROPIC_MODEL_COMPLEXO", "(=rapido)")
    monkeypatch.setattr(ai_tools, "provider_elegivel", lambda p: p == "groq")
    monkeypatch.setattr(ai_tools, "motivo_inelegivel", lambda p: f"{p} inelegível (teste)")

    cu = SimpleNamespace(role="advogado")
    out = _run(ai_tools.status_ia(cu=cu))

    assert out["ai_enabled"] is True
    assert out["anthropic_configurado"] is False
    assert out["groq_configurado"] is True
    assert out["modelo_rapido"] == "modelo-rapido-teste"
    assert out["modelo_complexo"] == "modelo-complexo-teste"
    assert "groq" not in out["motivos_inelegiveis"]
    assert out["motivos_inelegiveis"]["anthropic"] == "anthropic inelegível (teste)"


def test_ai_status_bloqueia_cliente_externo_com_enum_real():
    """Gate do router era inerte: `str(UserRole.cliente_externo)` em 3.11 é
    "UserRole.cliente_externo" (enum `(str, Enum)` sem `__str__`), então a
    comparação com "cliente_externo" nunca batia — só o AuthMiddleware segurava
    (defesa em profundidade quebrada; revisão de segurança de 03/09/2026)."""
    from fastapi import HTTPException

    from app.models.user import User, UserRole

    cliente = User(role=UserRole.cliente_externo)
    with pytest.raises(HTTPException) as exc:
        _run(ai_tools.status_ia(cu=cliente))
    assert exc.value.status_code == 403
    # E o mesmo gate continua aceitando string (fakes de teste, claim do JWT).
    with pytest.raises(HTTPException):
        ai_tools._bloquear_cliente_externo(SimpleNamespace(role="cliente_externo"))
    ai_tools._bloquear_cliente_externo(SimpleNamespace(role=UserRole.advogado))


def test_ai_enabled_segue_settings_nao_env(monkeypatch):
    s = get_settings()
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setattr(s, "AI_ENABLED", False)
    assert ai_tools._ai_enabled() is False
    monkeypatch.setattr(s, "AI_ENABLED", True)
    assert ai_tools._ai_enabled() is True
