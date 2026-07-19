from app.routers.documento_ia import _aplicar_classificacao_contextual


def test_multa_transito_prepara_area_e_rito_do_intake():
    resultado = {
        "classificacao": {"area": "civil"},
        "intake_result": {"caso": {"area": "civil"}},
    }

    _aplicar_classificacao_contextual(
        resultado,
        filename="auto_infracao.pdf",
        texto_sanitizado=(
            "Auto de Infração de Trânsito. Órgão autuador, placa, RENAVAM, "
            "código da infração, identificação do condutor e recurso à JARI."
        ),
    )

    assert resultado["classificacao_contextual"]["tipo"] == "multa_transito"
    assert resultado["classificacao"]["area"] == "transito"
    assert resultado["classificacao"]["rito"] == "administrativo de transito"
    assert resultado["classificacao"]["area_anterior"] == "civil"
    assert resultado["intake_result"]["caso"]["area"] == "transito"
    assert "recurso-jari-cetran" in resultado["acoes_contextuais_sugeridas"]


def test_contrato_bancario_prepara_area_sem_apagar_origem():
    resultado = {
        "classificacao": {"area": "consumidor", "subarea": "contrato"},
        "intake_result": {"caso": {}},
    }

    _aplicar_classificacao_contextual(
        resultado,
        filename="financiamento.pdf",
        texto_sanitizado=(
            "Instituição financeira, custo efetivo total, taxa efetiva mensal e anual, "
            "saldo devedor e sistema de amortização."
        ),
    )

    assert resultado["classificacao"]["area"] == "bancario"
    assert resultado["classificacao"]["area_anterior"] == "consumidor"
    assert resultado["classificacao"]["requer_confirmacao_humana"] is True
    assert resultado["intake_result"]["caso"]["area"] == "bancario"
