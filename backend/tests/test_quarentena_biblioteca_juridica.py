import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).parents[1] / "scripts" / "quarentenar_biblioteca_juridica_piloto.py"
_SPEC = importlib.util.spec_from_file_location("quarentenar_biblioteca", _SCRIPT)
assert _SPEC and _SPEC.loader
MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MOD)


def test_quarentena_rebaixa_aprovado_para_pendente():
    novo, mudou = MOD.aplicar_quarentena_extra(
        {"rag_status": "aprovado", "human_reviewed": True},
        quando="2026-08-14T20:00:00-03:00",
    )
    assert mudou is True
    assert novo["rag_status"] == "pendente"
    assert novo["requires_human_review"] is True
    assert novo["human_reviewed"] is False
    assert novo["quarantine_active"] is True


def test_quarentena_preserva_recusa_humana_e_hitl():
    novo, _ = MOD.aplicar_quarentena_extra(
        {"rag_status": "recusado", "human_reviewed": True},
        quando="2026-08-14T20:00:00-03:00",
    )
    assert novo["rag_status"] == "recusado"
    assert novo["human_reviewed"] is True
    assert novo["quarantine_active"] is True


def test_transformacao_e_idempotente_mesmo_com_novo_horario():
    primeiro, _ = MOD.aplicar_quarentena_extra({}, quando="2026-08-14T20:00:00-03:00")
    segundo, mudou = MOD.aplicar_quarentena_extra(primeiro, quando="2026-08-15T09:00:00-03:00")
    assert segundo == primeiro
    assert mudou is False
    assert segundo["quarantined_at"] == "2026-08-14T20:00:00-03:00"


def test_lote_tem_24_ids_unicos():
    assert len(MOD.CANONICAL_IDS) == 24
    assert len(set(MOD.CANONICAL_IDS)) == 24
