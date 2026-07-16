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
    assert resultado["metodo"] == "regras_locais_v2"


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
