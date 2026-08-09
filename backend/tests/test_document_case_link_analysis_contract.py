"""Contrato do hook de análise estratégica usado após vínculo documental."""
from __future__ import annotations

from pathlib import Path


HOOK = Path(__file__).parents[1] / "app/services/document_analysis_hook.py"


def test_hook_preserva_ailog_hitl_e_escopo_do_caso():
    src = HOOK.read_text(encoding="utf-8")
    assert "analisar_caso(" in src
    assert "scope_client_id=" in src
    assert "case_id=case_id" in src
    assert "AILog(" in src
    assert "AIStatusHITL.gerado" in src
    assert "classificar_risco_ia" in src
