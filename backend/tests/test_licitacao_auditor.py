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
