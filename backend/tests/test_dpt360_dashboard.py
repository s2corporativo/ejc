from types import SimpleNamespace

from app.modules.dpt360.dashboard_service import (
    BUSINESS_AREAS,
    _is_critical_case,
    _visible_business_cases_query,
    _visible_company_query,
)
from app.modules.dpt360.schemas import DptCompanySummary, DptDashboardMetrics


def _user(role: str = "advogado"):
    return SimpleNamespace(id="user-1", role=SimpleNamespace(value=role))


def _case(*, status="aberto", prioridade="media", risco=None):
    return SimpleNamespace(status=status, prioridade=prioridade, risco=risco)


def test_areas_empresariais_sao_explicitas_e_sem_coringa():
    assert {
        "empresarial",
        "tributario",
        "ambiental",
        "administrativo",
        "trabalhista",
        "contratual",
        "societario",
        "licitacoes",
        "digital_lgpd",
    }.issubset(BUSINESS_AREAS)
    assert "civil" not in BUSINESS_AREAS
    assert "criminal" not in BUSINESS_AREAS


def test_risco_critico_exige_caso_aberto_e_sinal_objetivo():
    assert _is_critical_case(_case(prioridade="critica")) is True
    assert _is_critical_case(_case(risco="alto")) is True
    assert _is_critical_case(_case(status="encerrado", prioridade="critica")) is False
    assert _is_critical_case(_case(status="aberto", prioridade="media", risco=None)) is False


def test_query_de_advogado_restringe_empresas_e_casos_a_vinculo():
    company_sql = str(_visible_company_query(_user()))
    case_sql = str(_visible_business_cases_query(_user(), ["company-1"]))

    assert "clients.responsavel_id" in company_sql
    assert "cases.advogado_responsavel_id" in company_sql
    assert "cases.advogado_auxiliar_id" in company_sql
    assert "cases.advogado_responsavel_id" in case_sql
    assert "cases.advogado_auxiliar_id" in case_sql
    assert "cases.client_id" in case_sql


def test_gestao_nao_recebe_filtro_de_advogado_individual():
    company_sql = str(_visible_company_query(_user("socio")))
    case_sql = str(_visible_business_cases_query(_user("socio"), ["company-1"]))

    assert "clients.responsavel_id" not in company_sql
    assert "cases.advogado_responsavel_id" not in case_sql
    assert "cases.advogado_auxiliar_id" not in case_sql


def test_payload_empresarial_nao_expoe_pii_de_contato_documental():
    fields = set(DptCompanySummary.model_fields)
    forbidden = {
        "cpf",
        "cnpj",
        "cpf_enc",
        "cnpj_enc",
        "cpf_hash",
        "cnpj_hash",
        "email",
        "telefone",
        "whatsapp",
    }
    assert fields.isdisjoint(forbidden)


def test_metricas_nao_transformam_integracoes_ausentes_em_zero():
    metrics = DptDashboardMetrics()
    assert metrics.empresas_acompanhadas == 0
    assert metrics.mudancas_juridicas_hoje is None
    assert metrics.empresas_potencialmente_impactadas is None
    assert metrics.diagnosticos_pendentes is None
