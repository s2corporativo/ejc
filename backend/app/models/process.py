# ── app/models/process.py ─────────────────────────────────────────────────────
# Entidade Processo, independente do Caso (1 Caso : N Processos).
#
# A tabela `processes` já existe no banco desde a migration 048 (criada por SQL
# cru), com is_principal adicionada em 056 e archived_at/archive_reason em 059.
# Até aqui NÃO havia model ORM — o acesso era 100% SQL cru em routers/processes.py
# e services/processo_service.py, o que deixava a tabela fora de Base.metadata e,
# portanto, invisível para o Alembic autogenerate e para checagens de drift.
#
# Este model é DECLARATIVO sobre a tabela existente: mapeia fielmente as colunas
# reais (ver migrations 048/056/059). NÃO altera schema, NÃO gera DDL, NÃO muda o
# comportamento dos routers (que seguem em SQL cru). O objetivo é fechar o achado
# C3 da auditoria (Etapa 3): tabela sem model → risco em disaster recovery e drift
# silencioso. Uma futura migração dos routers para ORM é trabalho separado.
from __future__ import annotations
from sqlalchemy import (
    Column, String, DateTime, func, Text, Numeric, ForeignKey, Boolean,
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class Process(Base):
    __tablename__ = "processes"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)

    # Identificação processual (larguras conforme migration 048 — note que aqui
    # tribunal/comarca/vara são varchar(160), mais largos que os campos legados
    # homônimos em `cases`).
    numero_cnj = Column(String(30), nullable=True)
    instancia = Column(String(20), nullable=True)
    tribunal = Column(String(160), nullable=True)
    comarca = Column(String(160), nullable=True)
    vara = Column(String(160), nullable=True)
    classe = Column(String(160), nullable=True)
    fase = Column(String(40), nullable=True)
    tipo = Column(String(30), nullable=False, server_default="judicial")

    # Auto-relacionamento: processo principal × acessórios (recurso, cautelar…).
    # index=True declara o ix_processes_processo_principal_id da migration 076 (#11)
    processo_principal_id = Column(
        String(36), ForeignKey("processes.id"), nullable=True, index=True
    )
    valor_causa = Column(Numeric, nullable=True)
    status = Column(String(30), nullable=False, server_default="ativo")

    # Um único processo principal ativo por caso (unique index parcial da 056).
    is_principal = Column(Boolean, nullable=False, server_default="false")

    # Arquivamento reversível (migration 059) — mesmo padrão de `cases`.
    archived_at = Column(DateTime(timezone=True), nullable=True)
    archive_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relacionamentos. `backref="processes"` cria Case.processes sem precisar
    # editar case.py (aditivo, lazy-loaded — não altera queries existentes).
    case = relationship("Case", backref="processes")
    processo_principal = relationship(
        "Process", remote_side=[id], backref="acessorios"
    )

    def __repr__(self):
        return f"<Process {self.numero_cnj or self.id} [{self.status}]>"
