from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.activity_alert import ActivityAlertState
from app.schemas.activity_alert import ActivityAlertStateUpdate
from app.services.activity_alert_service import (
    _activity_scope_sql,
    _case_scope_sql,
    _document_scope_sql,
    nivel_alerta,
)


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


def test_atividade_de_caso_nao_usa_responsavel_como_bypass_de_ownership():
    advogado = SimpleNamespace(id="u1", role="advogado")
    scope = _activity_scope_sql(advogado)

    assert "v.case_id IS NULL AND v.responsavel_id = :uid" in scope
    assert "cc.advogado_responsavel_id = :uid" in scope
    assert "cc.advogado_auxiliar_id = :uid" in scope
    assert "cc.deleted_at IS NULL" in scope
    assert "v.responsavel_id = :uid OR EXISTS" not in scope


def test_caso_orfao_nao_e_escape_de_rbac_para_usuario_nao_gestor():
    advogado = SimpleNamespace(id="u1", role="advogado")
    scope = _case_scope_sql(advogado)

    assert "c.advogado_responsavel_id = :uid" in scope
    assert "c.advogado_auxiliar_id = :uid" in scope
    assert "IS NULL" not in scope


def test_documento_de_caso_segue_ownership_e_avulso_segue_uploader():
    advogado = SimpleNamespace(id="u1", role="advogado")
    scope = _document_scope_sql(advogado)

    assert "d.case_id IS NULL AND d.uploaded_by = :uid" in scope
    assert "cc.advogado_responsavel_id = :uid" in scope
    assert "cc.advogado_auxiliar_id = :uid" in scope
    assert "cc.deleted_at IS NULL" in scope
    assert "d.uploaded_by = :uid OR EXISTS" not in scope


def test_gestao_nao_recebe_filtro_de_ownership_nos_alertas():
    socio = SimpleNamespace(id="u1", role="socio")

    assert _activity_scope_sql(socio) == ""
    assert _case_scope_sql(socio) == ""
    assert _document_scope_sql(socio) == ""
