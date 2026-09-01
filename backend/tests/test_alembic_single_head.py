from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_DIR = Path(__file__).resolve().parents[1]
# Atualizar este identificador no mesmo PR que adicionar uma nova migration.
HEAD_REVISION = "156_prazos_auditaveis_regime"
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
    revision = _script_directory().get_revision("112_client_pii_drop_plaintext")
    assert revision.down_revision == "111_ai_provider_metrics"


def test_calendar_feed_encadeia_apos_cutover_pii():
    revision = _script_directory().get_revision("113_calendar_feed_revocation")
    assert revision.down_revision == "112_client_pii_drop_plaintext"


def test_consolidacao_v4_encadeia_apos_calendar_feed():
    revision = _script_directory().get_revision("114_consolidar_v4")
    assert revision.down_revision == "113_calendar_feed_revocation"


def test_case_proxima_acao_encadeia_apos_consolidacao_v4():
    revision = _script_directory().get_revision("115_case_proxima_acao")
    assert revision.down_revision == "114_consolidar_v4"


def test_ai_log_risco_ia_encadeia_apos_case_proxima_acao():
    revision = _script_directory().get_revision("116_risco_ia")
    assert revision.down_revision == "115_case_proxima_acao"


def test_knowledge_revisao_encadeia_apos_ai_log_risco_ia():
    revision = _script_directory().get_revision("117_knowledge_revisao")
    assert revision.down_revision == "116_risco_ia"


def test_doc_versionamento_encadeia_apos_knowledge_revisao():
    revision = _script_directory().get_revision("118_doc_versionamento")
    assert revision.down_revision == "117_knowledge_revisao"


def test_base_rag_enum_encadeia_apos_doc_versionamento():
    revision = _script_directory().get_revision("119_base_rag_enum")
    assert revision.down_revision == "118_doc_versionamento"


def test_chunk_pagina_encadeia_apos_base_rag_enum():
    revision = _script_directory().get_revision("120_chunk_pagina")
    assert revision.down_revision == "119_base_rag_enum"


def test_sala_juridica_encadeia_apos_chunk_pagina():
    revision = _script_directory().get_revision("121_sala_juridica_chat")
    assert revision.down_revision == "120_chunk_pagina"


def test_route_usage_encadeia_apos_sala_juridica():
    revision = _script_directory().get_revision("122_route_usage_metrics")
    assert revision.down_revision == "121_sala_juridica_chat"


def test_vinculo_legal_doc_ai_log_encadeia_apos_metricas_de_rota():
    revision = _script_directory().get_revision("123_legal_doc_ai_log_vinculo")
    assert revision.down_revision == "122_route_usage_metrics"


def test_hardening_data_room_encadeia_apos_vinculo_legal_doc():
    revision = _script_directory().get_revision("124_dataroom_public_hardening")
    assert revision.down_revision == "123_legal_doc_ai_log_vinculo"


def test_contador_de_execucoes_zeradas_encadeia_apos_hardening_data_room():
    revision = _script_directory().get_revision("125_fonte_execucoes_zeradas")
    assert revision.down_revision == "124_dataroom_public_hardening"


def test_quatro_estados_encadeia_apos_contador_de_execucoes_zeradas():
    revision = _script_directory().get_revision("126_case_status_quatro_estados")
    assert revision.down_revision == "125_fonte_execucoes_zeradas"


def test_publicacao_explicita_encadeia_apos_quatro_estados():
    revision = _script_directory().get_revision("127_publicacao_explicita")
    assert revision.down_revision == "126_case_status_quatro_estados"


def test_ejc_skills_uso_encadeia_apos_publicacao_explicita():
    revision = _script_directory().get_revision("130_ejc_skills_uso")
    assert revision.down_revision == "127_publicacao_explicita"


def test_preliminares_encadeiam_apos_consolidacao_fontes():
    revisao_139 = _script_directory().get_revision("139_dpt360_ciclo_vida_lgpd")
    assert revisao_139.down_revision == "138_consolida_fontes_ingestao"
    revisao_140 = _script_directory().get_revision("140_preliminares_fundacao_schema")
    assert revisao_140.down_revision == "139_dpt360_ciclo_vida_lgpd"
    revisao_141 = _script_directory().get_revision("141_dpt360_diagnostico")
    assert revisao_141.down_revision == "140_preliminares_fundacao_schema"
    revisao_142 = _script_directory().get_revision("142_document_hash_rescan")
    assert revisao_142.down_revision == "141_dpt360_diagnostico"
    revisao_143 = _script_directory().get_revision(
        "143_signature_documento_visualizado"
    )
    assert revisao_143.down_revision == "142_document_hash_rescan"
    revisao_144 = _script_directory().get_revision("144_alembic_version_varchar128")
    assert revisao_144.down_revision == "143_signature_documento_visualizado"
    revisao_145 = _script_directory().get_revision("145_drop_orphan_db_only_columns")
    assert revisao_145.down_revision == "144_alembic_version_varchar128"
    assert _script_directory().get_heads() == [HEAD_REVISION]
