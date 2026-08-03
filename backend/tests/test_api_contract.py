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


def test_cliente_axios_apara_prefixo_repetido_como_o_interceptor():
    """Regressão P0-009: o verificador precisa reproduzir o interceptor de
    frontend/src/lib/api.ts, não o defeito que ele mascarava.

    O interceptor apara /api/v1, /api ou /v1 do config.url antes de a chamada
    sair, porque o baseURL do cliente já é /api/v1. Antes desta correção
    `_final_url` concatenava direto e produzia `/api/v1/v1/despesas` — URL que
    o navegador nunca emite. Como oito routers embutiam "/v1" no próprio
    prefixo, essa URL fantasma casava a rota real: o contrato ficava verde
    enquanto 27 chamadas do frontend davam 404 em produção.
    """
    assert _final_url(True, "/v1/despesas") == "/api/v1/despesas"
    assert _final_url(True, "/api/casos") == "/api/v1/casos"
    assert _final_url(True, "/api/v1/casos") == "/api/v1/casos"
    # Sem barra depois do prefixo NÃO é prefixo repetido — é nome de recurso.
    assert _final_url(True, "/v1beta/x") == "/api/v1/v1beta/x"
    assert _final_url(True, "/apiario") == "/api/v1/apiario"


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
