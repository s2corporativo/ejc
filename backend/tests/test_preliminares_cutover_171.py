"""Backfill, escrita compatível e rollback com dados exclusivamente fictícios."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

PATH = Path(__file__).resolve().parents[1] / "alembic/versions/171_preliminares_cutover.py"
LEGADAS = [
    "raio_x_analises",
    "legal_chat_sessions",
    "raio_x_documentos",
    "legal_chat_attachments",
    "legal_chat_messages",
    "legal_chat_state_versions",
]
CANONICAS = ["preliminares", "preliminar_documentos", "preliminar_mensagens", "preliminar_estados"]


def test_migration_cutover_existe_e_parte_do_head_real():
    assert PATH.exists()
    m = carregar()
    assert m.revision == "171_preliminares_cutover"
    assert m.down_revision == "170_djen_remove_unicidade_global"


def carregar():
    spec = importlib.util.spec_from_file_location("cutover_171", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def banco():
    if not os.getenv("RUN_DB_TESTS"):
        pytest.skip("requer PostgreSQL local migrado")
    engine = create_engine(os.environ["DATABASE_URL_SYNC"])
    with engine.connect() as conn:
        txn = conn.begin()
        # Todo o schema fictício e seus dados somem por rollback; sem DROP.
        schema = "test_preliminares_" + uuid4().hex
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        tables = set(inspect(conn).get_table_names(schema="public"))
        for table in LEGADAS + CANONICAS:
            source = table if table in tables else table + "_legado_171"
            conn.execute(text(f'CREATE TABLE "{schema}".{table} (LIKE public.{source} INCLUDING ALL)'))
        conn.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
        for child, column, parent in [
            ("raio_x_documentos", "analise_id", "raio_x_analises"),
            ("legal_chat_attachments", "session_id", "legal_chat_sessions"),
            ("legal_chat_messages", "session_id", "legal_chat_sessions"),
            ("legal_chat_state_versions", "session_id", "legal_chat_sessions"),
            *[(table, "preliminar_id", "preliminares") for table in CANONICAS[1:]],
        ]:
            conn.execute(
                text(f"ALTER TABLE {child} ADD FOREIGN KEY ({column}) REFERENCES {parent}(id) ON DELETE CASCADE")
            )
        yield conn
        txn.rollback()
    engine.dispose()


def migrar(conn, direction="upgrade"):
    with Operations.context(MigrationContext.configure(conn)):
        getattr(carregar(), direction)()


def legado(conn):
    conn.execute(
        text("INSERT INTO raio_x_analises (id,titulo,created_by,area) VALUES ('r1','Raio fictício','u1','civil')")
    )
    conn.execute(
        text(
            "INSERT INTO legal_chat_sessions (id,titulo,created_by,cliente_potencial,area_sugerida) VALUES ('s1','Sala fictícia','u2','Pessoa fictícia','civil')"
        )
    )
    conn.execute(
        text(
            "INSERT INTO raio_x_documentos (id,analise_id,nome_original,filepath,size_bytes,sha256,uploaded_by,paginas) VALUES ('d1','r1','ficticio.pdf','/tmp/ficticio.pdf',10,'hash-r','u1',2)"
        )
    )
    conn.execute(
        text(
            "INSERT INTO legal_chat_attachments (id,session_id,nome_original,filepath,size_bytes,sha256,uploaded_by) VALUES ('d2','s1','ficticio.txt','/tmp/ficticio.txt',20,'hash-s','u2')"
        )
    )
    conn.execute(
        text(
            "INSERT INTO legal_chat_messages (id,session_id,autor,conteudo) VALUES ('m1','s1','user','Mensagem fictícia')"
        )
    )
    conn.execute(
        text(
            "INSERT INTO legal_chat_state_versions (id,session_id,versao,origem,estado) VALUES ('e1','s1',1,'ia','{\"fatos\":[]}'::jsonb)"
        )
    )


def test_backfill_views_e_rollback_preservam_todos_os_campos(banco):
    legado(banco)
    before = {
        t: banco.execute(text(f"SELECT row_to_json(t)::jsonb FROM {t} t ORDER BY id")).scalars().all() for t in LEGADAS
    }
    migrar(banco)
    assert set(LEGADAS) <= set(inspect(banco).get_view_names())
    assert banco.execute(text("SELECT count(*) FROM preliminares")).scalar() == 2
    for table, rows in before.items():
        after = (
            banco.execute(text(f"SELECT row_to_json(t)::jsonb - 'origem' FROM {table} t ORDER BY id")).scalars().all()
            if table in LEGADAS[:2]
            else banco.execute(text(f"SELECT row_to_json(t)::jsonb FROM {table} t ORDER BY id")).scalars().all()
        )
        assert after == rows
    migrar(banco, "downgrade")
    for table, rows in before.items():
        assert banco.execute(text(f"SELECT row_to_json(t)::jsonb FROM {table} t ORDER BY id")).scalars().all() == rows
    migrar(banco)
    assert banco.execute(text("SELECT count(*) FROM preliminares")).scalar() == 2


def test_duas_origens_orm_e_views_escrevem_no_mesmo_registro(banco):
    from app.models.legal_chat import LegalChatSession
    from app.models.raio_x import RaioXAnalise

    migrar(banco)
    session = Session(bind=banco, join_transaction_mode="create_savepoint")
    session.add_all(
        [
            RaioXAnalise(id="r1", titulo="Raio fictício", created_by="u1"),
            LegalChatSession(id="s1", titulo="Sala fictícia", created_by="u2"),
        ]
    )
    session.flush()
    assert session.get(RaioXAnalise, "s1") is None
    assert session.get(LegalChatSession, "r1") is None
    assert session.scalars(select(RaioXAnalise)).all()[0].id == "r1"
    assert session.scalars(select(LegalChatSession)).all()[0].id == "s1"
    session.commit()
    session.close()
    banco.execute(text("INSERT INTO legal_chat_sessions (id,titulo,created_by) VALUES ('s2','Sala via view','u2')"))
    banco.execute(text("UPDATE raio_x_analises SET titulo='Raio atualizado' WHERE id='r1'"))
    banco.execute(text("DELETE FROM legal_chat_sessions WHERE id='s1'"))
    migrar(banco, "downgrade")
    assert banco.execute(text("SELECT titulo FROM raio_x_analises WHERE id='r1'")).scalar() == "Raio atualizado"
    assert banco.execute(text("SELECT id FROM legal_chat_sessions ORDER BY id")).scalars().all() == ["s2"]


def test_documentos_mensagens_estados_e_cascata_espelham_rollback(banco):
    legado(banco)
    migrar(banco)
    banco.execute(
        text(
            "INSERT INTO legal_chat_attachments (id,session_id,nome_original,filepath,size_bytes,sha256,uploaded_by) VALUES ('d3','s1','nova.txt','/tmp/nova.txt',1,'nova','u2')"
        )
    )
    banco.execute(text("UPDATE legal_chat_messages SET conteudo='Revisão fictícia' WHERE id='m1'"))
    banco.execute(text("UPDATE legal_chat_state_versions SET origem='advogado' WHERE id='e1'"))
    banco.execute(text("DELETE FROM raio_x_analises WHERE id='r1'"))
    migrar(banco, "downgrade")
    assert banco.execute(text("SELECT count(*) FROM raio_x_documentos")).scalar() == 0
    assert banco.execute(text("SELECT count(*) FROM legal_chat_attachments")).scalar() == 2
    assert banco.execute(text("SELECT conteudo FROM legal_chat_messages WHERE id='m1'")).scalar() == "Revisão fictícia"
    assert banco.execute(text("SELECT origem FROM legal_chat_state_versions WHERE id='e1'")).scalar() == "advogado"


def test_colisao_de_ids_aborta_sem_alterar_legado(banco):
    legado(banco)
    banco.execute(text("INSERT INTO legal_chat_sessions (id,titulo,created_by) VALUES ('r1','Colisão fictícia','u2')"))
    with banco.begin_nested() as savepoint:
        with pytest.raises(DBAPIError):
            migrar(banco)
        savepoint.rollback()
    assert not set(LEGADAS) & set(inspect(banco).get_view_names())
    assert banco.execute(text("SELECT count(*) FROM preliminares")).scalar() == 0
    assert banco.execute(text("SELECT count(*) FROM legal_chat_sessions")).scalar() == 2


def test_view_de_documento_rejeita_origem_errada(banco):
    legado(banco)
    migrar(banco)
    with banco.begin_nested() as savepoint:
        with pytest.raises(DBAPIError):
            banco.execute(
                text(
                    "INSERT INTO raio_x_documentos (id,analise_id,nome_original,filepath,size_bytes,sha256,uploaded_by) VALUES ('invalido','s1','teste.txt','/tmp/teste.txt',1,'x','u1')"
                )
            )
        savepoint.rollback()
    assert banco.execute(text("SELECT count(*) FROM preliminar_documentos WHERE id='invalido'")).scalar() == 0


def test_acl_de_leitura_da_interface_legada_e_preservado(banco):
    legado(banco)
    role = "test_preliminar_role_" + uuid4().hex
    schema = banco.execute(text("SELECT current_schema()")).scalar()
    banco.execute(text(f'CREATE ROLE "{role}"'))
    banco.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"'))
    banco.execute(text(f'GRANT SELECT ON legal_chat_sessions TO "{role}"'))
    migrar(banco)
    banco.execute(text(f'SET LOCAL ROLE "{role}"'))
    assert banco.execute(text("SELECT id FROM legal_chat_sessions")).scalars().all() == ["s1"]
    with banco.begin_nested() as savepoint:
        with pytest.raises(DBAPIError):
            banco.execute(text("UPDATE legal_chat_sessions SET titulo='Não autorizado' WHERE id='s1'"))
        savepoint.rollback()
    banco.execute(text("RESET ROLE"))


def test_owner_mantem_select_quando_acl_antiga_e_nula(banco):
    role = "test_preliminar_owner_" + uuid4().hex
    extra = "test_preliminar_extra_" + uuid4().hex
    schema = banco.execute(text("SELECT current_schema()")).scalar()
    banco.execute(text(f'CREATE ROLE "{role}"'))
    banco.execute(text(f'CREATE ROLE "{extra}"'))
    for table in LEGADAS:
        banco.execute(text(f'ALTER TABLE {table} OWNER TO "{role}"'))
    banco.execute(text(f'GRANT ALL ON {", ".join(CANONICAS)} TO "{role}"'))
    banco.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" GRANT SELECT ON TABLES TO "{extra}"'))
    migrar(banco)
    assert banco.execute(
        text("SELECT has_table_privilege(:role, 'legal_chat_sessions', 'SELECT')"), {"role": role}
    ).scalar()
    assert not banco.execute(
        text("SELECT has_table_privilege(:role, 'legal_chat_sessions', 'SELECT')"), {"role": extra}
    ).scalar()


def test_escritor_raio_x_nao_precisa_acessar_espelho_da_sala(banco):
    role = "test_preliminar_writer_" + uuid4().hex
    schema = banco.execute(text("SELECT current_schema()")).scalar()
    banco.execute(text(f'CREATE ROLE "{role}"'))
    banco.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"'))
    banco.execute(
        text(f'GRANT ALL ON raio_x_analises, raio_x_documentos, preliminares, preliminar_documentos TO "{role}"')
    )
    migrar(banco)
    banco.execute(text(f'SET LOCAL ROLE "{role}"'))
    banco.execute(text("INSERT INTO raio_x_analises (id,titulo,created_by) VALUES ('r2','Raio fictício','u1')"))
    banco.execute(
        text(
            "INSERT INTO raio_x_documentos (id,analise_id,nome_original,filepath,size_bytes,sha256,uploaded_by) VALUES ('d2','r2','teste.txt','/tmp/teste.txt',1,'hash','u1')"
        )
    )
    assert banco.execute(text("SELECT id FROM raio_x_documentos")).scalars().all() == ["d2"]
    with banco.begin_nested() as savepoint:
        with pytest.raises(DBAPIError):
            banco.execute(text("SELECT * FROM legal_chat_sessions_legado_171"))
        savepoint.rollback()
    banco.execute(text("RESET ROLE"))
    migrar(banco, "downgrade")
    assert banco.execute(text("SELECT id FROM raio_x_documentos")).scalars().all() == ["d2"]


def test_id_primario_e_imutavel_para_nao_duplicar_rollback(banco):
    migrar(banco)
    banco.execute(text("INSERT INTO raio_x_analises (id,titulo,created_by) VALUES ('r2','Raio fictício','u1')"))
    with banco.begin_nested() as savepoint:
        with pytest.raises(DBAPIError):
            banco.execute(text("UPDATE preliminares SET id='r3' WHERE id='r2'"))
        savepoint.rollback()
    migrar(banco, "downgrade")
    assert banco.execute(text("SELECT id FROM raio_x_analises")).scalars().all() == ["r2"]


def test_rls_existente_aborta_antes_do_cutover(banco):
    banco.execute(text("ALTER TABLE raio_x_analises ENABLE ROW LEVEL SECURITY"))
    with pytest.raises(RuntimeError, match="RLS existente"):
        migrar(banco)
    assert not set(LEGADAS) & set(inspect(banco).get_view_names())


def test_funcoes_de_espelho_nao_sao_api_de_usuario(banco):
    role = "test_preliminar_no_function_" + uuid4().hex
    schema = banco.execute(text("SELECT current_schema()")).scalar()
    banco.execute(text(f'CREATE ROLE "{role}"'))
    banco.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"'))
    migrar(banco)
    for table in CANONICAS:
        function = f'"{schema}".espelhar_171_{table}()'
        row = banco.execute(
            text("SELECT prosecdef, proconfig FROM pg_proc WHERE oid=to_regprocedure(:fn)"), {"fn": function}
        ).one()
        assert row.prosecdef
        assert row.proconfig == ["search_path=pg_catalog"]
        assert not banco.execute(
            text("SELECT has_function_privilege(:role,:fn,'EXECUTE')"), {"role": role, "fn": function}
        ).scalar()
