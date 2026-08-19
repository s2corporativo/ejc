from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ejc-release-gate.yml"


def test_release_gate_exige_gold_real_quando_nucleo_juridico_ia_muda() -> None:
    texto = WORKFLOW.read_text(encoding="utf-8")

    assert "Detectar alteração no núcleo jurídico de IA" in texto
    assert "Gold set humano bloqueante para mudança de IA" in texto
    assert "steps.ai_legal_scope.outputs.changed == 'true'" in texto
    assert "--require-real" in texto
    assert "--min-total 75" in texto
    assert "--min-casos-area 15" in texto
    assert "consumidor,trabalhista,civel,penal,tributario" in texto
    assert "backend/app/(agent/|system_prompts/" in texto
    assert "services/ai" in texto
    assert "services/(rag|rerank|citation|knowledge)" in texto
    assert "services/legal_" in texto
    assert "peca_geracao" in texto
    assert "raio_x" in texto
