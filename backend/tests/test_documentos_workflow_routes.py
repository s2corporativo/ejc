"""Contratos HTTP estáticos do workflow documental simplificado."""
from __future__ import annotations

from app.routers import documentos_workflow


def _route(path: str, method: str):
    for route in documentos_workflow.router.routes:
        if route.path == path and method in (getattr(route, "methods", None) or set()):
            return route
    raise AssertionError(f"rota ausente: {method} {path}")


def test_rotas_workflow_exigem_dependencia_de_usuario():
    for path, method in (
        ("/documents/workflow/stats", "GET"),
        ("/documents/workflow/inbox", "GET"),
        ("/documents/workflow/upload", "POST"),
        ("/documents/{doc_id}/versions", "GET"),
        ("/documents/{doc_id}/history", "GET"),
    ):
        route = _route(path, method)
        deps = {
            getattr(dep.call, "__name__", "")
            for dep in getattr(route, "dependant", None).dependencies
            if getattr(dep, "call", None) is not None
        }
        assert "get_current_user" in deps
        assert "get_db" in deps


def test_upload_workflow_e_201_e_inbox_limita_page_size():
    upload = _route("/documents/workflow/upload", "POST")
    assert upload.status_code == 201

    inbox = _route("/documents/workflow/inbox", "GET")
    page_size = next(
        field for field in inbox.dependant.query_params if field.name == "page_size"
    )
    assert page_size.field_info.metadata
