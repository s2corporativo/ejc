from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_DIR = Path(__file__).resolve().parents[1]
HEAD_REVISION = "111_consolidar_v4"
DATAJUD_REVISION = "110_datajud_cognitive_feed"
MERGE_REVISION = "104_merge_entrada_orquestrador"
EXPECTED_PARENTS = {
    "101_entrada_universal_documentos",
    "103_fee_proposal",
}


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


def test_alembic_possui_um_unico_head_canonico():
    script = _script_directory()
    assert script.get_heads() == [HEAD_REVISION]


def test_revisao_de_merge_reconcilia_os_dois_ramos_concorrentes():
    revision = _script_directory().get_revision(MERGE_REVISION)
    assert revision is not None
    assert set(revision.down_revision) == EXPECTED_PARENTS


def test_datajud_encadeia_apos_escopo_rag():
    revision = _script_directory().get_revision(DATAJUD_REVISION)
    assert revision.down_revision == "109_rag_scope_cliente"


def test_consolidacao_versionados_encadeia_apos_datajud():
    revision = _script_directory().get_revision(HEAD_REVISION)
    assert revision.down_revision == DATAJUD_REVISION
