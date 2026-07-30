"""Regressão da Auditoria Parte 9: rotas financeiras publicadas devem estar montadas."""

from app.main import app


ROTAS_FINANCEIRAS = {
    ("/api/v1/despesas", "GET"),
    ("/api/v1/office-contracts", "GET"),
    ("/api/v1/partner-withdrawals", "GET"),
}


def test_rotas_financeiras_publicadas_estao_montadas():
    montadas = {
        (getattr(route, "path", ""), method)
        for route in app.routes
        for method in (getattr(route, "methods", None) or [])
    }

    ausentes = sorted(ROTAS_FINANCEIRAS - montadas)
    assert not ausentes, f"rotas financeiras não montadas: {ausentes}"


def test_rotas_financeiras_publicadas_exigem_autenticacao_financeira():
    dependencias_por_rota = {}
    for route in app.routes:
        key = (getattr(route, "path", ""), "GET")
        if key not in ROTAS_FINANCEIRAS:
            continue
        dependencias_por_rota[key] = {
            getattr(getattr(dependency, "call", None), "__name__", "")
            for dependency in getattr(
                getattr(route, "dependant", None), "dependencies", []
            )
        }

    for route in sorted(ROTAS_FINANCEIRAS):
        assert "_req_fin" in dependencias_por_rota[route], (
            f"{route[0]} perdeu a dependência financeira explícita"
        )
