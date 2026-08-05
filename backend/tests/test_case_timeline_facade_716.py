from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.services.case_timeline_service import _as_utc, _document_query, _event

ROOT = Path(__file__).parents[1]


def _user(role: str):
    return SimpleNamespace(role=SimpleNamespace(value=role))


def test_evento_tem_contrato_estavel_e_data_utc():
    item = _event(
        entity_id="abc",
        kind="task",
        title="Revisar peça",
        description="Conferir pedidos",
        occurred_at=date(2026, 8, 5),
        status="a_fazer",
        source="tasks",
        metadata={"prioridade": "alta"},
    )
    assert item["id"] == "tasks:abc"
    assert item["occurred_at"] == "2026-08-05T00:00:00+00:00"
    assert item["metadata"] == {"prioridade": "alta"}
    assert item["_sort_at"].tzinfo is not None


def test_data_naive_e_normalizada_para_utc():
    result = _as_utc(datetime(2026, 8, 5, 10, 30))
    assert result.tzinfo == timezone.utc


def test_documento_restrito_e_filtrado_no_sql_antes_do_limit():
    query = _document_query(_user("advogado"), "case-1", 50)
    sql = str(query.compile(compile_kwargs={"literal_binds": True}))
    assert "documents.confidencialidade NOT IN" in sql
    assert "LIMIT 50" in sql
    assert sql.index("documents.confidencialidade NOT IN") < sql.index("LIMIT 50")


def test_socio_preserva_acesso_documental_conforme_politica_interna():
    query = _document_query(_user("socio"), "case-1", 50)
    sql = str(query.compile(compile_kwargs={"literal_binds": True}))
    assert "documents.confidencialidade NOT IN" not in sql


def test_timeline_agrega_dominios_sem_escrita_paralela_ou_nota_privada():
    source = (ROOT / "app/services/case_timeline_service.py").read_text(
        encoding="utf-8"
    )
    for model in (
        "CaseMovimento",
        "Process",
        "Document",
        "Deadline",
        "Task",
        "Atendimento",
        "LegalDoc",
    ):
        assert f"select({model})" in source
    upper = source.upper()
    assert "INSERT INTO" not in upper
    assert "UPDATE " not in upper
    assert "DELETE FROM" not in upper
    assert "observacoes_privadas" not in source


def test_router_exige_ownership_e_reusa_saude_deterministica():
    source = (ROOT / "app/routers/case_timeline.py").read_text(encoding="utf-8")
    assert '@router.get("/timeline")' in source
    assert '@router.get("/operational-health")' in source
    assert source.count("await verificar_acesso_caso(db, cu, case_id)") == 2
    assert "case_health.calcular_score_caso" in source


def test_router_e_anexado_uma_unica_vez_ao_dominio_cases():
    source = (ROOT / "app/routers/__init__.py").read_text(encoding="utf-8")
    assert source.count("cases.router.include_router(case_timeline.router)") == 1
