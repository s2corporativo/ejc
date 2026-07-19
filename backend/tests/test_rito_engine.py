from app.services.rito_engine import catalogo_ritos, identificar_rito


def test_identifica_jec_e_jornada_recursal():
    resultado = identificar_rito({
        "area": "civil",
        "texto": "Juizado Especial Cível. Sentença. Recurso inominado para a Turma Recursal conforme Lei 9.099.",
    })
    assert resultado["codigo"] == "jec"
    assert resultado["etapa_atual"] in {"recursal", "pos_sentenca"}
    assert "recurso inominado" in resultado["etapas"]
    assert resultado["requer_confirmacao_humana"] is True


def test_identifica_processo_administrativo_de_transito():
    resultado = identificar_rito({
        "area": "transito",
        "tipo_documento": "multa_transito",
        "texto": "Auto de infração de trânsito com RENAVAM. Prazo para defesa e recurso à JARI e CETRAN.",
    })
    assert resultado["codigo"] == "transito_administrativo"
    assert resultado["instancia"] == "administrativa"
    assert "defesa prévia" in resultado["etapas"]


def test_identifica_recursos_excepcionais_sem_confundir_instancia():
    stj = identificar_rito({
        "texto": "Recurso Especial ao Superior Tribunal de Justiça, com prequestionamento e juízo de admissibilidade.",
    })
    assert stj["codigo"] == "recurso_especial_stj"
    assert stj["instancia"] == "superior"

    stf = identificar_rito({
        "area": "constitucional",
        "texto": "Recurso Extraordinário ao Supremo Tribunal Federal com demonstração de repercussão geral.",
    })
    assert stf["codigo"] == "recurso_extraordinario_stf"
    assert stf["instancia"] == "superior"


def test_baixa_confianca_exige_selecao_manual():
    resultado = identificar_rito({"texto": "documento sem marcadores processuais suficientes"})
    assert resultado["confianca"] < 0.64
    assert any("selecionar rito manualmente" in alerta for alerta in resultado["alertas"])


def test_catalogo_tem_juizados_e_tribunais_superiores():
    codigos = {item["codigo"] for item in catalogo_ritos()}
    assert {"jec", "jef", "jefaz", "jecrim"}.issubset(codigos)
    assert {"recurso_especial_stj", "recurso_extraordinario_stf"}.issubset(codigos)
