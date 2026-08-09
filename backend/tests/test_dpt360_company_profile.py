from app.modules.dpt360.company_service import HEALTH_LABELS
from app.modules.dpt360.schemas import DptCompanyProfile, DptHealthArea, DptTwinDimension


def test_saude_juridica_nasce_nao_avaliada_sem_diagnostico_aprovado():
    item = DptHealthArea(area="Ambiental")
    assert item.classificacao == "Não avaliado"
    assert item.evidencias == 0
    assert "Sem diagnóstico" in item.justificativa


def test_legal_twin_diferencia_sem_dados_de_regularidade():
    item = DptTwinDimension(
        key="lgpd",
        label="Operações LGPD",
        status="sem_dados",
        registros=0,
        note="Nenhum registro localizado; isso não prova regularidade.",
    )
    assert item.status == "sem_dados"
    assert "regularidade" in (item.note or "")


def test_perfil_nao_carrega_pii_documental_ou_de_contato():
    fields = set(DptCompanyProfile.model_fields)
    assert fields.isdisjoint({"cpf", "cnpj", "email", "telefone", "whatsapp", "ocr_text"})


def test_areas_de_saude_cobrem_os_eixos_dpt():
    assert HEALTH_LABELS == [
        "Tributário",
        "Ambiental",
        "Administrativo",
        "Trabalhista",
        "Contratual",
        "LGPD",
        "Governança de IA",
    ]
