from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
MERGE_REVISION = "104_merge_entrada_orquestrador"
EXPECTED_PARENTS = {
    "101_entrada_universal_documentos",
    "103_fee_proposal",
}


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


def _head_revision() -> str:
    script = _script_directory()
    heads = script.get_heads()
    if not heads:
        raise AssertionError("Nenhuma head encontrada em backend/alembic/versions")
    if len(heads) != 1:
        raise AssertionError(f"Cadeia bifurcada: {heads}")
    return heads[0]


def test_alembic_possui_um_unico_head_canonico():
    # valida: existe exatamente UMA head canônica (sem bifurcação)
    script = _script_directory()
    heads = script.get_heads()
    assert len(heads) == 1, f"cadeia bifurcada: {heads}"


def test_revisao_de_merge_reconcilia_os_dois_ramos_concorrentes():
    revision = _script_directory().get_revision(MERGE_REVISION)
    assert revision is not None
    assert set(revision.down_revision) == EXPECTED_PARENTS


def _require_revision(name: str):
    script = _script_directory()
    rev = script.get_revision(name)
    if rev is None:
        pytest.skip(f"migration {name} não presente nesta branch")
    return rev


def test_datajud_encadeia_apos_escopo_rag():
    revision = _require_revision("110_datajud_cognitive_feed")
    assert revision.down_revision == "109_rag_scope_cliente"


def test_metricas_provedores_encadeiam_apos_datajud():
    revision = _require_revision("111_ai_provider_metrics")
    assert revision.down_revision == "110_datajud_cognitive_feed"


def test_cutover_pii_encadeia_apos_metricas_provedores():
    revision = _require_revision("112_client_pii_drop_plaintext")
    assert revision.down_revision == "111_ai_provider_metrics"


def test_calendar_feed_encadeia_apos_cutover_pii():
    revision = _require_revision("113_calendar_feed_revocation")
    assert revision.down_revision == "112_client_pii_drop_plaintext"


def test_consolidacao_v4_encadeia_apos_calendar_feed():
    revision = _require_revision("114_consolidar_v4")
    assert revision.down_revision == "113_calendar_feed_revocation"


def test_case_proxima_acao_encadeia_apos_consolidacao_v4():
    revision = _require_revision("115_case_proxima_acao")
    assert revision.down_revision == "114_consolidar_v4"


def test_ai_log_risco_ia_encadeia_apos_case_proxima_acao():
    revision = _require_revision("116_risco_ia")
    assert revision.down_revision == "115_case_proxima_acao"


def test_knowledge_revisao_encadeia_apos_ai_log_risco_ia():
    revision = _require_revision("117_knowledge_revisao")
    assert revision.down_revision == "116_risco_ia"


def test_doc_versionamento_encadeia_apos_knowledge_revisao():
    revision = _require_revision("118_doc_versionamento")
    assert revision.down_revision == "117_knowledge_revisao"


def test_base_rag_enum_encadeia_apos_doc_versionamento():
    revision = _require_revision("119_base_rag_enum")
    assert revision.down_revision == "118_doc_versionamento"


def test_chunk_pagina_encadeia_apos_base_rag_enum():
    revision = _require_revision("120_chunk_pagina")
    assert revision.down_revision == "119_base_rag_enum"
