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
