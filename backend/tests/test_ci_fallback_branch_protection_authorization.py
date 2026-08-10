from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROTECTION = ROOT / "scripts" / "governanca" / "branch-protection.sh"
ACTIVATE = ROOT / "scripts" / "ci-fallback-activate.sh"
FALLBACK = ROOT / "scripts" / "ci-fallback.sh"


def test_modo_fallback_exige_autorizacao_registrada_998():
    src = PROTECTION.read_text(encoding="utf-8")

    assert 'FALLBACK_AUTHORIZATION="${EJC_FALLBACK_AUTHORIZATION:-}"' in src
    assert '[ "$FALLBACK_AUTHORIZATION" = "998" ]' in src
    assert "decisão registrada na Issue #998" in src
    assert "ATO ADMINISTRATIVO PROTEGIDO" in src


def test_execucao_sem_argumento_e_somente_leitura():
    src = PROTECTION.read_text(encoding="utf-8")

    assert 'MODO="${1:---verificar}"' in src
    assert 'MODO="${1:---cloud}"' not in src
    assert "DEFAULT seguro" in src
    assert "Sem argumento" in src and "não altera a proteção" in src
    assert 'STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"' in src


def test_ativador_canonico_injeta_autorizacao_sem_bypass():
    src = ACTIVATE.read_text(encoding="utf-8")

    assert 'EJC_FALLBACK_AUTHORIZATION=998 EJC_FALLBACK_APP_ID="$FALLBACK_APP_ID"' in src
    assert "branch-protection.sh --fallback" in src
    assert "--force" not in src
    assert "bypass" not in src.lower()


def test_fallback_branch_protection_exige_check_vinculado_a_app():
    src = PROTECTION.read_text(encoding="utf-8")

    assert 'FALLBACK_APP_ID="${EJC_FALLBACK_APP_ID:-}"' in src
    assert '"checks"' not in src  # payload é construído com jq, não JSON estático inseguro
    assert 'checks: [' in src
    assert '{context: "EJC Local Full Gate", app_id: $app_id}' in src
    assert '(.required_status_checks.contexts // []) == []' in src
    assert '.required_status_checks.checks[0].app_id == $app_id' in src
    assert "app_id=-1" in src


def test_full_gate_publica_check_run_e_valida_app_id():
    src = FALLBACK.read_text(encoding="utf-8")

    assert 'FALLBACK_APP_ID="${EJC_FALLBACK_APP_ID:-}"' in src
    assert 'repos/$REPO/check-runs' in src
    assert 'repos/$REPO/statuses/$SHA' in src  # apenas statuses informativos dos subgates
    assert 'if [ "$context" = "$CONTEXT_FULL" ]' in src
    assert 'post_full_check "$state" "$description"' in src
    assert '.app.id // -1' in src
    assert '[ "$app_id" != "$FALLBACK_APP_ID" ]' in src
    assert 'select(.name == $c and .app.id == $app_id and .conclusion == "success")' in src


def test_ativador_propaga_app_id_para_scheduler_persistente():
    src = ACTIVATE.read_text(encoding="utf-8")

    assert '[[ "$FALLBACK_APP_ID" =~ ^[1-9][0-9]*$ ]]' in src
    assert "Environment=EJC_FALLBACK_APP_ID=$FALLBACK_APP_ID" in src
    assert "EJC_FALLBACK_APP_ID='$FALLBACK_APP_ID'" in src
