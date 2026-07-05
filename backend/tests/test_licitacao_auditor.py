# ── tests/test_licitacao_auditor.py ───────────────────────────────────────────
# Motor de regras deterministico do auditor de licitacoes (Lei 14.133/21).
# _aplicar_regras e puro (texto -> achados), entao testa-se sem PDF nem rede.
from app.core.licitacao_auditor import LicitacaoAuditor, _norm, REGRAS


def _regras(texto):
    return LicitacaoAuditor._aplicar_regras(texto)


def test_texto_limpo_nao_gera_achados():
    r = _regras("Proposta regular, com todos os documentos de habilitacao anexados.")
    assert r["falha"] == [] and r["equivalencia"] == []


def test_regra_anvisa_dispara_com_e_sem_acento():
    # A normalizacao colapsa 'certificação' e 'certificacao' na mesma regra.
    for t in ("Produto SEM CERTIFICAÇÃO ANVISA no lote.",
              "produto sem certificacao anvisa"):
        r = _regras(t)
        assert any("ANVISA" in m for m in r["falha"]), t


def test_similar_sem_equivalencia_vira_equivalencia():
    r = _regras("Ofertamos produto similar ao especificado.")
    assert len(r["equivalencia"]) == 1
    assert r["falha"] == []


def test_similar_com_laudo_nao_falso_positivo():
    """Excludente: se a propria proposta traz laudo/equivalencia comprovada,
    a regra de 'similar' NAO deve disparar."""
    r = _regras("Produto similar, com laudo de equivalencia tecnica anexo (equivalencia comprovada).")
    assert r["equivalencia"] == []


def test_regularidade_fiscal_positiva_com_efeito_negativa_nao_dispara():
    r = _regras("Apresenta certidao positiva com efeito de negativa, valida.")
    assert all("irregularidade" not in m.lower() for m in r["falha"])


def test_multiplos_achados_acumulam():
    texto = (
        "Produto sem certificacao anvisa. "
        "Prazo de entrega superior a 60 dias. "
        "Menciona subcontratacao de parte do objeto."
    )
    r = _regras(texto)
    assert len(r["falha"]) >= 3


def test_me_epp_sinaliza_beneficio():
    r = _regras("Declaramos enquadramento como microempresa (ME/EPP).")
    assert any("ME/EPP" in m or "beneficio" in m.lower() for m in r["falha"])


def test_norm_remove_acentos_e_caixa():
    assert _norm("Equivalência TÉCNICA") == "equivalencia tecnica"


def test_todas_as_regras_tem_id_unico_e_bucket_valido():
    ids = [r.id for r in REGRAS]
    assert len(ids) == len(set(ids)), "ids de regra duplicados"
    assert all(r.bucket in ("falha", "equivalencia") for r in REGRAS)


# ── Relatório de auditoria em PDF (Visual Law) ────────────────────────────────
def test_report_pdf_html_escapa_payload_e_lista_achados():
    """O HTML do relatório escapa toda string do payload (anti-injeção) e
    materializa os achados computados pelo motor de regras."""
    from app.routers.licitacao_auditoria import ReportIn, AnaliseIn, _html_report

    payload = ReportIn(
        analise=AnaliseIn(
            summary="Analise preliminar concluida.",
            potential_flaws=["Ausencia de atestado <script>alert(1)</script>"],
            equivalence_issues=["Produto similar sem laudo"],
            aviso="Revisao obrigatoria.",
        ),
        edital="Pregao 12/2026",
        concorrente="ACME <b>LTDA</b>",
    )
    html = _html_report(payload)
    # achados presentes
    assert "Ausencia de atestado" in html
    assert "Produto similar sem laudo" in html
    # injeção neutralizada: nenhuma tag executável do payload sobrevive crua
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "<b>LTDA</b>" not in html  # nome do concorrente escapado no banner


def test_report_schema_limita_tamanho_do_payload():
    """Listas gigantes são rejeitadas antes de chegar ao WeasyPrint."""
    import pytest
    from pydantic import ValidationError

    from app.routers.licitacao_auditoria import ReportIn

    with pytest.raises(ValidationError):
        ReportIn(analise={"summary": "x", "potential_flaws": ["a"] * 201,
                          "equivalence_issues": []})
