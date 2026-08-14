from datetime import datetime, timezone

from app.services.ai import reranker


def _candidate(**overrides):
    hoje = datetime.now(timezone.utc).date().isoformat()
    base = {
        "doc_id": "doc-1",
        "chunk_id": "chunk-1",
        "titulo": "Tema 466 STJ",
        "categoria": "jurisprudencia_stj",
        "fonte": "https://processo.stj.jus.br/repetitivos/temas_repetitivos/pesquisa.jsp?pesquisa_livre=466",
        "confianca": "alta",
        "tribunal": "STJ",
        "extra": {
            "score_autoridade": 90,
            "area_juridica": "consumidor_bancario",
            "last_verified_at": hoje,
        },
        "situacao_juridica": {
            "code": "nao_aplicavel",
            "label": "Não aplicável",
            "warning": False,
        },
    }
    base.update(overrides)
    return base


def test_score_autoridade_entra_como_sinal_secundario():
    alto, bonus_alto = reranker._enrich(
        _candidate(), "fraude bancária STJ consumidor"
    )
    baixo_extra = dict(_candidate()["extra"])
    baixo_extra["score_autoridade"] = 10
    baixo, bonus_baixo = reranker._enrich(
        _candidate(extra=baixo_extra), "fraude bancária STJ consumidor"
    )
    assert bonus_alto > bonus_baixo
    assert (
        alto["governance_factors"]["score_autoridade"]
        > baixo["governance_factors"]["score_autoridade"]
    )


def test_aderencia_de_tribunal_e_area_e_auditavel():
    item, _ = reranker._enrich(
        _candidate(), "responsabilidade por fraude bancária no STJ"
    )
    assert item["governance_factors"]["aderencia_jurisdicao_area"] > 0


def test_aderencia_normaliza_hifen_de_trf_e_trt():
    trf, _ = reranker._enrich(
        _candidate(tribunal="TRF6"),
        "competência federal e precedente do TRF-6",
    )
    trt, _ = reranker._enrich(
        _candidate(tribunal="TRT3"),
        "precedente trabalhista do TRT-3",
    )
    assert trf["governance_factors"]["aderencia_jurisdicao_area"] > 0
    assert trt["governance_factors"]["aderencia_jurisdicao_area"] > 0


def test_verificacao_recente_nao_confunde_com_data_do_julgamento():
    recente, _ = reranker._enrich(_candidate(), "fraude bancária")
    antigo_extra = dict(_candidate()["extra"])
    antigo_extra["last_verified_at"] = "2010-01-01"
    antigo, _ = reranker._enrich(
        _candidate(extra=antigo_extra), "fraude bancária"
    )
    assert (
        recente["governance_factors"]["verificacao_recente"]
        > antigo["governance_factors"]["verificacao_recente"]
    )


def test_norma_revogada_continua_penalizada():
    item, _ = reranker._enrich(
        _candidate(
            situacao_juridica={
                "code": "revogada",
                "label": "Revogada",
                "warning": True,
            }
        ),
        "fraude bancária",
    )
    assert item["governance_factors"]["situacao_juridica"] < 0
