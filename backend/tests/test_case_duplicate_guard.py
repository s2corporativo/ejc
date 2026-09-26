from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_case_creation_has_concurrent_duplicate_guard():
    router = (ROOT / "app/routers/cases.py").read_text(encoding="utf-8")
    integrity = (ROOT / "app/services/case_integrity_service.py").read_text(
        encoding="utf-8"
    )
    repository = (ROOT / "app/repositories/process_repository.py").read_text(
        encoding="utf-8"
    )

    # O router usa a regra canônica; o lock não precisa morar no router.
    assert "garantir_numero_processo_unico" in router
    # CNJ: lock global compartilhado pelo domínio Processo.
    assert "pg_advisory_xact_lock" in repository
    assert "process_cnj:" in repository
    # Número administrativo: lock por cliente+número no serviço de integridade.
    assert "pg_advisory_xact_lock" in integrity
    assert "case_duplicate:" in integrity
    assert "Já existe caso ativo para este cliente e número processual" in integrity
    assert "Case.client_id == client_id" in integrity
    assert "Case.deleted_at.is_(None)" in integrity
