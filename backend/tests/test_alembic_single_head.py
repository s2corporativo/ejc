from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_DIR = Path(__file__).resolve().parents[1]
# Atualizar este identificador no mesmo PR que adicionar uma nova migration.
HEAD_REVISION = "113_analise_caso_ia"
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
    revision = _script_directory().get_revision("110_datajud_cognitive_feed")
    assert revision.down_revision == "109_rag_scope_cliente"


def test_metricas_provedores_encadeiam_apos_datajud():
    revision = _script_directory().get_revision("111_ai_provider_metrics")
    assert revision.down_revision == "110_datajud_cognitive_feed"


def test_cutover_pii_encadeia_apos_metricas_provedores():
    # 112 (drop do CPF/CNPJ plaintext) encadeia após 111.
    revision = _script_directory().get_revision("112_client_pii_drop_plaintext")
    assert revision.down_revision == "111_ai_provider_metrics"


def test_analise_caso_ia_encadeia_apos_cutover_pii():
    # 113 (módulo Análise de Caso IA) é o novo head e encadeia após 112.
    revision = _script_directory().get_revision(HEAD_REVISION)
    assert revision.down_revision == "112_client_pii_drop_plaintext"
