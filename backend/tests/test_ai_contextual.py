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
    assert resultado["metodo"] == "regras_locais_v1"


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
