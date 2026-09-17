"""Rate limit nos endpoints de usuários da prioridade 1 (Fase 8, onda 1-A).

O inventário RBAC (auditoria §3.7 #3) classificou 11 rotas de
`app/routers/users.py` como ONLY_AUTH + sensíveis SEM rate limit — a
prioridade 1 da Fase 8. Todas passam a ter cota fixed-window de 60s por
(rota, usuário-ou-IP).

Cobre a presença E o parâmetro de cada rate_limit (nome/limite), lendo o
fechamento de `rate_limit()` direto do objeto de rota real do app montado —
sem rede, sem banco.

Critério dos limites:
- leitura de bootstrap/UI (`/me`, avatar em listas) tem margem para não
  quebrar navegação normal (120/min);
- estado de segurança e sessões, 60/min;
- operações com credencial ou efeito destrutivo (QR TOTP pré-ativação, URL
  de calendário assinada, revogação de sessão, upload/remoção de avatar,
  PATCH de usuário) ficam entre 5 e 30/min.

Gates desta onda: os endpoints /me/* são self-service (escopo próprio por
construção — `get_current_user` É o gate; exigir papel quebraria o portal
do cliente externo); `PATCH /{user_id}` tem RBAC completo inline
(admin × campos_self × anti-escalada `_validar_alvo`); avatar de terceiros
tem gate de staff inline com 404 anti-enumeração. O tratamento P1 aqui é o
rate limit; gates estruturais por papel ficam para as superfícies de gestão
(onda 1-B, ia_governanca).
"""
from __future__ import annotations

from app.core.rate_limit import rate_limit as _rate_limit_factory

# (path, method) -> (nome esperado, limite máximo/minuto)
_ALVOS = {
    ("/api/users/me", "GET"): ("users-me", 120),
    ("/api/users/me/security", "GET"): ("users-me-seguranca", 60),
    ("/api/users/me/sessions", "GET"): ("users-me-sessoes", 60),
    ("/api/users/me/sessions/revoke-others", "POST"): ("users-sessoes-revoga-outras", 10),
    ("/api/users/me/sessions/{session_id}/revoke", "POST"): ("users-sessoes-revoga", 10),
    ("/api/users/me/totp-qr", "GET"): ("users-totp-qr", 5),
    ("/api/users/{user_id}", "PATCH"): ("users-atualiza", 30),
    ("/api/users/me/calendar-url", "GET"): ("users-calendario-url", 10),
    ("/api/users/me/avatar", "POST"): ("users-avatar-envia", 10),
    ("/api/users/me/avatar", "DELETE"): ("users-avatar-remove", 10),
    ("/api/users/{user_id}/avatar", "GET"): ("users-avatar-ve", 120),
}


def _rotas_do_app() -> dict[tuple[str, str], object]:
    from app.main import app

    saida = {}
    for r in app.routes:
        path = getattr(r, "path", None)
        metodos = getattr(r, "methods", None) or set()
        if path is None:
            continue
        for m in metodos:
            saida[(path, m)] = r
    return saida


def _fechamento_do_rate_limit(rota):
    """Acha, entre `rota.dependencies`, a closure `_dep` de rate_limit() e
    devolve (nome, limite) lidos do próprio fechamento."""
    referencia = _rate_limit_factory("sonda", 1)  # mesmo formato de closure
    for dep in getattr(rota, "dependencies", []) or []:
        fn = getattr(dep, "dependency", None)
        if fn is None or fn.__code__ is not referencia.__code__:
            continue
        limite, nome = (c.cell_contents for c in fn.__closure__)
        return nome, limite
    return None


def test_todos_os_alvos_tem_rate_limit_com_o_limite_esperado():
    rotas = _rotas_do_app()
    faltando = []
    divergentes = []
    for chave, (nome_esperado, limite_esperado) in _ALVOS.items():
        rota = rotas.get(chave)
        assert rota is not None, f"rota sumiu do app: {chave}"
        achado = _fechamento_do_rate_limit(rota)
        if achado is None:
            faltando.append(chave)
            continue
        nome, limite = achado
        if (nome, limite) != (nome_esperado, limite_esperado):
            divergentes.append((chave, achado, (nome_esperado, limite_esperado)))
    assert not faltando, f"sem rate_limit: {faltando}"
    assert not divergentes, f"rate_limit com parâmetros diferentes do esperado: {divergentes}"


def test_nomes_de_rate_limit_sao_unicos():
    """Nome duplicado faria dois endpoints diferentes compartilhar a mesma
    cota — um esvazia o limite do outro."""
    nomes = [nome for nome, _ in _ALVOS.values()]
    assert len(nomes) == len(set(nomes)), nomes
