from copy import deepcopy

from app.services.legal_brain import EvidenceState, bridge_legal_chat_state


def test_comprovado_por_ia_permanece_inferencia_ate_revisao_humana():
    state = {
        "fatos": [
            {
                "id": "f1",
                "texto": "Pagamento consta do documento.",
                "classificacao": "comprovado",
                "documento_id": "doc-1",
            }
        ]
    }

    result = bridge_legal_chat_state(state, origin="ai")

    assert len(result.assertions) == 1
    assertion = result.assertions[0]
    assert assertion.id == "f1"
    assert assertion.state == EvidenceState.INFERENCIA_IA
    assert assertion.source_ids == ("doc-1",)
    assert assertion.validated_by_user_id is None


def test_comprovado_manual_exige_e_preserva_identidade_e_data():
    state = {
        "fatos": [
            {"id": "f1", "texto": "Fato revisado.", "classificacao": "confirmado"}
        ]
    }

    result = bridge_legal_chat_state(
        state,
        origin="manual",
        reviewer_user_id="adv-1",
        reviewed_at="2026-09-14T10:00:00-03:00",
    )

    assertion = result.assertions[0]
    assert assertion.state == EvidenceState.CONFIRMADO
    assert assertion.validated_by_user_id == "adv-1"
    assert assertion.validated_at == "2026-09-14T10:00:00-03:00"


def test_rotulos_sem_prova_viram_lacuna_e_vocabulario_desconhecido_e_ignorado():
    state = {
        "fatos": [
            {"texto": "Contrato integral não foi juntado.", "classificacao": "ausente"},
            {"texto": "Rótulo livre.", "classificacao": "certeza_total"},
        ],
        "pendencias": [
            {"descricao": "Confirmar data da ciência."},
            "Obter comprovante de pagamento.",
        ],
    }

    result = bridge_legal_chat_state(state)

    assert result.assertions == ()
    assert result.evidence_gaps == (
        "Contrato integral não foi juntado.",
        "Confirmar data da ciência.",
        "Obter comprovante de pagamento.",
    )
    assert result.ignored_items == 1


def test_alegacoes_e_controversia_mantem_estado_epistemico():
    state = {
        "fatos": [
            {"texto": "Cliente afirma pagamento.", "classificacao": "alegado"},
            {
                "texto": "Ré sustenta inadimplemento.",
                "classificacao": "alegado_parte_contraria",
            },
            {"texto": "Valor é controvertido.", "classificacao": "controvertido"},
            {"texto": "Hipótese analítica.", "classificacao": "inferido"},
            {"texto": "Versão superada.", "classificacao": "superado"},
        ]
    }

    result = bridge_legal_chat_state(state)

    assert [item.state for item in result.assertions] == [
        EvidenceState.ALEGADO_CLIENTE,
        EvidenceState.ALEGADO_PARTE_CONTRARIA,
        EvidenceState.CONTROVERTIDO,
        EvidenceState.INFERENCIA_IA,
        EvidenceState.DESCARTADO,
    ]


def test_bridge_nao_muta_estado_versionado_original():
    state = {
        "fatos": [
            {
                "texto": "Fato A",
                "classificacao": "comprovado",
                "source_ids": ["src-1", "src-1", "src-2"],
            }
        ]
    }
    before = deepcopy(state)

    result = bridge_legal_chat_state(state)

    assert state == before
    assert result.assertions[0].source_ids == ("src-1", "src-2")
