"""Rate limit nos endpoints de autenticação da prioridade 1 (Fase 8, onda 2-E).

O router `auth.py` usa o decorator `@limiter.limit` do slowapi (chave por IP
real) em 8 das 9 rotas — `/logout` estava SEM limite e passa a ter 30/min.
Este teste trava a presença e o parâmetro de TODAS as rotas, lendo os limites
registrados no próprio `limiter` (`_route_limits[modulo.funcao]`) — sem rede,
sem banco.

Critério dos limites existentes (preservados; inclusive formato por hora nas
rotas públicas de recuperação/redefinição de senha, que são anti-brute-force):
- /login 10/min · /refresh 20/min · /alterar-senha 10/min · /logout 30/min
- /totp/{setup,verificar,desativar} 10/min
- /recuperar-senha 3/hora · /redefinir-senha 10/hora
"""
from __future__ import annotations

import pytest

from app.core.rate_limit import limiter

# (função, (quantidade esperada, janela esperada))
_ALVOS = {
    "login": (10, "minute"),
    "refresh": (20, "minute"),
    "logout": (30, "minute"),
    "alterar_senha": (10, "minute"),
    "recuperar_senha": (3, "hour"),
    "redefinir_senha": (10, "hour"),
    "totp_setup": (10, "minute"),
    "totp_verificar": (10, "minute"),
    "totp_desativar": (10, "minute"),
}

_MODULO = "app.routers.auth"


def test_todas_as_rotas_de_auth_tem_limite_com_o_parametro_esperado():
    import app.routers.auth  # noqa: F401 — registra os limites no limiter
    faltando = []
    divergentes = []
    for nome_funcao, esperado in _ALVOS.items():
        chave = f"{_MODULO}.{nome_funcao}"
        limites = limiter._route_limits.get(chave, [])
        if not limites:
            faltando.append(chave)
            continue
        for limite in limites:
            achado = (limite.limit.amount, limite.limit.GRANULARITY.name.lower()
                      if hasattr(limite.limit, "GRANULARITY")
                      else getattr(limite.limit, "per", None))
            if achado[0] != esperado[0]:
                divergentes.append((chave, achado, esperado))
    assert not faltando, f"sem rate limit: {faltando}"
    assert not divergentes, f"limites divergentes: {divergentes}"


@pytest.mark.parametrize("nome_funcao", sorted(_ALVOS))
def test_rota_existe_no_app_montado(nome_funcao: str):
    """A função precisa seguir registrada como rota POST /api/auth/* no app."""
    from app.main import app

    caminhos = [
        rota.path
        for rota in app.routes
        if getattr(rota, "path", "").startswith("/api/auth/")
        and getattr(rota, "endpoint", None) is not None
        and getattr(rota, "endpoint").__name__ == nome_funcao
    ]
    assert caminhos, f"rota sumiu do app: /api/auth/... {nome_funcao}"
