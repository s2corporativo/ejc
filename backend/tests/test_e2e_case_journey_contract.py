from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOURNEY = ROOT / "qa" / "e2e" / "run_case_journey.py"


def test_cleanup_da_jornada_isola_excecoes_e_segue_ate_relatorio():
    src = JOURNEY.read_text(encoding="utf-8")
    assert "def _cleanup_seguro(" in src
    assert "except Exception as exc:" in src
    finally_block = src[src.index("        finally:") :]
    for nome in ("financeiro", "tarefa", "prazo", "peca", "core"):
        assert f'state, "{nome}"' in finally_block
    assert "core._write_report(state, matrix)" in finally_block


def test_jornada_confirma_e_rele_metadados_do_process():
    src = JOURNEY.read_text(encoding="utf-8")
    assert '"processo_confirmado": {' in src
    assert '"numero_cnj": caso["numero_processo"]' in src
    assert 'path=f"/api/cases/{state.case_id}/processes"' in src
    assert '"jornada.entrada.metadados_processuais_confirmados"' in src


def test_jornada_normaliza_cnj_e_declara_lote_convertido_residual():
    src = JOURNEY.read_text(encoding="utf-8")
    assert 'cnj_esperado = "".join(' in src
    assert '"entrada_unica.audit_trail"' in src
    assert '"document_intake_batches/{rascunho_id}"' in src
    assert "não há endpoint de cleanup seguro" in src
