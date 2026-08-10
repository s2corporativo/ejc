"""Contratos estruturais do lifecycle documental consolidado.

São guardas de regressão para decisões arquiteturais deliberadas desta onda;
os fluxos DB-level de ownership/referências permanecem cobertos pelos testes de
domínio da subonda A1.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError


BACKEND = Path(__file__).parents[1]
REPO = Path(__file__).parents[2]
DOCUMENTS = BACKEND / "app/routers/documents.py"
DRIVE = BACKEND / "app/services/google_drive.py"
FRONTEND = REPO / "frontend/src/pages/Documentos.tsx"


def test_patch_documento_nao_aceita_case_id():
    from app.routers.documents import DocumentPatchRequest

    assert "case_id" not in DocumentPatchRequest.model_fields
    with pytest.raises(ValidationError):
        DocumentPatchRequest(case_id="caso-arbitrario")


def test_router_nao_faz_hard_delete_de_documents_nem_monta_google_api():
    source = DOCUMENTS.read_text(encoding="utf-8")

    assert "DELETE FROM documents" not in source
    assert "service_account" not in source
    assert "googleapiclient" not in source
    assert "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON" not in source
    assert "_get_or_create_case_folder" not in source


def test_router_usa_guarda_de_referencias_em_ambas_as_exclusoes():
    source = DOCUMENTS.read_text(encoding="utf-8")

    assert source.count("exigir_documento_sem_referencias_bloqueantes(") >= 2
    assert "document.deleted_at = datetime.now(timezone.utc)" in source


def test_drive_nao_bloqueia_event_loop_dos_handlers():
    source = DOCUMENTS.read_text(encoding="utf-8")

    for operacao in ("gd.upload_file", "gd.download_file", "gd.delete_file"):
        assert operacao in source
    assert source.count("await asyncio.to_thread(") >= 5


def test_hook_de_analise_documental_nao_esta_duplicado_no_router():
    source = DOCUMENTS.read_text(encoding="utf-8")

    assert "def _analisar_doc_bg" not in source
    assert "analisar_documento_bg" in source


def test_adapter_drive_deixa_scan_recursivo_marcado_como_legado():
    source = DRIVE.read_text(encoding="utf-8")

    assert '"lsjson", "-R", "--files-only"' in source
    assert "Fallback LEGADO O(N)" in source
    assert '"lsjson", dest_file, "--stat"' in source


def test_frontend_nao_move_documento_por_patch_e_usa_post_canonico():
    source = FRONTEND.read_text(encoding="utf-8")

    assert "payload.case_id" not in source
    assert "patchLote({ case_id:" not in source
    assert "editForm.case_id" not in source
    assert "`/cases/${loteCaso}/documentos/${d.id}/vincular`" in source


def test_frontend_so_expoe_vinculo_para_roles_do_backend():
    source = FRONTEND.read_text(encoding="utf-8")

    for role in (
        "superadmin",
        "admin",
        "socio",
        "advogado",
        "advogado_auxiliar",
        "estagiario",
    ):
        assert f'"{role}"' in source
    assert '"financeiro"' not in source.split("PAPEIS_VINCULO_DOCUMENTAL", 1)[1].split("]);", 1)[0]
    assert '"secretaria"' not in source.split("PAPEIS_VINCULO_DOCUMENTAL", 1)[1].split("]);", 1)[0]
