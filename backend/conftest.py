# conftest.py — garante ambiente de teste (dev: SECRET_KEY efêmera, sem .env).
# Estar na raiz do backend coloca `app` no sys.path (import mode prepend do pytest).
#
# Blindagem contra backend/.env local: pydantic-settings LÊ o .env se ele
# existir, e a suíte assume os defaults do código (ex.: os testes de
# test_feriados_brasilapi.py assumem FERIADOS_BRASILAPI_ENABLED=true, o
# default de Settings). Como variável de ambiente REAL tem precedência sobre
# o .env no pydantic-settings, fixamos aqui (via setdefault — quem exporta
# explicitamente no shell/CI continua mandando) as envs críticas cujos
# valores num .env de dev contaminariam os testes.
import os

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("FERIADOS_BRASILAPI_ENABLED", "true")
# Testes nunca devem gerar uma chave Fernet aleatória a cada processo nem
# tentar enviar eventos para um coletor externo. Esta chave é exclusiva para a
# suíte; produção exige VAULT_MASTER_KEYS configurada fora do repositório.
os.environ.setdefault(
    "VAULT_MASTER_KEYS",
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
)
os.environ.setdefault("SENTRY_DSN", "")

# ── Engine global: fail-safe contra cross-loop entre testes ──────────────────
# pytest-asyncio (asyncio_mode=auto) cria um event loop NOVO por função de
# teste. O engine async de app/core/database.py é um singleton MODULE-LEVEL:
# sua pool pode reter conexões abertas sob o loop de um teste anterior já
# encerrado. O próximo teste que fizer checkout dessa conexão (pool_pre_ping
# testa a conexão a cada checkout) recebe 'Future attached to a different
# loop' — e tentar simplesmente `engine.dispose()` (fechar graciosamente as
# conexões antigas) FALHA DE NOVO com 'Event loop is closed', porque fechar
# uma conexão asyncpg também precisa do loop original.
#
# 28 arquivos *_dblevel.py já usam a fixture local `_dispose_engine_apos_teste`
# (dispose APÓS o próprio teste) — mas isso só protege quem roda DEPOIS de um
# arquivo com a fixture, não de QUALQUER teste (incl. fora de *_dblevel.py, ou
# via TestClient/get_db) que tenha aberto uma conexão real sem limpar. Fix
# sistêmico: descartar a pool ANTES de cada teste roda, sempre, globalmente —
# com close=False (mesma mitigação já documentada em check_db()): abandona
# conexões presas ao loop morto SEM tentar fechá-las graciosamente (não
# dispara o RuntimeError de fechamento). Barato quando a pool está vazia
# (nada em produção real usa pool_pre_ping perdendo tempo aqui — só a suíte).
import pytest


@pytest.fixture(autouse=True)
async def _engine_pool_limpo_por_teste():
    from app.core.database import engine
    await engine.dispose(close=False)
    yield


# ── Isolamento das cotas de rate limit entre testes ──────────────────────────
# A suíte roda em segundos com o MESMO IP/usuário sintético: sem este reset,
# as janelas de 60s acumulam ENTRE testes (o teste que roda depois herda a
# cota já consumida pelo anterior) e loops legítimos de TestClient batem 429
# nos endpoints agora protegidos pela Fase 8. Isolamento de teste — o
# comportamento de produção (contador por rota/usuário-IP) permanece intacto.
# O slowapi (@limiter.limit em auth) usa storage próprio e também é zerado.
@pytest.fixture(autouse=True)
def _rate_limit_zerado_por_teste():
    from app.core import rate_limit as _rl

    def _resetar_estado():
        # Usa a API interna canônica para respeitar o lock que protege _janelas.
        _rl._limpar_janelas()
        storage = getattr(_rl.limiter, "_storage", None)
        if storage is not None and hasattr(storage, "reset"):
            storage.reset()

    _resetar_estado()
    yield
    # Teardown simétrico: nenhum estado do contador próprio ou do slowapi
    # deve vazar para o teste seguinte, mesmo se o teste atual falhar.
    _resetar_estado()


@pytest.fixture(autouse=True)
def _sentry_transport_noop(monkeypatch):
    """Preserva o teste de inicialização sem enviar eventos para a rede."""
    import sentry_sdk

    original_init = sentry_sdk.init

    def _init_sem_rede(*args, **kwargs):
        dsn = kwargs.get("dsn") or (args[0] if args else "")
        # DSNs inválidos continuam passando pelo SDK para preservar o teste de
        # fail-closed; somente um DSN com formato válido recebe transporte no-op.
        if isinstance(dsn, str) and "://" in dsn and "@" in dsn:
            kwargs.setdefault("transport", lambda event, hint=None: None)
        return original_init(*args, **kwargs)

    monkeypatch.setattr(sentry_sdk, "init", _init_sem_rede)
    yield


