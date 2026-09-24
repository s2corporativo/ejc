import pytest

from app.core.licitacao_auditor import LicitacaoAuditor


@pytest.mark.asyncio
async def test_auditoria_sem_texto_falha_fechado(monkeypatch):
    auditor = LicitacaoAuditor()
    monkeypatch.setattr(auditor, "_extract_text_from_pdf", lambda _: "")

    out = await auditor.analyze_competitor_proposal(b"%PDF")

    assert out["status"] == "requires_manual_review"
    assert out["potential_flaws"] == []
    assert out["equivalence_issues"] == []
    assert "não foi realizada" in out["aviso"].lower()


@pytest.mark.asyncio
async def test_auditoria_sinaliza_apenas_achados_preliminares(monkeypatch):
    auditor = LicitacaoAuditor()
    monkeypatch.setattr(
        auditor,
        "_extract_text_from_pdf",
        lambda _: "Produto similar sem certificação ANVISA. Prazo de entrega superior a 30 dias.",
    )

    out = await auditor.analyze_competitor_proposal(b"%PDF")

    assert out["status"] == "success"
    assert len(out["potential_flaws"]) == 2
    assert len(out["equivalence_issues"]) == 1
    assert "Revisao do advogado obrigatoria" in out["aviso"]
