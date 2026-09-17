from app.core.taxonomia import AREAS_CANONICAS
from app.services.ai.core.ejc_skill_catalog import native_skill_coverage
from app.services.legal_brain import (
    build_legal_brain_plan,
    resolve_area_specialization,
    supplemental_area_coverage,
)
from app.services.system_prompts import SYSTEM_PROMPTS


def test_cobertura_suplementar_fecha_exatamente_lacunas_nativas_atuais():
    missing = set(native_skill_coverage()["legal_areas"]["missing"])
    supplemental = set(supplemental_area_coverage()["covered"])

    assert missing
    assert supplemental == missing
    assert missing <= set(AREAS_CANONICAS)


def test_especializacoes_diretas_referenciam_prompt_canonico_sem_copiar_texto():
    for area in (
        "sucessoes",
        "constitucional",
        "saude",
        "medico",
        "agrario",
        "agronegocio",
        "eleitoral",
        "internacional",
        "contratual",
    ):
        ref = resolve_area_specialization(area)
        assert ref is not None
        assert ref.area == area
        assert ref.prompt_key == area
        assert ref.prompt_key in SYSTEM_PROMPTS
        assert ref.inherited_from is None
        assert ref.source == "system_prompts"
        assert ref.requires_human_review is True


def test_societario_e_licitacoes_usam_somente_herancas_canonicas_explicitas():
    societario = resolve_area_specialization("societario")
    licitacoes = resolve_area_specialization("licitacoes")

    assert societario is not None
    assert societario.prompt_key == "empresarial"
    assert societario.inherited_from == "empresarial"
    assert licitacoes is not None
    assert licitacoes.prompt_key == "administrativo"
    assert licitacoes.inherited_from == "administrativo"


def test_area_inexistente_falha_fechado():
    assert resolve_area_specialization("tributario_inventado") is None
    assert resolve_area_specialization("") is None
    assert resolve_area_specialization(None) is None


def test_plano_shadow_reconhece_area_sem_skill_nativa_sem_injetar_runtime():
    plan = build_legal_brain_plan(
        task_type="analise_juridica",
        domain="sucessoes",
        message="Inventário com documentos ainda incompletos.",
    )

    assert plan.area == "sucessoes"
    assert "area_juridica_nao_confirmada" not in plan.warnings
    assert "area_com_especializacao_existente_ainda_sem_skill_nativa" in plan.warnings
    specialization = plan.to_dict()["metadata"]["area_specialization"]
    assert specialization["prompt_key"] == "sucessoes"
    assert specialization["runtime_injected"] is False


def test_area_ja_nativa_nao_recebe_overlay_suplementar():
    plan = build_legal_brain_plan(
        task_type="analise_juridica",
        domain="ambiental",
        message="Auto de infração ambiental e prova técnica.",
    )

    assert plan.area == "ambiental"
    assert plan.to_dict()["metadata"]["area_specialization"] is None