# ── Guarda: ninguém recria o singleton de Settings entre testes (Issue #620) ─
# `Settings` é cacheada via `lru_cache` em app.core.config.get_settings(), e
# vários módulos capturam a referência da instância NO IMPORT (ex.:
# app/services/vault_crypto.py: `settings = get_settings()`, linha de módulo).
# Se um teste chamar `get_settings.cache_clear()`, o PRÓXIMO get_settings()
# nasce OUTRA instância — quem já capturou a referência antiga fica
# desalinhado, com sintomas em arquivos sem nenhuma relação com quem limpou o
# cache (10 falhas em 5 arquivos, ver Issue #620: identidade de singleton,
# chave Fernet efêmera nova para o Cofre, flags de política voltando ao
# default).
#
# Tentativa descartada: detectar a recriação DEPOIS do fato (comparar
# identidade antes/depois numa fixture autouse) e "restaurar" trocando
# `app.core.config.get_settings` por um wrapper novo. Não funciona: arquivos
# de teste que fazem `from app.core.config import get_settings` no TOPO do
# arquivo (ex.: test_vault_service.py, test_roteamento_gateway.py — os
# mesmos citados na Issue #620) capturam essa referência na COLETA, antes de
# qualquer teste rodar. Trocar o atributo do módulo depois não afeta esse
# nome já vinculado — ele continua apontando para a função ORIGINAL, cujo
# `lru_cache` interno já foi poluído pelo `cache_clear()+get_settings()` do
# teste ofensor. "Restaurar depois" é tarde demais; é preciso IMPEDIR.
#
# `get_settings` é um único objeto-função por processo — TODO `from
# app.core.config import get_settings`, não importa quando rodar, aponta
# para esse MESMO objeto (é assim que o cache de módulos do Python
# funciona). Por isso a trava monkeypatcha `.cache_clear` DIRETO no objeto
# compartilhado, aqui no nível de módulo do conftest.py raiz — roda uma
# única vez, na coleta, antes de qualquer arquivo de teste ser importado, e
# vale para a suíte inteira independentemente de quem capturar a referência
# antes ou depois. `get_settings()` (a leitura) continua normal — só a
# limpeza do cache fica bloqueada.
#
# Para VARIAR configuração num teste, use a fixture `override_settings`
# abaixo — ela muta atributos da instância JÁ CACHEADA (via monkeypatch,
# desfeito automaticamente ao final do teste), nunca troca o objeto nem
# limpa o cache.
from app.core.config import get_settings as _settings_singleton


def _cache_clear_bloqueado_em_teste(*_args, **_kwargs):
    pytest.fail(
        "get_settings.cache_clear() foi chamado durante os testes. Isso "
        "recria o singleton de Settings — vários módulos capturam a "
        "referência da instância no import (ex.: vault_crypto.py: "
        "`settings = get_settings()`), e uma segunda instância os deixa "
        "desalinhados, com sintomas em arquivos sem relação nenhuma com "
        "quem limpou o cache (Issue #620: 10 falhas em 5 arquivos). Use a "
        "fixture `override_settings` (backend/conftest.py) para variar "
        "configuração em teste sem recriar o singleton."
    )


_settings_singleton.cache_clear = _cache_clear_bloqueado_em_teste


@pytest.fixture
def override_settings(monkeypatch):
    """Varia atributos de `Settings` SEM recriar o singleton (Issue #620).

    Muta a instância já cacheada de `get_settings()` via `monkeypatch`
    (desfeito automaticamente ao final do teste) — quem capturou
    `settings = get_settings()` no import de outro módulo (ex.:
    vault_crypto.py) continua vendo o MESMO objeto Python, só que com o
    valor novo. Nunca chama `cache_clear()`, então a chave Fernet efêmera do
    Cofre, a identidade do singleton e qualquer estado capturado por outro
    módulo permanecem estáveis.

    Uso:
        def test_x(override_settings):
            override_settings(AI_ENABLED=False, SOME_FLAG=True)
            ...  # exercita o código; restaurado ao valor original no teardown
    """
    instancia = _settings_singleton()

    def _aplicar(**valores):
        for campo, valor in valores.items():
            monkeypatch.setattr(instancia, campo, valor, raising=True)
        return instancia

    return _aplicar
