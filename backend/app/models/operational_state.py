"""Modelos dos estados operacionais antes criados por DDL em runtime.

As tabelas são caches/estado de integração; os serviços continuam usando SQL
parametrizado para preservar seus contratos, enquanto os modelos permitem que
Alembic e o guard de schema conheçam o desenho oficial.
"""
from sqlalchemy import Boolean, Column, Date, DateTime, Integer, Numeric, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class IndicesBcbCache(Base):
    __tablename__ = "indices_bcb_cache"
    codigo = Column(Integer, primary_key=True)
    data = Column(Date, primary_key=True)
    valor = Column(Numeric(20, 10), nullable=False)
    atualizado_em = Column(DateTime(timezone=True), nullable=False)


class IndicesBcbCacheMeta(Base):
    __tablename__ = "indices_bcb_cache_meta"
    codigo = Column(Integer, primary_key=True)
    data_inicial = Column(Date, nullable=False)
    data_final = Column(Date, nullable=False)
    consultado_em = Column(DateTime(timezone=True), nullable=False)


class GoogleDriveSyncState(Base):
    __tablename__ = "google_drive_sync_state"
    folder_id = Column(Text, primary_key=True)
    last_start_page_token = Column(Text)
    last_sync_at = Column(DateTime(timezone=True))
    last_status = Column(Text)
    last_error = Column(Text)
    total_files_seen = Column(Integer, nullable=False, default=0)
    total_files_ingested = Column(Integer, nullable=False, default=0)
    total_files_skipped = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class InfosimplesUso(Base):
    __tablename__ = "infosimples_uso"
    id = Column(String(36), primary_key=True)
    dia = Column(Date, nullable=False)
    caminho = Column(Text, nullable=False)
    parametros_hash = Column(String(64), nullable=False)
    code = Column(Integer)
    resultado = Column(JSONB)
    user_id = Column(String(36))
    created_at = Column(DateTime(timezone=True), nullable=False)


class RadarLegislativoVisto(Base):
    __tablename__ = "radar_legislativo_visto"
    fonte = Column(String(20), primary_key=True)
    id_externo = Column(String(80), primary_key=True)
    tipo = Column(String(30))
    numero = Column(Integer)
    ano = Column(Integer)
    ementa = Column(Text)
    url = Column(Text)
    data_apresentacao = Column(String(30))
    ultima_tramitacao = Column(Text)
    termo = Column(String(200))
    criado_em = Column(DateTime(timezone=True))


class TransparenciaCache(Base):
    __tablename__ = "transparencia_cache"
    id = Column(String(36), primary_key=True)
    dia = Column(Date, nullable=False)
    base = Column(String(80), nullable=False)
    cnpj = Column(String(32), nullable=False)
    resultado = Column(JSONB)
    created_at = Column(DateTime(timezone=True), nullable=False)


class BackupDriveState(Base):
    __tablename__ = "backup_drive_state"
    id = Column(SmallInteger, primary_key=True, default=1)
    last_run_at = Column(DateTime(timezone=True))
    last_status = Column(Text)
    last_error = Column(Text)
    last_origem = Column(Text)
    duracao_segundos = Column(Numeric)
    detalhes = Column(JSONB)
    offsite_ok = Column(Boolean)
    updated_at = Column(DateTime(timezone=True), nullable=False)
