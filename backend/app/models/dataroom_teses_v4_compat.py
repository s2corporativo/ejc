# ── app/models/dataroom_teses_v4_compat.py ─────────────────────────────────────
# Compatibilidade de schema pós-consolidação (PR #1115, 13/08/2026): os routers
# `data_room_v4.py` e `teses_v4.py` foram arquivados em `app/routers/_dead_code/`
# (varredura de chamadas de API comprovou zero consumidores em produção —
# ver docs/consolidacao/MAPA_VERDADE_V1.md), mas as classes ORM `DataRoomSala`
# e `TeseJuridica` precisam permanecer registradas em `Base.metadata` para que
# o autogenerate do Alembic não as trate como pendentes de drop (e para que o
# gate test_schema_sync.py continue reconhecendo as tabelas
# `dataroom_salas` e `teses_juridicas_v4`, originalmente criadas nas
# migrations 067 e 114). Os routers CANÔNICOS que atendem essas áreas são
# `data_room.py` (/api/data-rooms) e `teses.py` (/api/teses) — este módulo
# existe SOMENTE para preservar o registro ORM, não para ser reimportado em
# novos routers.
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, String, Text

from app.core.database import Base


class DataRoomSala(Base):
    """Sala do Data Room v4 — tabela preservada em migration; acesso via SQL
    cru no router canônico `data_room.py`. Não recriar coluna aqui sem revisar
    a migration 067."""

    __tablename__ = "dataroom_salas"

    id = Column(String(36), primary_key=True)
    nome = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=True)
    client_id = Column(String(36), nullable=True)
    expira_em = Column(DateTime(timezone=True), nullable=True)
    publica = Column(Boolean, default=False)


class TeseJuridica(Base):
    """Banco de Teses v4 — compatibilidade temporária do antigo banco. Toda
    nova leitura/escrita usa a tabela canônica `teses`; `teses_juridicas_v4`
    permanece apenas como origem do backfill da migration 114, sem receber
    novas gravações."""

    __tablename__ = "teses_juridicas_v4"

    id = Column(String(36), primary_key=True)
    titulo = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=False)
    fundamentacao = Column(Text, nullable=False)
    jurisprudencia = Column(Text, nullable=True)
    taxa_sucesso = Column(Float, default=0.0)
    area_juridica = Column(String(50), nullable=False)
    tribunal = Column(String(100), nullable=True)
    magistrado = Column(String(100), nullable=True)
    vencedora = Column(Boolean, default=False)
