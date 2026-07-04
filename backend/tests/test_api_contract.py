"""Contrato HTTP frontend↔backend: toda chamada estática do frontend deve
casar uma rota REAL do app montado (já com o prefixo /api).

Guarda de regressão da auditoria Graphify (2026-07-04): 11 bugs de 404 em
produção nasceram de paths do frontend divergindo das rotas do FastAPI
(prefixo /v1 fantasma, routers nunca montados). Este teste é a versão
executável daquela verificação — falha o CI antes do merge se o drift voltar.
"""
import pytest

from app.utils.api_contract import check_frontend_contract


def test_frontend_calls_batem_com_rotas_reais():
    unmatched, stats = check_frontend_contract()
    if stats.files == 0:
        pytest.skip("frontend/src ausente neste checkout — nada a verificar")
    # Sanidade: o extrator precisa ter enxergado rotas e chamadas.
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


def test_extrator_reconhece_chamada_encadeada_multilinha():
    """Regressão: o prettier quebra chamadas longas em `api\n  .get<T>(...)` e
    a regex antiga exigia `api.` colado — as rotas Visual Law passaram sem
    rota no backend justamente por esse ponto cego (404 silencioso em prod)."""
    from app.utils.api_contract import _CALL_RE

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
