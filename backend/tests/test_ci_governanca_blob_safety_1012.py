from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GOV = ROOT / "scripts" / "governanca" / "ci-local-governanca.sh"


def test_governanca_varre_blob_git_e_nao_abre_path_materializado():
    source = GOV.read_text(encoding="utf-8")

    assert 'git cat-file -t "HEAD:$f"' in source
    assert 'git cat-file blob "HEAD:$f"' in source
    assert 'grep -EIn "$PADROES" -- "$f"' not in source
    assert '[ -f "$f" ]' not in source
    assert "Symlinks do commit poderiam" in source


def test_governanca_rejeita_objeto_nao_blob_e_path_com_controle():
    source = GOV.read_text(encoding="utf-8")

    assert '[[ "$f" =~ [[:cntrl:]] ]]' in source
    assert 'object_type' in source
    assert '[ "$object_type" = "blob" ]' in source
    assert "objeto alterado não é blob regular" in source


def test_governanca_e_nul_safe_na_enumeracao_de_paths():
    source = GOV.read_text(encoding="utf-8")

    assert 'git diff --name-only -z "$BASE...HEAD"' in source
    assert "while IFS= read -r -d '' f" in source


def test_root_of_trust_inclui_worker_e_auth():
    source = GOV.read_text(encoding="utf-8")

    for marker in (
        "ci-local\\.sh",
        "ci-fallback",
        "ci-worker-isolation",
        "ci_evidence",
        "github-app-auth",
        "branch-protection",
        "ci-local-governanca",
    ):
        assert marker in source
    assert "security-auditor: executado" in source
