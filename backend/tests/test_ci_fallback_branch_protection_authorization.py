from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROTECTION = ROOT / "scripts" / "governanca" / "branch-protection.sh"
ACTIVATE = ROOT / "scripts" / "ci-fallback-activate.sh"


def test_modo_fallback_exige_autorizacao_registrada_998():
    src = PROTECTION.read_text(encoding="utf-8")

    assert 'FALLBACK_AUTHORIZATION="${EJC_FALLBACK_AUTHORIZATION:-}"' in src
    assert '[ "$FALLBACK_AUTHORIZATION" = "998" ]' in src
    assert "decisão registrada na Issue #998" in src
    assert "ATO ADMINISTRATIVO PROTEGIDO" in src


def test_ativador_canonico_injeta_autorizacao_sem_bypass():
    src = ACTIVATE.read_text(encoding="utf-8")

    assert (
        "EJC_FALLBACK_AUTHORIZATION=998 bash "
        "scripts/governanca/branch-protection.sh --fallback"
    ) in src
    assert "--force" not in src
    assert "bypass" not in src.lower()
