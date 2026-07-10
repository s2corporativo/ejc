import pytest
from pydantic import ValidationError

from app.schemas.google_drive_knowledge import (
    GoogleDriveCuradoriaApplyRequest,
    GoogleDriveCuradoriaPreviewRequest,
)


def test_preview_defaults_to_dry_run_only_changes():
    req = GoogleDriveCuradoriaPreviewRequest()
    assert req.limit == 500
    assert req.only_changes is True


def test_apply_requires_exact_confirmation():
    with pytest.raises(ValidationError):
        GoogleDriveCuradoriaApplyRequest(
            limit=100,
            only_changes=True,
            confirmacao="CONFIRMAR",
        )


def test_apply_accepts_exact_confirmation():
    req = GoogleDriveCuradoriaApplyRequest(
        limit=100,
        only_changes=True,
        confirmacao="RECLASSIFICAR_RAG_DRIVE",
    )
    assert req.confirmacao == "RECLASSIFICAR_RAG_DRIVE"


def test_curadoria_routes_are_registered_under_rag():
    from app.main import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/rag/google-drive/curadoria/preview" in paths
    assert "/api/rag/google-drive/curadoria/apply" in paths
