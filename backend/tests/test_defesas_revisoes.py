from app.routers.defesas_revisoes import (
    ADVOGADO_ROLES,
    JURIDICO_ROLES,
    MODALIDADES,
    _normalizar_resultado,
    _parse_json,
)
from app.routers.defesas_revisoes_avancado import (
    _matriz_teses,
    _resultado_completude,
)


def test_catalogo_tem_as_cinco_jornadas_solicitadas():
    assert set(MODALIDADES) == {
        "multa_transito",
        "multa_ambiental",
        "multa_administrativa",
        "revisao_contratual",
        "revisao_bancaria",
    }


def test_parse_json_aceita_resposta_com_ruido():
    assert _parse_json('texto antes {"resumo":"ok"} texto depois') == {
        "resumo": "ok"
    }


def test_normalizacao_impede_peca_fora_do_catalogo_e_corrige_nome_antigo():
    out = _normalizar_resultado(
        "multa_transito",
        {"peca_recomendada": {"codigo": "apelacao", "nome": "Apelação"}},
        "",
    )
    assert out["peca_recomendada"]["codigo"] == "defesa_administrativa"
    assert out["peca_recomendada"]["nome"] == "Defesa Administrativa"
    assert out["motor_peca_codigo"] == "defesa_administrativa"
    assert out["revisao_obrigatoria"] is True


def test_ambiental_nao_presume_defesa_federal_sem_identificar_ibama():
    out = _normalizar_resultado(
        "multa_ambiental",
        {"orgao_ou_instituicao": "Secretaria Municipal", "peca_recomendada": {"codigo": "apelacao"}},
        "",
    )
    assert out["peca_recomendada"]["codigo"] == "recurso_administrativo"


def test_ambiental_pode_selecionar_defesa_especializada_quando_ibama_e_fase_defesa():
    out = _normalizar_resultado(
        "multa_ambiental",
        {
            "orgao_ou_instituicao": "IBAMA",
            "fase": "defesa do auto",
            "peca_recomendada": {"codigo": "fora_catalogo"},
        },
        "",
    )
    assert out["peca_recomendada"]["codigo"] == "defesa_administrativa_ambiental"


def test_revisao_bancaria_segue_para_gerador_geral_quando_sem_codigo_motor():
    out = _normalizar_resultado(
        "revisao_bancaria",
        {"peca_recomendada": {"codigo": "peticao_inicial", "nome": "Ação revisional"}},
        "",
    )
    assert out["peca_recomendada"]["codigo"] == "peticao_inicial"
    assert out["motor_peca_codigo"] is None
    assert out["area"] == "bancario"


def test_normalizacao_blinda_arrays_e_bloqueia_redacao_com_pendencia():
    out = _normalizar_resultado(
        "multa_administrativa",
        {
            "teses": "texto indevido",
            "documentos_faltantes": ["processo integral"],
            "checklist_obrigatorio": [
                {"item": "confirmar ciência", "status": "pendente", "impeditivo": True}
            ],
        },
        "",
    )
    assert out["teses"] == []
    assert out["completude_juridica"]["nivel"] == "nao_apto_para_redacao"
    assert out["completude_juridica"]["pode_gerar_peca"] is False


def test_completude_avancada_classifica_tres_estados():
    assert _resultado_completude({"documentos_faltantes": ["contrato"]})["nivel"] == "nao_apto_para_redacao"
    assert _resultado_completude({"checklist_obrigatorio": []})["nivel"] == "apto_com_ressalvas"
    assert _resultado_completude({
        "checklist_obrigatorio": [{"item": "contrato", "status": "atendido", "impeditivo": True}]
    })["nivel"] == "apto_para_redacao"


def test_matriz_teses_separa_formal_e_merito_e_vincula_provas():
    matriz = _matriz_teses({
        "vicios_formais": [{"titulo": "falta de motivação", "fundamento": "verificar", "risco": "baixo"}],
        "teses": [{"titulo": "ausência de materialidade", "fatos": ["laudo incompleto"], "provas": ["laudo"], "forca": 80}],
    })
    assert matriz[0]["tipo"] == "formal"
    assert matriz[1]["tipo"] == "merito"
    assert matriz[1]["provas"] == ["laudo"]


def test_roles_sao_allowlists_explicitas_sem_financeiro_e_sem_geracao_auxiliar():
    assert "financeiro" not in JURIDICO_ROLES
    assert "financeiro" not in ADVOGADO_ROLES
    assert "estagiario" in JURIDICO_ROLES
    assert "estagiario" not in ADVOGADO_ROLES
    assert "advogado_auxiliar" in JURIDICO_ROLES
    assert "advogado_auxiliar" not in ADVOGADO_ROLES
