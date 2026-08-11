from __future__ import annotations

from pathlib import Path


RAIZ = Path(__file__).resolve().parents[2]
GOVERNANCA = RAIZ / "scripts/governanca/ci-local-governanca.sh"


def test_mudanca_sensivel_nao_aceita_marcador_literal_do_corpo_do_pr():
    fonte = GOVERNANCA.read_text(encoding="utf-8")
    bloco = fonte[fonte.index('if [ "$SENSITIVE_CHANGED" -eq 1 ]; then') :]

    assert "security-auditor: executado" not in bloco
    assert "marcador literal" not in bloco
    assert 'EVIDENCE_FILE="$EVIDENCE_DIR/$HEAD_SHA.json"' in bloco
    assert 'EVIDENCE_ISSUER="$(jq -r' in bloco
    assert '[ "$EVIDENCE_ISSUER" = "security-auditor" ]' in bloco


def test_evidencia_security_auditor_e_vinculada_ao_sha_e_protegida_por_owner_mode():
    fonte = GOVERNANCA.read_text(encoding="utf-8")
    bloco = fonte[fonte.index('if [ "$SENSITIVE_CHANGED" -eq 1 ]; then') :]

    assert 'HEAD_SHA="$(git rev-parse HEAD)"' in bloco
    assert '[ ! -L "$EVIDENCE_DIR" ]' in bloco
    assert '[ ! -L "$EVIDENCE_FILE" ]' in bloco
    assert "stat -c '%u' \"$EVIDENCE_DIR\"" in bloco
    assert "stat -c '%u' \"$EVIDENCE_FILE\"" in bloco
    assert "8#022" in bloco
    assert '[ "$EVIDENCE_SHA" = "$HEAD_SHA" ]' in bloco
    assert '[ "$EVIDENCE_RESULT" = "completed" ]' in bloco
