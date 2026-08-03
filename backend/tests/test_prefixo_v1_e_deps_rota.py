"""Regressão dos três P0 da auditoria integral (docs/auditoria-ejc/).

Os defeitos cobertos aqui sobreviveram a 4463 testes verdes porque nenhum era
alcançável por teste de unidade: todos moram na SUPERFÍCIE — no path que o
router registra e nas dependências que a rota realmente resolve. É esse o vão
que este arquivo fecha.

P0-1  Oito routers declaravam prefix="/v1/...". Como main.py os monta sob
      prefix="/api", o path REAL virava /api/v1/despesas; mas o
      APIVersionCompatibilityMiddleware reescreve /api/v1/* -> /api/* ANTES do
      roteamento, então a rota só respondia em /api/v1/v1/despesas. Resultado:
      Contratos do Escritório, DataJud, Despesas e Kanban ficaram inacessíveis
      pela interface — sem erro visível, apenas "lista vazia".

P0-3  O monkeypatch de GET /api/rag/docs trocava route.endpoint por uma função
      cuja assinatura tinha `db=None, cu=None` SEM Depends. include_router roda
      depois e reconstrói o dependant a partir da assinatura: db e cu viravam
      QUERY PARAMS, get_db e get_current_user sumiam, e a rota estourava 500 em
      toda chamada — levando junto o escopo de visibilidade que o patch existe
      para instalar.

(P0-2, o verificador de contrato cego para o P0-1, é coberto por
 tests/test_api_contract.py, que agora modela o interceptor do frontend.)
"""
from __future__ import annotations

import os

import pytest

ROUTERS_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "routers")


def test_nenhum_router_declara_prefixo_v1():
    """O "/v1" é contrato PÚBLICO, entregue pelo middleware — nunca prefixo de router.

    Declarar prefix="/v1/..." no APIRouter empurra o "/v1" para o path interno,
    que o middleware então come, tornando a rota inalcançável pelo caminho
    canônico. Se este teste falhar, remova o "/v1" do prefix: o /api/v1 público
    continua funcionando sozinho.
    """
    infratores = []
    for nome in sorted(os.listdir(ROUTERS_DIR)):
        if not nome.endswith(".py"):
            continue
        caminho = os.path.join(ROUTERS_DIR, nome)
        with open(caminho, encoding="utf-8") as fh:
            for n, linha in enumerate(fh, 1):
                if 'prefix="/v1' in linha or "prefix='/v1" in linha:
                    infratores.append(f"{nome}:{n}: {linha.strip()}")
    assert not infratores, (
        "Router(es) declarando prefixo /v1 — o path interno deve ser /api/<recurso>, "
        "e o /api/v1 público é entregue pelo APIVersionCompatibilityMiddleware:\n  "
        + "\n  ".join(infratores)
    )


def _app():
    from app.main import app

    return app


def test_rotas_dos_modulos_afetados_respondem_no_contrato_canonico():
    """As rotas dos 8 routers do P0-1 existem em /api/<recurso> (sem /v1 interno)."""
    paths = {getattr(r, "path", "") for r in _app().routes}
    esperadas = [
        "/api/despesas",
        "/api/office-contracts",
        "/api/partner-withdrawals",
        "/api/kanban-columns",
        "/api/datajud/process/{numero_cnj}",
        "/api/regulatorio/digest-semanal",
        "/api/clients/{client_id}/pending-items",
        "/api/whatsapp/status",
    ]
    faltando = [p for p in esperadas if p not in paths]
    assert not faltando, f"rotas ausentes no path canônico: {faltando}"


def test_nenhuma_rota_registrada_sob_api_v1_interno():
    """Nada deve ser REGISTRADO em /api/v1 — esse prefixo é só a superfície pública.

    Uma rota registrada em /api/v1/X é inalcançável: o middleware reescreve a
    requisição /api/v1/X para /api/X antes do roteamento.
    """
    internas = sorted(
        p for r in _app().routes if (p := getattr(r, "path", "")).startswith("/api/v1")
    )
    assert not internas, (
        "rotas registradas sob /api/v1 são inalcançáveis (o middleware as reescreve "
        f"para /api antes do roteamento): {internas}"
    )


def test_rag_docs_resolve_db_e_usuario_por_dependency():
    """GET /api/rag/docs precisa de get_db e get_current_user na cadeia de DI.

    Se `db`/`cu` aparecerem como query params, o monkeypatch perdeu os Depends e
    a rota devolve 500 em toda chamada — além de deixar de aplicar o escopo de
    visibilidade dos KnowledgeDoc.
    """
    rota = next(
        (r for r in _app().routes if getattr(r, "path", "") == "/api/rag/docs"), None
    )
    assert rota is not None, "rota GET /api/rag/docs não encontrada"

    query = {p.name for p in rota.dependant.query_params}
    assert not ({"db", "cu"} & query), (
        "db/cu viraram query params — o endpoint perdeu os Depends "
        f"(query params: {sorted(query)})"
    )

    subdeps = {d.call.__name__ for d in rota.dependant.dependencies}
    assert "get_db" in subdeps, f"get_db ausente da cadeia de DI: {sorted(subdeps)}"
    assert "get_current_user" in subdeps, (
        f"get_current_user ausente da cadeia de DI: {sorted(subdeps)}"
    )


@pytest.mark.parametrize(
    "raw, esperado",
    [
        # O interceptor (frontend/src/lib/api.ts:21-23) apara um prefixo já
        # presente antes de aplicar o baseURL /api/v1.
        ("/despesas", "/api/v1/despesas"),
        ("/v1/despesas", "/api/v1/despesas"),
        ("/api/despesas", "/api/v1/despesas"),
        ("/api/v1/despesas", "/api/v1/despesas"),
        # Passe ÚNICO: o interceptor não normaliza a duplicação já formada.
        # Documentado como limitação conhecida, não como comportamento desejado.
        ("/api/v1/v1/despesas", "/api/v1/v1/despesas"),
    ],
)
def test_verificador_de_contrato_reproduz_o_interceptor(raw, esperado):
    """P0-2: _final_url deve calcular a URL que o navegador REALMENTE envia.

    Antes, a função concatenava baseURL + raw sem a poda, e para "/v1/despesas"
    produzia /api/v1/v1/despesas — que casava com a rota registrada e gerava
    falso verde sobre exatamente a classe de bug do P0-1.
    """
    from app.utils.api_contract import _final_url

    assert _final_url(True, raw) == esperado
