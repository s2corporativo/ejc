from __future__ import annotations

from dataclasses import asdict

from app.services.document_version_audit_service import AuditoriaVersionamentoDocumental


def _auditoria(**overrides) -> AuditoriaVersionamentoDocumental:
    dados = {
        "total_documentos": 10,
        "documentos_sem_grupo": 0,
        "grupos_sem_raiz_canonica": 0,
        "raizes_canonicas_invalidas": 0,
        "numeracoes_duplicadas": 0,
        "grupos_contexto_inconsistente": 0,
        "grupos_multiplas_raizes": 0,
        "predecessores_ausentes": 0,
        "predecessores_fora_grupo": 0,
        "predecessores_contexto_divergente": 0,
        "cadeias_ciclicas": 0,
        "versoes_invalidas": 0,
    }
    dados.update(overrides)
    return AuditoriaVersionamentoDocumental(**dados)


def test_apto_para_constraint_quando_todas_as_anomalias_sao_zero():
    assert _auditoria().apto_para_constraint is True


def test_qualquer_anomalia_bloqueia_constraint():
    campos = [
        "documentos_sem_grupo",
        "grupos_sem_raiz_canonica",
        "raizes_canonicas_invalidas",
        "numeracoes_duplicadas",
        "grupos_contexto_inconsistente",
        "grupos_multiplas_raizes",
        "predecessores_ausentes",
        "predecessores_fora_grupo",
        "predecessores_contexto_divergente",
        "cadeias_ciclicas",
        "versoes_invalidas",
    ]
    for campo in campos:
        assert _auditoria(**{campo: 1}).apto_para_constraint is False


def test_resultado_expoe_somente_contagens_agregadas():
    payload = asdict(_auditoria())
    assert set(payload) == {
        "total_documentos",
        "documentos_sem_grupo",
        "grupos_sem_raiz_canonica",
        "raizes_canonicas_invalidas",
        "numeracoes_duplicadas",
        "grupos_contexto_inconsistente",
        "grupos_multiplas_raizes",
        "predecessores_ausentes",
        "predecessores_fora_grupo",
        "predecessores_contexto_divergente",
        "cadeias_ciclicas",
        "versoes_invalidas",
    }
    assert all(isinstance(valor, int) for valor in payload.values())
