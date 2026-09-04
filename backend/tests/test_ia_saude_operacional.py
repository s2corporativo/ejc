"""Regressões do estado operacional da IA sem depender de rede ou banco."""
from types import SimpleNamespace

from app.routers.ia_saude import _busca_semantica_pronta, _estado_provedores


def _cfg_embeddings(provider: str, *, enabled: bool = True, api_url: str = ""):
    return SimpleNamespace(
        EMBEDDINGS_ENABLED=enabled,
        EMBEDDINGS_PROVIDER=provider,
        EMBEDDINGS_API_URL=api_url,
    )


def _cfg_provedores(*, ai_enabled: bool = True, ai_provider: str = "auto"):
    return SimpleNamespace(
        AI_ENABLED=ai_enabled,
        AI_PROVIDER=ai_provider,
        AI_EXTERNAL_PROVIDERS_ALLOWED=True,
        ANTHROPIC_ENABLED=True,
        ANTHROPIC_API_KEY="anthropic-configurada",
        MARITACA_ENABLED=False,
        MARITACA_API_KEY="",
        GROQ_ENABLED=True,  # fonte única (provider_registry) exige a flag
        GROQ_API_KEY="groq-configurada",
        OLLAMA_ENABLED=True,
        AI_PROVIDER_PRIORITY="ollama,anthropic,maritaca,groq",
    )


def test_embeddings_http_sem_url_nao_fica_semanticamente_pronto():
    assert not _busca_semantica_pronta(
        _cfg_embeddings("http", api_url=""), fastembed_instalado=True
    )


def test_embeddings_http_com_url_fica_pronto_sem_fastembed_local():
    assert _busca_semantica_pronta(
        _cfg_embeddings("http", api_url="http://embeddings-interno:8000"),
        fastembed_instalado=False,
    )


def test_embeddings_local_exige_fastembed_e_respeita_kill_switch():
    assert not _busca_semantica_pronta(
        _cfg_embeddings("local"),
        fastembed_instalado=False,
        validar_local=lambda: (True, "ok"),
    )
    assert _busca_semantica_pronta(
        _cfg_embeddings("local"),
        fastembed_instalado=True,
        validar_local=lambda: (True, "modelo e dimensão válidos"),
    )
    assert not _busca_semantica_pronta(
        _cfg_embeddings("local", enabled=False),
        fastembed_instalado=True,
        validar_local=lambda: (True, "ok"),
    )


def test_embeddings_local_invalido_nao_e_anunciado_como_pronto():
    assert not _busca_semantica_pronta(
        _cfg_embeddings("local"),
        fastembed_instalado=True,
        validar_local=lambda: (False, "dimensão incompatível"),
    )


def test_embeddings_local_falha_fechado_se_validador_lancar_excecao():
    def falhar():
        raise RuntimeError("registro fastembed indisponível")

    assert not _busca_semantica_pronta(
        _cfg_embeddings("local"),
        fastembed_instalado=True,
        validar_local=falhar,
    )


def test_kill_switch_global_desativa_todos_os_provedores_runtime():
    estado = _estado_provedores(_cfg_provedores(ai_enabled=False))

    assert estado["modo"] == "indisponivel"
    assert estado["elegiveis"] == []
    assert not any(estado["runtime"].values())


def test_provider_forcado_elegivel_vira_unico_runtime():
    estado = _estado_provedores(_cfg_provedores(ai_provider="ollama"))

    assert estado["modo"] == "local"
    assert estado["elegiveis"] == ["ollama"]
    assert estado["runtime"]["ollama"] is True
    assert estado["runtime"]["anthropic"] is False
    assert estado["runtime"]["groq"] is False


def test_provider_forcado_inelegivel_cai_para_cadeia_automatica():
    cfg = _cfg_provedores(ai_provider="maritaca")
    estado = _estado_provedores(cfg)

    assert estado["forcado_inelegivel"] is True
    assert estado["modo"] == "auto_fallback"
    assert estado["elegiveis"] == ["ollama", "anthropic", "groq"]
