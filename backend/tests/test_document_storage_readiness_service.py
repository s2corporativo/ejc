from __future__ import annotations

from dataclasses import asdict

from app.services.document_storage_readiness_service import AuditoriaStorageDocumental


def _auditoria(**overrides) -> AuditoriaStorageDocumental:
    dados = {
        "documentos_ativos": 10,
        "ativos_drive": 3,
        "ativos_local": 7,
        "drive_id_duplicado": 0,
        "drive_id_sem_marcador": 0,
        "marcador_drive_sem_id": 0,
        "paths_ativos_duplicados": 0,
    }
    dados.update(overrides)
    return AuditoriaStorageDocumental(**dados)


def test_storage_consistente_quando_anomalias_sao_zero():
    assert _auditoria().metadados_consistentes is True


def test_qualquer_anomalia_bloqueia_readiness():
    for campo in (
        "drive_id_duplicado",
        "drive_id_sem_marcador",
        "marcador_drive_sem_id",
        "paths_ativos_duplicados",
    ):
        assert _auditoria(**{campo: 1}).metadados_consistentes is False


def test_resultado_expoe_somente_contagens():
    payload = asdict(_auditoria())
    assert set(payload) == {
        "documentos_ativos",
        "ativos_drive",
        "ativos_local",
        "drive_id_duplicado",
        "drive_id_sem_marcador",
        "marcador_drive_sem_id",
        "paths_ativos_duplicados",
    }
    assert all(isinstance(valor, int) for valor in payload.values())
