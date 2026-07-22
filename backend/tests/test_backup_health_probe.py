"""Testes da sonda de saúde do backup de produção."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts" / "backup" / "check_backup_health.py"
SPEC = importlib.util.spec_from_file_location("check_backup_health", PROBE)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
avaliar_saude_backup = module.avaliar_saude_backup


AGORA = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def _config(**overrides):
    data = {
        "enabled": True,
        "chave_configurada": True,
        "pasta_configurada": True,
        "credencial_drive_configurada": True,
        "credencial_dedicada_configurada": True,
        "pg_dump_disponivel": True,
    }
    data.update(overrides)
    return data


def _estado(**overrides):
    data = {
        "last_run_at": AGORA - timedelta(hours=7),
        "last_status": "sucesso",
        "detalhes": [
            {"nome": "ejc_backup_20260722T050000Z_db.dump.enc"},
            {"nome": "ejc_backup_20260722T050000Z_uploads.tar.gz.enc"},
        ],
    }
    data.update(overrides)
    return data


def test_backup_saudavel_exige_banco_uploads_recencia_e_credencial_dedicada():
    result = avaliar_saude_backup(_config(), _estado(), agora=AGORA)
    assert result["ok"] is True
    assert result["age_hours"] == 7.0
    assert result["problemas"] == []


def test_credencial_herdada_nao_atende_segregacao_do_backup():
    result = avaliar_saude_backup(
        _config(credencial_dedicada_configurada=False),
        _estado(),
        agora=AGORA,
    )
    assert result["ok"] is False
    assert any("credencial exclusiva" in item for item in result["problemas"])


def test_backup_parcial_e_upload_ausente_falham():
    result = avaliar_saude_backup(
        _config(),
        _estado(
            last_status="parcial",
            detalhes=[{"nome": "ejc_backup_x_db.dump.enc"}],
        ),
        agora=AGORA,
    )
    assert result["ok"] is False
    assert any("status" in item for item in result["problemas"])
    assert any("uploads" in item for item in result["problemas"])


def test_backup_atrasado_falha_no_limite_configurado():
    result = avaliar_saude_backup(
        _config(),
        _estado(last_run_at=AGORA - timedelta(hours=31)),
        agora=AGORA,
        max_age_hours=30,
    )
    assert result["ok"] is False
    assert any("atrasado" in item for item in result["problemas"])


def test_configuracao_incompleta_e_estado_ausente_falham():
    result = avaliar_saude_backup(
        _config(enabled=False, credencial_drive_configurada=False),
        None,
        agora=AGORA,
    )
    assert result["ok"] is False
    assert "agendamento desabilitado" in result["problemas"]
    assert "credencial de escrita do Drive ausente" in result["problemas"]
    assert "nenhuma execução de backup registrada" in result["problemas"]


def test_detalhes_json_string_sao_interpretados():
    result = avaliar_saude_backup(
        _config(),
        _estado(
            detalhes=(
                '[{"nome":"ejc_backup_x_db.dump.enc"},'
                '{"nome":"ejc_backup_x_uploads.tar.gz.enc"}]'
            )
        ),
        agora=AGORA,
    )
    assert result["ok"] is True


def test_data_futura_e_limite_invalido_falham_com_default_seguro():
    result = avaliar_saude_backup(
        _config(),
        _estado(last_run_at=AGORA + timedelta(hours=2)),
        agora=AGORA,
        max_age_hours=float("nan"),
    )
    assert result["ok"] is False
    assert result["max_age_hours"] == 30.0
    assert any("futuro" in item for item in result["problemas"])
