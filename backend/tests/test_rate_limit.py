"""Testes da dependency rate_limit() (app/core/rate_limit.py).

Cobre a dependency ISOLADAMENTE num app FastAPI mínimo (sem banco): a auth
(get_current_user) é substituída por dependency_overrides, exatamente como o
FastAPI resolve em produção — o que valida também que a abordagem por
`dependencies=[Depends(rate_limit(...))]` é compatível com PEP 563
(`from __future__ import annotations`), a razão de os decorators @limiter.limit
do slowapi terem sido revertidos (commits 3d0df67 / 11da80f).
"""
from __future__ import annotations

import types

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core import rate_limit as rl
from app.core.config import get_settings
from app.core.security import get_current_user


@pytest.fixture(autouse=True)
def _estado_rate_limit_limpo(monkeypatch):
    """Cada teste começa com contador e backend Redis em estado conhecido."""
    rl._limpar_janelas()
    rl._redis_client = None
    monkeypatch.setattr(get_settings(), "RATE_LIMIT_REDIS_ENABLED", False)
    yield
    rl._limpar_janelas()
    rl._redis_client = None


def _montar_app(nome: str, limite: int):
    """App mínimo com uma rota protegida pela dependency, auth substituível."""
    app = FastAPI()

    @app.get("/alvo", dependencies=[Depends(rl.rate_limit(nome, limite))])
    async def alvo():
        return {"ok": True}

    estado = {"user": types.SimpleNamespace(id="user-a")}
    app.dependency_overrides[get_current_user] = lambda: estado["user"]
    return app, estado


def test_estourar_limite_retorna_429_com_retry_after():
    app, _ = _montar_app("t-estouro", 3)
    client = TestClient(app)

    for _ in range(3):
        assert client.get("/alvo").status_code == 200

    r = client.get("/alvo")
    assert r.status_code == 429
    assert "Limite de 3 requisições por minuto" in r.json()["detail"]
    assert 1 <= int(r.headers["Retry-After"]) <= 60


def test_janela_expirada_libera_novamente(monkeypatch):
    relogio = {"t": 1000.0}
    monkeypatch.setattr(rl, "_agora", lambda: relogio["t"])

    app, _ = _montar_app("t-janela", 2)
    client = TestClient(app)

    assert client.get("/alvo").status_code == 200
    assert client.get("/alvo").status_code == 200
    assert client.get("/alvo").status_code == 429

    relogio["t"] += rl._JANELA_SEGUNDOS + 1
    assert client.get("/alvo").status_code == 200


def test_usuarios_diferentes_nao_colidem():
    app, estado = _montar_app("t-usuarios", 2)
    client = TestClient(app)

    estado["user"] = types.SimpleNamespace(id="user-a")
    assert client.get("/alvo").status_code == 200
    assert client.get("/alvo").status_code == 200
    assert client.get("/alvo").status_code == 429

    estado["user"] = types.SimpleNamespace(id="user-b")
    assert client.get("/alvo").status_code == 200


def test_sem_autenticacao_401_nao_consome_cota():
    """Auth roda ANTES do contador: request sem credencial leva 401 e não gasta cota."""
    app, estado = _montar_app("t-auth", 1)
    client = TestClient(app)

    def _nega():
        raise HTTPException(status_code=401, detail="Credencial inválida ou expirada")

    app.dependency_overrides[get_current_user] = _nega
    assert client.get("/alvo").status_code == 401

    app.dependency_overrides[get_current_user] = lambda: estado["user"]
    assert client.get("/alvo").status_code == 200


class _FakeRedis:
    """Redis async mínimo: implementa o fixed-window do script Lua em memória."""

    def __init__(self):
        self.contadores: dict[str, int] = {}

    async def eval(self, _script, _nkeys, key, janela):
        self.contadores[key] = self.contadores.get(key, 0) + 1
        return [self.contadores[key], int(janela)]


class _RedisQuebrado:
    async def eval(self, *_a, **_k):
        raise ConnectionError("redis caiu")


async def test_redis_off_usa_memoria(monkeypatch):
    """Flag desligada: consumir() nunca toca o Redis."""
    monkeypatch.setattr(get_settings(), "RATE_LIMIT_REDIS_ENABLED", False)

    async def _boom():
        raise AssertionError("Redis não deveria ser consultado com a flag off")

    monkeypatch.setattr(rl, "_get_redis", _boom)
    for _ in range(2):
        await rl.consumir("m-off", "user:x", 2)
    with pytest.raises(HTTPException) as e:
        await rl.consumir("m-off", "user:x", 2)
    assert e.value.status_code == 429


async def test_redis_on_conta_no_redis(monkeypatch):
    """Flag ligada + Redis disponível: cota contada no Redis com chaves independentes."""
    monkeypatch.setattr(get_settings(), "RATE_LIMIT_REDIS_ENABLED", True)
    fake = _FakeRedis()
    monkeypatch.setattr(rl, "_get_redis", lambda: _async(fake))

    await rl.consumir("r-on", "user:a", 2)
    await rl.consumir("r-on", "user:a", 2)
    with pytest.raises(HTTPException) as e:
        await rl.consumir("r-on", "user:a", 2)
    assert e.value.status_code == 429
    assert 1 <= int(e.value.headers["Retry-After"]) <= 60

    await rl.consumir("r-on", "user:b", 2)
    nome_rl, chave_a = rl._chave_interna("r-on", "user:a")
    _, chave_b = rl._chave_interna("r-on", "user:b")
    assert fake.contadores[f"rl:{nome_rl}:{chave_a}"] == 3
    assert fake.contadores[f"rl:{nome_rl}:{chave_b}"] == 1
    assert "user:a" not in next(k for k in fake.contadores if chave_a in k)


async def test_redis_indisponivel_faz_fallback_para_memoria(monkeypatch):
    """Flag ligada mas Redis falha no eval: cai para contador em memória."""
    monkeypatch.setattr(get_settings(), "RATE_LIMIT_REDIS_ENABLED", True)
    rl._redis_client = "sentinela-para-invalidar"
    monkeypatch.setattr(rl, "_get_redis", lambda: _async(_RedisQuebrado()))

    for _ in range(2):
        await rl.consumir("r-fallback", "user:z", 2)
    with pytest.raises(HTTPException) as e:
        await rl.consumir("r-fallback", "user:z", 2)
    assert e.value.status_code == 429
    assert rl._redis_client is None


async def _async(valor):
    """Embrulha um valor síncrono numa coroutine."""
    return valor


def test_rotas_alvo_registradas_com_rate_limit():
    """Smoke: os endpoints da auditoria continuam montados no app real."""
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    for sufixo in ("/gerar-peca", "/classificar", "/teses-sugeridas",
                   "/compliance/radar", "/checar-conflito",
                   "/anexos/preview", "/anexos/gerar", "/anexos/razoes"):
        assert any(p.endswith(sufixo) for p in paths), f"rota {sufixo} sumiu"
