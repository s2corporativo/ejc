from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ejc-release-gate.yml"

# O GitHub Actions foi ARQUIVADO em 31/08 (commit `b77ff4c`): os workflows saíram
# para `docs/arquivo/ci/github-actions-legacy/` e o Woodpecker virou o CI oficial.
# Este módulo inteiro assertava sobre um YAML que já não é executado por ninguém —
# guarda sem objeto. Fica DORMENTE em vez de deletado: se o Actions voltar, o
# arquivo reaparece e as travas voltam a valer sozinhas, sem depender de alguém
# lembrar. Não aponto para a cópia arquivada de propósito: workflow arquivado não
# roda, e guarda sobre arquivo que não roda é decorativo.
pytestmark = pytest.mark.skipif(
    not WORKFLOW.is_file(),
    reason="GitHub Actions arquivado em 31/08 (b77ff4c) — workflows movidos para docs/arquivo/ci/github-actions-legacy/; Woodpecker é o CI oficial",
)


def test_release_gate_exige_gold_real_quando_nucleo_juridico_ia_muda() -> None:
    texto = WORKFLOW.read_text(encoding="utf-8")

    assert "Detectar alteração no núcleo jurídico de IA" in texto
    assert "Gold set humano bloqueante para mudança de IA" in texto
    assert "steps.ai_legal_scope.outputs.changed == 'true'" in texto
    assert "--require-real" in texto
    assert "--min-total 105" in texto
    assert "--min-casos-area 15" in texto
    assert "consumidor,trabalhista,civel,penal,tributario,empresarial,administrativo" in texto
    assert "backend/app/(agent/|system_prompts/" in texto
    assert "services/ai" in texto
    assert "services/(rag|rerank|citation|knowledge)" in texto
    assert "services/legal_" in texto
    assert "peca_geracao" in texto
    assert "raio_x" in texto


def test_release_gate_exige_definition_of_done_minima_em_pr_humano() -> None:
    texto = WORKFLOW.read_text(encoding="utf-8")

    assert "Definition of Done mínima do PR" in texto
    assert "github.event_name == 'pull_request'" in texto
    assert "github.event.pull_request.user.login == 'dependabot[bot]'" in texto
    assert "github.actor == 'dependabot[bot]'" in texto
    assert 'grep -Fqi -- "- [x] $ITEM"' in texto
    for item in (
        "DoD revisada para o escopo deste PR",
        "Testes compatíveis com o escopo executados",
        "Riscos jurídicos/LGPD avaliados",
        "Rollback definido",
        "Sem quebra conhecida de módulo existente",
    ):
        assert item in texto
    assert "Definition of Done mínima confirmada no Release Gate" in texto
