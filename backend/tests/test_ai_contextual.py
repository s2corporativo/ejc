from types import SimpleNamespace

from app.services.ai_contextual import (
    classificar_documento,
    proximas_skills,
    ranquear_skills_contextuais,
)


def _skill(name, display_name, area="juridico", requires_case=False):
    return SimpleNamespace(
        id=f"id-{name}",
        name=name,
        display_name=display_name,
        description=display_name,
        area=area,
        requires_case=requires_case,
        requires_human_review=True,
        oab_restricted=False,
    )


def test_classifica_contestacao_sem_expor_trecho():
    resultado = classificar_documento(
        "contestacao_empresa.pdf",
        "CONTESTAÇÃO. Preliminarmente, requer a impugnação específica dos pedidos.",
    )

    assert resultado["tipo"] == "contestacao"
    assert resultado["confianca"] >= 0.7
    assert "maquina-replica" in resultado["skills_sugeridas"]
    assert "CONTESTAÇÃO" not in str(resultado)
    assert resultado["metodo"] == "regras_locais_v3_motor_ritos"
    assert resultado["requer_confirmacao_humana"] is True
    assert resultado["jornada_sugerida"]["metodo"] == "motor_ritos_deterministico_v1"


def test_reconhece_multa_transito_e_sugere_fluxo_pertinente():
    resultado = classificar_documento(
        "auto_infracao.pdf",
        "Auto de Infração de Trânsito. Órgão autuador, placa, RENAVAM, código da infração e prazo para recurso à JARI.",
    )

    assert resultado["tipo"] == "multa_transito"
    assert resultado["area_sugerida"] == "transito"
    assert resultado["rito_sugerido"] == "administrativo de transito"
    assert "recurso-jari-cetran" in resultado["skills_sugeridas"]
    assert "renavam" in resultado["campos_esperados"]
    assert resultado["jornada_sugerida"]["codigo"] == "transito_administrativo"


def test_reconhece_contrato_bancario_e_sugere_analise_financeira():
    resultado = classificar_documento(
        "financiamento.pdf",
        "Instituição financeira. Custo Efetivo Total, taxa efetiva mensal e anual, saldo devedor e sistema de amortização.",
    )

    assert resultado["tipo"] == "contrato_bancario"
    assert resultado["area_sugerida"] == "bancario"
    assert resultado["surface_sugerida"] == "financeiro"
    assert "revisional-juros-bancarios" in resultado["skills_sugeridas"]
    assert "cet" in resultado["campos_esperados"]


def test_reconhece_juizado_e_recurso_superior():
    jec = classificar_documento(
        "sentenca_jec.pdf",
        "Juizado Especial Cível. Sentença. Recurso inominado dirigido à Turma Recursal, nos termos da Lei 9.099.",
    )
    assert jec["tipo"] == "juizado_especial_civel"
    assert jec["jornada_sugerida"]["codigo"] == "jec"
    assert "recurso inominado" in jec["jornada_sugerida"]["etapas"]

    stj = classificar_documento(
        "recurso_especial.pdf",
        "Recurso Especial ao Superior Tribunal de Justiça. Prequestionamento e juízo de admissibilidade.",
    )
    assert stj["tipo"] == "recurso_especial"
    assert stj["jornada_sugerida"]["codigo"] == "recurso_especial_stj"
    assert stj["instancia_sugerida"] == "superior"


def test_reconhece_areas_adicionais():
    sucessoes = classificar_documento(
        "inventario.pdf",
        "Inventário do espólio, com herdeiros, bens, dívidas e proposta de partilha.",
    )
    assert sucessoes["area_sugerida"] == "sucessoes"

    saude = classificar_documento(
        "negativa.pdf",
        "Plano de saúde e negativa de cobertura de procedimento médico urgente, com relatório médico.",
    )
    assert saude["area_sugerida"] == "saude"

    lgpd = classificar_documento(
        "incidente.pdf",
        "Incidente de segurança envolvendo dados pessoais, controlador, operador e comunicação à ANPD conforme LGPD.",
    )
    assert lgpd["area_sugerida"] == "digital_lgpd"


def test_ranqueia_poucas_acoes_por_aba_e_area():
    skills = [
        _skill("raio-x-processual", "Raio-X Processual"),
        _skill("detector-contradicoes", "Detector de Contradições", "provas"),
        _skill("contestacao-trabalhista", "Contestação", "trabalhista"),
        _skill("reclamacao-trabalhista", "Reclamação", "trabalhista"),
        _skill("acao-despejo", "Despejo", "imobiliario"),
    ]

    resultado = ranquear_skills_contextuais(
        skills,
        surface="processos",
        area="trabalhista",
        phase="conhecimento",
        limit=3,
    )

    nomes = [item["skill"].name for item in resultado]
    assert len(nomes) == 3
    assert "raio-x-processual" in nomes
    assert "contestacao-trabalhista" in nomes
    assert "acao-despejo" not in nomes
    assert all(item["reason"] for item in resultado)


def test_remove_skill_que_exige_caso_em_contexto_geral():
    skills = [
        _skill("raio-x-processual", "Raio-X", requires_case=True),
        _skill("sintese-processo", "Síntese", requires_case=False),
    ]
    resultado = ranquear_skills_contextuais(
        skills,
        surface="resumo",
        area="civel",
        has_case=False,
    )
    assert [item["skill"].name for item in resultado] == ["sintese-processo"]


def test_proxima_acao_e_somente_sugestao():
    assert proximas_skills("maquina-replica") == [
        "detector-contradicoes",
        "simulador-defesa-adversarial",
    ]
