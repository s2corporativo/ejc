from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.activity_alert import ActivityAlertState
from app.schemas.activity_alert import ActivityAlertStateUpdate
from app.services.activity_alert_service import nivel_alerta


def test_nivel_prazo_vencido_e_janela_urgente():
    assert nivel_alerta("prazo", -1) == "critico"
    assert nivel_alerta("prazo", 0) == "alto"
    assert nivel_alerta("prazo", 1) == "alto"
    assert nivel_alerta("prazo", 3) == "atencao"
    assert nivel_alerta("prazo", 4) == "normal"


def test_nivel_tarefa_so_alerta_vencida_hoje_ou_prioridade_alta():
    assert nivel_alerta("tarefa", -2) == "critico"
    assert nivel_alerta("tarefa", 0) == "alto"
    assert nivel_alerta("tarefa", 5, prioridade="alta") == "atencao"
    assert nivel_alerta("tarefa", 5, prioridade="media") == "normal"


def test_intimacao_e_movimentacao_tem_classificacao_deterministica():
    assert nivel_alerta("intimacao", None) == "alto"
    assert nivel_alerta("movimentacao", None, subtipo="decisao") == "alto"
    assert nivel_alerta("movimentacao", None, subtipo="peticao") == "info"


def test_estado_alerta_aceita_somente_visualizado_ou_tratado():
    assert ActivityAlertStateUpdate(estado="visualizado").estado == "visualizado"
    assert ActivityAlertStateUpdate(estado="tratado").estado == "tratado"
    with pytest.raises(ValidationError):
        ActivityAlertStateUpdate(estado="novo")


def test_modelo_nao_duplica_estado_por_usuario_e_fonte():
    nomes = {constraint.name for constraint in ActivityAlertState.__table__.constraints}
    assert "uq_activity_alert_user_source" in nomes


def test_migration_160_e_aditiva_e_tem_downgrade():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "160_activity_alert_states.py"
    src = path.read_text(encoding="utf-8")
    assert 'down_revision = "159_user_cpf_secure"' in src
    assert 'op.create_table(\n        "activity_alert_states"' in src
    assert 'op.drop_table("activity_alert_states")' in src
    assert "DROP TABLE" not in src.upper().replace('OP.DROP_TABLE("ACTIVITY_ALERT_STATES")', "")


def test_fingerprint_reabre_alerta_quando_origem_muda():
    from app.services.activity_alert_service import _estado, _fingerprint

    row = {
        "id": "p1",
        "titulo": "Prazo contestação",
        "descricao": "X",
        "data": "2026-09-14",
        "status": "pendente",
        "prioridade": "alta",
        "case_id": "c1",
    }
    fp = _fingerprint("prazo", row)
    reconhecido = {**row, "estado_alerta": "tratado", "source_fingerprint": fp}
    assert _estado(reconhecido, fp) == "tratado"

    alterado = {**row, "data": "2026-09-15"}
    novo_fp = _fingerprint("prazo", alterado)
    assert novo_fp != fp
    assert _estado(reconhecido, novo_fp) == "novo"
