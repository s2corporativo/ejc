"""Regressão dos P1 de segurança/custo da auditoria integral (docs/auditoria-ejc/).

Três defeitos da mesma família: o gate existia no caminho gêmeo, ou na tela, mas
não no endpoint que de fato executa o ato.

P1-1  `routers/ai.py` tinha 14 rotas POST e apenas 3 com rate limit, e o
      `SlowAPIMiddleware` não é registrado (só o exception handler), logo não há
      `default_limits`. Qualquer conta staff — inclusive estagiário, admitido no
      assistente — podia rodar um laço contra `/dual` (duas inferências por
      request) e queimar o orçamento de provedor do escritório; sob worker único,
      ainda saturava o event loop.

P1-2  `POST /victory_vault/teses` e `/modelos` gravavam no cofre institucional só
      com JWT, e `POST /document-templates/generate` renderizava documento
      jurídico sem vínculo a caso e sem piso de papel — enquanto o caminho gêmeo
      (`kit_documental.py:58`) já exigia advogado + rate limit.

P1-4  `/prompts` era restrito a ROLES.juridico **apenas no moduleRegistry**. No
      backend o corte era `>= estagiario`, e `financeiro` (4) > `estagiario` (3),
      então o perfil financeiro recebia a biblioteca inteira.
"""
from __future__ import annotations

import pytest


def _app():
    from app.main import app

    return app


def _rotas_por_path(app):
    return {
        (getattr(r, "path", ""), m): r
        for r in app.routes
        for m in (getattr(r, "methods", None) or [])
    }


def _tem_dep(rota, nome: str, profundidade: int = 6) -> bool:
    """Procura uma dependency pelo nome do callable, descendo a árvore de DI."""

    def desce(dep, nivel=0):
        if dep is None or nivel > profundidade:
            return False
        for d in getattr(dep, "dependencies", []) or []:
            call = getattr(d, "call", None)
            if getattr(call, "__name__", "") == nome:
                return True
            if desce(d, nivel + 1):
                return True
        return False

    return desce(getattr(rota, "dependant", None))


# ── P1-1 · rate limit nas rotas caras de IA ──────────────────────────────────

ROTAS_IA_CARAS = [
    "/api/ai/analisar-caso",
    "/api/ai/resumir-documento",
    "/api/ai/teses-ocultas",
    "/api/ai/auditar-peca",
    "/api/ai/preparar-audiencia",
    "/api/ai/casos/{case_id}/assistente",
    "/api/ai/casos/{case_id}/dual",
    "/api/ai/caso/{case_id}/visual-law",
    "/api/ai/caso/{case_id}/estrategia",
    "/api/ai/analisar-contrato",
    "/api/ai/detectar-prazos",
]


@pytest.mark.parametrize("path", ROTAS_IA_CARAS)
def test_rota_de_ia_cara_tem_rate_limit(path):
    """Toda rota que dispara o ai_gateway precisa de teto por usuário.

    Não há `default_limits` global (o SlowAPIMiddleware não é registrado), então
    a ausência aqui significa custo de provedor sem nenhum limite.
    """
    rota = _rotas_por_path(_app()).get((path, "POST"))
    assert rota is not None, f"rota POST {path} não encontrada"
    assert _tem_dep(rota, "_dep"), (
        f"POST {path} sem rate_limit — endpoint de IA sem teto de custo"
    )


def test_nenhuma_rota_post_de_ia_ficou_sem_rate_limit():
    """Guarda de cobertura: rota nova em /api/ai/ nasce com teto.

    A allowlist é curta e explícita — são as rotas baratas, que não chamam
    modelo. Qualquer POST novo em /api/ai/ reprova até ser classificado.
    """
    baratas = {
        "/api/ai/logs/{log_id}/feedback",  # grava feedback, não chama modelo
        "/api/ai/gateway/health",          # diagnóstico do gateway
    }
    sem_limite = sorted(
        path
        for (path, metodo), rota in _rotas_por_path(_app()).items()
        if metodo == "POST"
        and path.startswith("/api/ai/")
        and path not in baratas
        and not _tem_dep(rota, "_dep")
    )
    assert not sem_limite, (
        "rota(s) POST de IA sem rate limit — classifique como barata na "
        f"allowlist deste teste ou aplique Depends(rate_limit(...)): {sem_limite}"
    )


# ── P1-2 · ato jurídico exige advogado+ ──────────────────────────────────────

@pytest.mark.parametrize(
    "path",
    [
        "/api/victory_vault/teses",
        "/api/victory_vault/modelos",
        "/api/document-templates/generate",
    ],
)
def test_escrita_de_ato_juridico_exige_advogado(path):
    """Gravar no cofre institucional e gerar documento são atos jurídicos.

    Antes bastava JWT: secretaria (nível 2) e estagiário (3) passavam.
    """
    rota = _rotas_por_path(_app()).get((path, "POST"))
    assert rota is not None, f"rota POST {path} não encontrada"
    assert _tem_dep(rota, "_req_advogado"), (
        f"POST {path} sem gate de advogado — ato jurídico aberto a qualquer perfil"
    )


@pytest.mark.parametrize(
    "path",
    ["/api/victory_vault/teses", "/api/victory_vault/modelos"],
)
def test_leitura_do_cofre_segue_aberta_a_staff(path):
    """A restrição é de ESCRITA. Consultar o acervo continua sendo de todo staff."""
    rota = _rotas_por_path(_app()).get((path, "GET"))
    assert rota is not None, f"rota GET {path} não encontrada"
    assert not _tem_dep(rota, "_req_advogado"), (
        f"GET {path} não deveria exigir advogado — ler o acervo não é ato jurídico"
    )


# ── P1-4 · /prompts alinhado à matriz do frontend ────────────────────────────

def test_conjunto_juridico_de_prompts_exclui_financeiro_e_secretaria():
    """`financeiro` tem nível MAIOR que `estagiario` — por isso o corte é conjunto.

    Este teste trava a semântica: "jurídico" é um time, não um piso de nível.
    Um `ROLE_LEVEL >= estagiario` deixaria `financeiro` entrar.
    """
    from app.core.security import ROLE_LEVEL
    from app.routers.prompts_juridicos import _ROLES_JURIDICO

    assert "financeiro" not in _ROLES_JURIDICO
    assert "secretaria" not in _ROLES_JURIDICO
    assert {"advogado", "estagiario", "socio", "admin", "superadmin"} <= _ROLES_JURIDICO

    # A armadilha que motivou a correção — se isto deixar de valer, o corte por
    # nível voltaria a ser seguro e este teste pode ser revisto.
    assert ROLE_LEVEL["financeiro"] > ROLE_LEVEL["estagiario"]
