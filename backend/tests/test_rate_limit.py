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
from app.core.security import get_current_user


@pytest.fixture(autouse=True)
def _janelas_limpas():
    """Cada teste começa com os contadores zerados (storage é module-level)."""
    rl._limpar_janelas()
    yield
    rl._limpar_janelas()


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
    # Mensagem clara em pt-BR e header Retry-After dentro da janela de 60s.
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

    # Avança além da janela de 60s → contador reinicia.
    relogio["t"] += rl._JANELA_SEGUNDOS + 1
    assert client.get("/alvo").status_code == 200


def test_usuarios_diferentes_nao_colidem():
    app, estado = _montar_app("t-usuarios", 2)
    client = TestClient(app)

    estado["user"] = types.SimpleNamespace(id="user-a")
    assert client.get("/alvo").status_code == 200
    assert client.get("/alvo").status_code == 200
    assert client.get("/alvo").status_code == 429  # user-a estourou

    estado["user"] = types.SimpleNamespace(id="user-b")
    assert client.get("/alvo").status_code == 200  # user-b tem cota própria


def test_sem_autenticacao_401_nao_consome_cota():
    """Auth roda ANTES do contador: request sem token leva 401 e não gasta cota."""
    app, estado = _montar_app("t-auth", 1)
    client = TestClient(app)

    def _nega():
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    app.dependency_overrides[get_current_user] = _nega
    assert client.get("/alvo").status_code == 401

    app.dependency_overrides[get_current_user] = lambda: estado["user"]
    assert client.get("/alvo").status_code == 200  # cota intacta (limite = 1)


def test_rotas_alvo_registradas_com_rate_limit():
    """Smoke: os endpoints da auditoria continuam montados no app real
    (a dependency não pode quebrar a montagem — regressão dos commits
    3d0df67/11da80f, NameError com PEP 563)."""
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    for sufixo in ("/gerar-peca", "/classificar", "/teses-sugeridas",
                   "/compliance/radar", "/checar-conflito",
                   "/anexos/preview", "/anexos/gerar", "/anexos/razoes"):
        assert any(p.endswith(sufixo) for p in paths), f"rota {sufixo} sumiu"
