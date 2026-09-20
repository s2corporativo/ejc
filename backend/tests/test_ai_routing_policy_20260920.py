"""Política operacional de provedores — decisão 20/09/2026.

Contrato:
- automático corriqueiro -> Groq;
- automático de leitura/análise/pesquisa -> Maritaca;
- Claude não entra automaticamente;
- Claude continua disponível quando solicitado explicitamente;
- a escolha explícita continua sujeita à elegibilidade/LGPD.
"""
from types import SimpleNamespace

from app.schemas.ai import ConversarRequest
from app.services.ai import provider_policy as pp


def _settings():
    return SimpleNamespace(
        AI_PROVIDER_PRIORITY="groq,maritaca,ollama,anthropic",
        ANTHROPIC_AUTO_ROUTING_ENABLED=False,
        AI_REQUIRE_SANITIZATION_FOR_EXTERNAL=False,
        AI_REQUIRE_HITL=True,
        AI_ENABLED=True,
    )


def _policy(monkeypatch):
    monkeypatch.setattr(pp, "get_settings", _settings)
    monkeypatch.setattr(
        pp.AIProviderPolicy,
        "_elegivel",
        staticmethod(lambda provider: provider in {"groq", "maritaca", "anthropic", "ollama"}),
    )
    return pp.AIProviderPolicy()


def test_auto_corriqueiro_prioriza_groq_e_exclui_claude(monkeypatch):
    decisao = _policy(monkeypatch).avaliar(
        "resuma este andamento", "resumo", ja_sanitizado=True,
    )
    providers = [p for p, _ in decisao.provider_chain]
    assert providers[0] == "groq"
    assert "anthropic" not in providers


def test_auto_merito_prioriza_maritaca_e_exclui_claude(monkeypatch):
    decisao = _policy(monkeypatch).avaliar(
        "pesquise jurisprudência e analise a tese",
        "analise_juridica",
        ja_sanitizado=True,
        exige_fonte=True,
    )
    providers = [p for p, _ in decisao.provider_chain]
    assert providers[0] == "maritaca"
    assert "anthropic" not in providers


def test_merito_nao_usa_groq_se_maritaca_indisponivel(monkeypatch):
    policy = _policy(monkeypatch)
    monkeypatch.setattr(
        pp.AIProviderPolicy,
        "_elegivel",
        staticmethod(lambda provider: provider in {"groq", "anthropic"}),
    )
    decisao = policy.avaliar(
        "analise juridicamente esta tese", "analise_juridica", ja_sanitizado=True,
    )
    assert decisao.permitido is False
    assert all(p != "groq" for p, _ in decisao.provider_chain)


def test_rotina_nao_usa_maritaca_se_groq_indisponivel(monkeypatch):
    policy = _policy(monkeypatch)
    monkeypatch.setattr(
        pp.AIProviderPolicy,
        "_elegivel",
        staticmethod(lambda provider: provider in {"maritaca", "anthropic"}),
    )
    decisao = policy.avaliar("resuma este texto", "resumo", ja_sanitizado=True)
    assert decisao.permitido is False
    assert all(p != "maritaca" for p, _ in decisao.provider_chain)


def test_area_juridica_direta_e_tratada_como_merito(monkeypatch):
    decisao = _policy(monkeypatch).avaliar(
        "analise defesa criminal", "criminal", ja_sanitizado=True,
    )
    assert [p for p, _ in decisao.provider_chain][0] == "maritaca"
    assert "groq" not in [p for p, _ in decisao.provider_chain]


def test_honorarios_e_tratado_como_rotina(monkeypatch):
    decisao = _policy(monkeypatch).avaliar(
        "consulte honorarios", "honorarios", ja_sanitizado=True,
    )
    assert [p for p, _ in decisao.provider_chain][0] == "groq"
    assert "maritaca" not in [p for p, _ in decisao.provider_chain]


def test_claude_entra_quando_solicitado_explicitamente(monkeypatch):
    decisao = _policy(monkeypatch).avaliar(
        "faça uma análise com Claude",
        "analise_juridica",
        ja_sanitizado=True,
        provider_solicitado="anthropic",
    )
    assert decisao.permitido is True
    assert decisao.provider_chain == [("anthropic", None)]


def test_porta_canonica_aceita_selecao_de_claude():
    req = ConversarRequest(texto="Analise esta questão jurídica.", provider="anthropic")
    assert req.provider == "anthropic"
