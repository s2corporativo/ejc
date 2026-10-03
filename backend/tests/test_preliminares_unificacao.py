"""Contratos da base única: isolamento de origem, aliases e normalização."""

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import selectinload

from app.core.database import Base
from app.models.legal_chat import (
    LegalChatAttachment,
    LegalChatMessage,
    LegalChatSession,
    LegalChatStateVersion,
)
from app.models.preliminar import (
    Preliminar,
    PreliminarDocumento,
    PreliminarEstado,
    PreliminarMensagem,
)
from app.models.raio_x import RaioXAnalise, RaioXDocumento


def test_seis_modelos_antigos_usam_quatro_tabelas_canonicas():
    assert RaioXAnalise.__table__ is LegalChatSession.__table__ is Preliminar.__table__
    assert RaioXDocumento is LegalChatAttachment is PreliminarDocumento
    assert LegalChatMessage is PreliminarMensagem
    assert LegalChatStateVersion is PreliminarEstado
    assert (
        not {
            "raio_x_analises",
            "raio_x_documentos",
            "legal_chat_sessions",
            "legal_chat_attachments",
            "legal_chat_messages",
            "legal_chat_state_versions",
        }
        & Base.metadata.tables.keys()
    )


def test_select_e_count_nao_misturam_origens():
    for model, origem in [(RaioXAnalise, "raio_x"), (LegalChatSession, "sala_juridica")]:
        for stmt in [select(model), select(model.id), select(func.count(model.id))]:
            sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
            assert "preliminares.origem IN" in sql
            assert repr(origem) in sql


def test_defaults_e_aliases_preservam_contratos_antigos():
    raio = RaioXAnalise(id="raio", titulo="Fictício", created_by="user")
    sala = LegalChatSession(
        id="sala", titulo="Fictício", created_by="user", cliente_potencial="Pessoa fictícia", area_sugerida="civil"
    )
    assert (raio.origem, raio.status) == ("raio_x", "novo")
    assert (sala.origem, sala.status) == ("sala_juridica", "em_analise")
    assert sala.potencial_cliente == sala.cliente_potencial == "Pessoa fictícia"
    assert sala.area == sala.area_sugerida == "civil"
    assert RaioXDocumento(analise_id="raio").preliminar_id == "raio"
    assert LegalChatAttachment(session_id="sala").preliminar_id == "sala"
    assert LegalChatMessage(session_id="sala").preliminar_id == "sala"
    assert LegalChatStateVersion(session_id="sala", origem="ia").autoria == "ia"


def test_aliases_relacionamentos_aceitam_eager_loading():
    for model, attr in [(RaioXAnalise, RaioXAnalise.documentos), (LegalChatSession, LegalChatSession.anexos)]:
        select(model).options(selectinload(attr)).compile()


def test_normalizacao_da_sala_nao_altera_area_do_raio_x():
    sala = LegalChatSession(area_sugerida="area_invalida")
    raio = RaioXAnalise(area="texto_legado_raio_x")
    assert sala.area_sugerida is None
    assert raio.area == "texto_legado_raio_x"
