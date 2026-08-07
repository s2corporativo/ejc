"""Contrato HTTP frontend↔backend: toda chamada estática do frontend deve
casar uma rota REAL do app montado.

O cliente usa o contrato público /api/v1; os routers permanecem montados em
/api e o middleware versionador reescreve o prefixo antes do dispatch.
"""
import pytest

from app.utils.api_contract import (
    _CALL_RE,
    _final_url,
    _internal_api_url,
    check_frontend_contract,
)


def test_frontend_calls_batem_com_rotas_reais():
    unmatched, stats = check_frontend_contract()
    if stats.files == 0:
        pytest.skip("frontend/src ausente neste checkout — nada a verificar")
    assert stats.routes > 300, f"poucas rotas extraídas ({stats.routes})"
    assert stats.calls > 50, f"poucas chamadas extraídas ({stats.calls})"
    if unmatched:
        linhas = "\n".join(
            f"  {c.method:6} {c.raw_path}  <- {c.file}:{c.line}" for c in unmatched
        )
        pytest.fail(
            f"{len(unmatched)} chamada(s) do frontend sem rota correspondente no "
            f"backend (404 em produção):\n{linhas}\n\n"
            "Corrija o path no frontend ou monte/adicione a rota no backend. "
            "Se for chamada legitimamente dinâmica/externa, adicione à "
            "ALLOWLIST_SUBSTR em app/utils/api_contract.py com justificativa."
        )


def test_cliente_axios_resolve_no_prefixo_publico_versionado():
    assert _final_url(True, "/cases") == "/api/v1/cases"
    assert _final_url(True, "/auth/refresh") == "/api/v1/auth/refresh"


def test_prefixo_publico_versionado_equivale_ao_path_interno_exato():
    assert _internal_api_url("/api/v1") == "/api"
    assert _internal_api_url("/api/v1/auth/refresh") == "/api/auth/refresh"
    assert _internal_api_url("/api/v10/auth/refresh") == "/api/v10/auth/refresh"
    assert _internal_api_url("/api/auth/refresh") == "/api/auth/refresh"


def test_extrator_reconhece_chamada_encadeada_multilinha():
    """O prettier pode quebrar `api.get` em múltiplas linhas."""
    src = (
        "const r = await api\n"
        "  .get<TimelineResponse>(\n"
        '    "/visual-law/casos/abc/timeline",\n'
        "  );\n"
    )
    m = _CALL_RE.search(src)
    assert m is not None, "chamada encadeada multilinha não reconhecida"
    assert m.group(1) == "api"
    assert m.group(2) == "get"
    assert m.group(4) == "/visual-law/casos/abc/timeline"


# ── Ponto cego que mascarava um 404 real (Onda 2 da refatoração) ─────────────
# O verificador não modelava o interceptor de request do frontend. Resultado:
# `api.get("/v1/despesas")` era lido como `/api/v1/v1/despesas` — que casava a
# rota montada POR ENGANO em `/api/v1/despesas` — enquanto o navegador de
# verdade pedia `/api/v1/despesas` e tomava 404. O verificador aprovava
# justamente o defeito que existe para pegar.
def test_verificador_espelha_a_poda_de_prefixo_do_interceptor():
    from app.utils.api_contract import _podar_prefixo_do_interceptor as podar

    assert podar("/v1/despesas") == "/despesas"
    assert podar("/api/despesas") == "/despesas"
    assert podar("/api/v1/despesas") == "/despesas"
    # Sem prefixo repetido, nada muda.
    assert podar("/despesas") == "/despesas"
    # Não pode comer um segmento que apenas COMEÇA com o prefixo.
    assert podar("/apiario/x") == "/apiario/x"
    assert podar("/v10/x") == "/v10/x"


def test_chamada_escrita_com_prefixo_resolve_na_mesma_url_da_canonica():
    """As duas formas produzem o MESMO request na rede — é o que o interceptor
    garante. O verificador precisa enxergar isso, senão aprova uma e reprova a
    outra sem que nada tenha mudado no comportamento."""
    assert _final_url(True, "/despesas") == "/api/v1/despesas"
    assert _final_url(True, "/v1/despesas") == "/api/v1/despesas"
    assert _final_url(True, "/api/despesas") == "/api/v1/despesas"
    assert _final_url(True, "/api/v1/despesas") == "/api/v1/despesas"


def test_nenhum_router_fica_montado_dentro_de_api_v1():
    """Router com `prefix="/v1/..."` montado sob `prefix="/api"` cai em
    `/api/v1/...` — exatamente o que o middleware de versão reescreve para
    longe, deixando a rota inalcançável pelo contrato público. Oito routers
    estavam assim (despesas, office-contracts, partner-withdrawals,
    pending-items, kanban, datajud, regulatorio, whatsapp), e era a causa do
    'Financeiro: Despesas, Contratos e Sociedade hoje 404'."""
    from app.main import app

    presos = sorted(
        {p for r in app.routes if "/api/v1/" in (p := getattr(r, "path", "") or "")}
    )
    assert presos == [], (
        "rota(s) montada(s) em /api/v1/ — o middleware de versão as reescreve "
        "para /api/... e elas ficam inalcançáveis:\n  " + "\n  ".join(presos)
    )
