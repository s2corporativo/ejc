"""Regressões críticas da Auditoria EJC Parte 12."""
from sqlalchemy.sql.elements import BinaryExpression

from app.core.status_caso import (
    STATUS_ABERTOS,
    contar_ativos,
    validar_area_caso,
    validar_status_caso,
)
from app.models.case import Case, CaseArea, CaseStatus


def test_status_all_todos_e_asterisco_sao_filtros_neutros():
    for valor in ("all", "ALL", " todos ", "*"):
        expr = Case.status == validar_status_caso(valor)
        assert isinstance(expr, BinaryExpression)
        assert "cases.status = cases.status" in str(expr)


def test_area_all_todos_e_asterisco_sao_filtros_neutros():
    for valor in ("all", "ALL", " todos ", "*"):
        expr = Case.area == validar_area_caso(valor)
        assert isinstance(expr, BinaryExpression)
        assert "cases.area = cases.area" in str(expr)


def test_status_reais_continuam_tipados():
    assert validar_status_caso("triagem") is CaseStatus.triagem
    assert validar_status_caso(" ATIVO ") is CaseStatus.ativo
    assert validar_area_caso(" CIVIL ") is CaseArea.civil


def test_agregado_ativos_exclui_encerrado_e_arquivado():
    mapa = {
        "triagem": 8,
        "ativo": 2,
        "suspenso": 1,
        "acordo": 1,
        "encerrado": 5,
        "arquivado": 7,
    }
    assert contar_ativos(mapa) == 12
    assert {s.value for s in STATUS_ABERTOS} == {
        "triagem", "ativo", "suspenso", "acordo"
    }
