"""Regressões dos redirects 308 legados de novos_modulos (PR #1224)."""

from app.routers import novos_modulos


def _location(response) -> str:
    return response.headers["location"]


def test_redirect_precificacao_interpolando_rule_id():
    response = novos_modulos._redirect_get_precificacao_calcular_rule_id("regra-123")
    assert response.status_code == 308
    assert _location(response) == "/api/modulos/precificacao/calcular/regra-123"


def test_redirect_inadimplencia_interpolando_alert_id():
    response = novos_modulos._redirect_patch_inadimplencia_alertas_alert_id_resolver("alerta-456")
    assert response.status_code == 308
    assert _location(response) == "/api/modulos/inadimplencia/alertas/alerta-456/resolver"


def test_redirects_cofre_interpolam_document_id():
    document_id = "doc-789"
    casos = [
        (
            novos_modulos._redirect_get_cofre_documentos_document_id_logs(document_id),
            f"/api/modulos/cofre/documentos/{document_id}/logs",
        ),
        (
            novos_modulos._redirect_post_cofre_documentos_document_id_registrar_acesso(document_id),
            f"/api/modulos/cofre/documentos/{document_id}/registrar-acesso",
        ),
        (
            novos_modulos._redirect_patch_cofre_documentos_document_id_sensibilidade(document_id),
            f"/api/modulos/cofre/documentos/{document_id}/sensibilidade",
        ),
    ]
    for response, destino in casos:
        assert response.status_code == 308
        assert _location(response) == destino
