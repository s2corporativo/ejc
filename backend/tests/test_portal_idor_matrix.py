"""Matriz de segregação do Portal do Cliente — camadas 1 e 2 (SEM banco).

Prova exaustivamente, de forma rápida (roda na suíte padrão, sem Postgres):

  CAMADA 1 — AuthMiddleware (app/core/auth_middleware.py):
    o perfil `cliente_externo` fica CONFINADO à allowlist
    (/api/portal/*, /api/auth/*, /api/health, /api/notifications,
     /api/signatures, /api/users/me). Qualquer rota de staff
    (/api/cases, /api/clients, /api/deadlines, /api/fees, ...) → 403,
    NUNCA 200. Sem token → 401. Staff NÃO é confinado.

  CAMADA 2 — gate `_exigir_cliente` por endpoint (defesa em profundidade):
    mesmo que a camada 1 fosse contornada, cada handler do portal reexige
    role=cliente_externo + client_id → 403 para staff / cliente sem vínculo.

O isolamento ROW-LEVEL entre clientes (cliente A forjando id de cliente B →
404) exige dados reais e vive em test_portal_idor_matrix_dblevel.py — aqui
o FakeDB não filtraria de fato, então provamos apenas os gates de acesso.

Padrão do repo: mount de middleware em app mínimo + TestClient
(test_bloco6_auth.py) e chamada direta de handler com fake
(test_portal_fees_melhorias.py). Nenhum Postgres necessário.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.auth_middleware import AuthMiddleware
from app.core.security import create_access_token
from app.models.user import User, UserRole


# ══════════════════════════════════════════════════════════════════════════════
# CAMADA 1 — AuthMiddleware: allowlist do cliente_externo
# ══════════════════════════════════════════════════════════════════════════════
#
# Montamos o AuthMiddleware sobre um app mínimo com uma rota catch-all que
# devolve 200. Assim distinguimos as duas decisões possíveis do middleware:
#   • BLOQUEIO  → dispatch retorna 401/403 SEM chamar a rota (curto-circuito);
#   • LIBERAÇÃO → dispatch chama a rota → 200 {"reached": <path>}.
# A rota real nem precisa existir: a decisão é 100% path+role do JWT, tomada
# ANTES do roteamento. Os tokens são assinados por create_access_token, ou
# seja, pela MESMA SECRET_KEY que o middleware usa para validar (sem isso o
# teste viraria 401 espúrio).


def _app_com_middleware() -> TestClient:
    app = FastAPI()

    @app.api_route(
        "/api/{full_path:path}",
        methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    )
    async def catch_all(full_path: str):
        # Só é atingida quando o middleware LIBERA a requisição.
        return {"reached": full_path}

    app.add_middleware(AuthMiddleware)
    return TestClient(app)


CLIENTE = create_access_token("u-cliente", "cliente_externo")
ADVOGADO = create_access_token("u-adv", "advogado")
SOCIO = create_access_token("u-socio", "socio")


def _get(client: TestClient, path: str, token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get(path, headers=headers)


# ── 1.1 cliente_externo BLOQUEADO em toda rota de staff (403, nunca 200) ──────
# O coração do IDOR: um login de portal com JWT válido não pode alcançar o
# núcleo do escritório. Cada path abaixo é território exclusivo do staff.
ROTAS_STAFF = [
    "/api/cases",
    "/api/cases/algum-id",
    "/api/clients",
    "/api/clients/algum-id",
    "/api/deadlines",
    "/api/fees",
    "/api/documents",
    "/api/documents/algum-id/download",
    "/api/processes",
    "/api/tasks",
    "/api/intimacoes",
    "/api/audit",
    "/api/rag/buscar",
    "/api/datajud/consulta",
    "/api/templates",
    "/api/score-juridico",
    "/api/timesheet/casos/x",
    "/api/gestao-societaria",
    "/api/honorarios-oab",
    "/api/data-rooms",
    "/api/users",  # lista de usuários — NÃO é /api/users/me
    "/api/ia-core/executar",
]


@pytest.mark.parametrize("path", ROTAS_STAFF)
def test_cliente_externo_bloqueado_em_rota_de_staff(path):
    """Prova: cliente_externo com JWT válido → 403 em rota de staff, e a rota
    (catch-all 200) NUNCA é atingida. Se algum dia virar 200, é vazamento."""
    client = _app_com_middleware()
    r = _get(client, path, CLIENTE)
    assert r.status_code == 403, f"{path} deveria bloquear cliente_externo"
    assert r.json()["detail"] == "Acesso restrito ao Portal do Cliente"


# ── 1.2 cliente_externo LIBERADO nas rotas da allowlist (passa o middleware) ──
# Contraprova: a allowlist realmente deixa passar o que o portal precisa.
# 200 aqui = "o middleware liberou e a rota catch-all respondeu" (a autorização
# fina por client_id é da CAMADA 2 / row-level, não do middleware).
ROTAS_PORTAL_PERMITIDAS = [
    "/api/portal/meus-casos",
    "/api/portal/casos/algum-id",
    "/api/portal/documentos",
    "/api/portal/financeiro",
    "/api/portal/solicitacoes-documentos",
    "/api/portal/mensagens/nao-lidas",
    "/api/notifications",
    "/api/notifications/marcar-todas",
    "/api/signatures",
    "/api/signatures/sig-id/assinar",
    "/api/users/me",
    "/api/auth/alterar-senha",
    "/api/health",
]


@pytest.mark.parametrize("path", ROTAS_PORTAL_PERMITIDAS)
def test_cliente_externo_liberado_na_allowlist(path):
    """Prova: a allowlist do portal deixa o cliente_externo ALCANÇAR a rota
    (200 do catch-all) — não há falso bloqueio do que o portal usa."""
    client = _app_com_middleware()
    r = _get(client, path, CLIENTE)
    assert r.status_code == 200, f"{path} deveria passar o middleware p/ cliente"
    assert "reached" in r.json()


# ── 1.3 Colisão textual de prefixo NÃO amplia a allowlist ─────────────────────
# _path_casa_prefixo_publico casa subárvore deliberada, não prefixo textual:
# um path que "começa parecido" com uma rota liberada continua bloqueado.
ROTAS_COLISAO_BLOQUEADAS = [
    "/api/portal-admin/tudo",  # não é /api/portal/
    "/api/users",  # não é /api/users/me
    "/api/users/outro-id",  # não é /api/users/me
    "/api/notifications-internas",  # não é /api/notifications[/...]
    "/api/signatures-admin",  # não é /api/signatures[/...]
]


@pytest.mark.parametrize("path", ROTAS_COLISAO_BLOQUEADAS)
def test_colisao_textual_de_prefixo_nao_libera_cliente(path):
    """Prova: prefixo textual parecido (portal-admin, users, signatures-admin)
    NÃO entra na allowlist — cliente_externo continua 403."""
    client = _app_com_middleware()
    r = _get(client, path, CLIENTE)
    assert r.status_code == 403, f"{path} não pode ser liberado por colisão textual"


# ── 1.4 Sem token → 401 em rota protegida; público continua 200 ───────────────
def test_sem_token_rota_protegida_401():
    """Prova: rota protegida sem Authorization → 401 (não 403, não 200)."""
    client = _app_com_middleware()
    r = _get(client, "/api/cases", None)
    assert r.status_code == 401


def test_sem_token_portal_tambem_401():
    """Prova: o portal NÃO é público — sem token, 401 mesmo em /api/portal/*."""
    client = _app_com_middleware()
    r = _get(client, "/api/portal/meus-casos", None)
    assert r.status_code == 401


def test_sem_token_health_publico_200():
    """Prova: /api/health é público (liberado sem JWT) — controle de que o 401
    acima vem da proteção, não de tudo cair."""
    client = _app_com_middleware()
    r = _get(client, "/api/health", None)
    assert r.status_code == 200


# ── 1.5 Staff NÃO é confinado pela allowlist do portal ────────────────────────
@pytest.mark.parametrize("token", [ADVOGADO, SOCIO])
@pytest.mark.parametrize("path", ["/api/cases", "/api/clients", "/api/fees"])
def test_staff_nao_e_confinado(token, path):
    """Prova: o confinamento é EXCLUSIVO do cliente_externo — advogado/socio
    passam o middleware normalmente (200 do catch-all). Garante que a matriz
    1.1 mede confinamento de perfil, não indisponibilidade geral da rota."""
    client = _app_com_middleware()
    r = _get(client, path, token)
    assert r.status_code == 200
    assert "reached" in r.json()


# ── 1.6 Token com type != access é rejeitado (401) ────────────────────────────
def test_token_tipo_invalido_401():
    """Prova: o middleware exige type=access. Um refresh token (type=refresh)
    apresentado como Bearer → 401 (não abre a sessão do portal)."""
    from app.core.security import create_refresh_token

    refresh, _jti = create_refresh_token("u-cliente")
    client = _app_com_middleware()
    r = _get(client, "/api/portal/meus-casos", refresh)
    assert r.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# CAMADA 2 — gate `_exigir_cliente` por endpoint (defesa em profundidade)
# ══════════════════════════════════════════════════════════════════════════════
#
# Chamamos os handlers do portal DIRETAMENTE (padrão test_portal_fees_melhorias)
# com um usuário de staff e com um cliente_externo SEM client_id. Ambos devem
# tomar 403 — o gate roda ANTES de qualquer query, então um DB no-op basta.


class _DBNoop:
    """DB que nunca deveria ser tocado: o gate 403 precede a query."""

    async def execute(self, *a, **k):  # pragma: no cover - não deve ser chamado
        raise AssertionError("query executada apesar do gate _exigir_cliente")

    async def commit(self):  # pragma: no cover
        raise AssertionError("commit apesar do gate _exigir_cliente")


def _staff() -> User:
    return User(id="u-staff", role=UserRole.advogado, client_id=None, email="adv@ex.com", full_name="Adv Staff")


def _cliente_sem_vinculo() -> User:
    return User(
        id="u-orfao",
        role=UserRole.cliente_externo,
        client_id=None,
        email="orfao@ex.com",
        full_name="Cliente Sem Vínculo",
    )


# Cada entrada: (label, factory(cu, db) -> coroutine). Só o selecionado é
# instanciado e aguardado (evita "coroutine never awaited").
def _endpoints_portal():
    from app.routers.portal import (
        caso_detalhe,
        documentos,
        enviar_mensagem_portal,
        financeiro,
        listar_mensagens_portal,
        mensagens_nao_lidas,
        meus_casos,
        MsgIn,
    )

    return [
        ("portal.meus_casos", lambda cu, db: meus_casos(db=db, cu=cu)),
        ("portal.caso_detalhe", lambda cu, db: caso_detalhe(case_id="x", db=db, cu=cu)),
        ("portal.documentos", lambda cu, db: documentos(db=db, cu=cu)),
        ("portal.financeiro", lambda cu, db: financeiro(db=db, cu=cu)),
        ("portal.mensagens_nao_lidas", lambda cu, db: mensagens_nao_lidas(db=db, cu=cu)),
        ("portal.listar_mensagens", lambda cu, db: listar_mensagens_portal(case_id="x", db=db, cu=cu)),
        (
            "portal.enviar_mensagem",
            lambda cu, db: enviar_mensagem_portal(case_id="x", body=MsgIn(mensagem="oi"), db=db, cu=cu),
        ),
    ]


@pytest.mark.parametrize("quem", ["staff", "cliente_sem_vinculo"])
@pytest.mark.parametrize("idx", range(7))
async def test_endpoints_portal_exigem_cliente_com_vinculo(quem, idx):
    """Prova (defesa em profundidade): TODO endpoint do portal reexige
    role=cliente_externo + client_id. Staff e cliente sem vínculo → 403,
    ANTES de qualquer acesso a banco (o _DBNoop explode se for consultado)."""
    cu = _staff() if quem == "staff" else _cliente_sem_vinculo()
    label, factory = _endpoints_portal()[idx]
    with pytest.raises(HTTPException) as exc:
        await factory(cu, _DBNoop())
    assert exc.value.status_code == 403, f"{label} deveria negar {quem}"


async def test_portal_solicitacoes_documentos_exige_cliente():
    """Prova: o router de solicitações de documentos (upload do cliente) usa o
    MESMO gate — staff não lista solicitações pelo portal."""
    from app.routers.portal_documentos import listar_solicitacoes_portal

    with pytest.raises(HTTPException) as exc:
        await listar_solicitacoes_portal(db=_DBNoop(), cu=_staff())
    assert exc.value.status_code == 403


async def test_signatures_assinar_exige_cliente_externo():
    """Prova: POST /signatures/{id}/assinar é ato do cliente — staff → 403
    (o role-check precede o uso de request/db)."""
    from app.routers.signatures import assinar

    with pytest.raises(HTTPException) as exc:
        await assinar(sig_id="x", request=None, db=_DBNoop(), cu=_staff())
    assert exc.value.status_code == 403
