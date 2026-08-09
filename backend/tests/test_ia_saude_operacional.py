"""Regressões do estado operacional da IA sem depender de rede ou banco."""
from types import SimpleNamespace

from app.routers.ia_saude import _busca_semantica_pronta


def _cfg(provider: str, *, enabled: bool = True, api_url: str = ""):
    return SimpleNamespace(
        EMBEDDINGS_ENABLED=enabled,
        EMBEDDINGS_PROVIDER=provider,
        EMBEDDINGS_API_URL=api_url,
    )


def test_embeddings_http_sem_url_nao_fica_semanticamente_pronto():
    assert not _busca_semantica_pronta(
        _cfg("http", api_url=""), fastembed_instalado=True
    )


def test_embeddings_http_com_url_fica_pronto_sem_fastembed_local():
    assert _busca_semantica_pronta(
        _cfg("http", api_url="http://embeddings-interno:8000"),
        fastembed_instalado=False,
    )


def test_embeddings_local_exige_fastembed_e_respeita_kill_switch():
    assert not _busca_semantica_pronta(_cfg("local"), fastembed_instalado=False)
    assert _busca_semantica_pronta(_cfg("local"), fastembed_instalado=True)
    assert not _busca_semantica_pronta(
        _cfg("local", enabled=False), fastembed_instalado=True
    )
