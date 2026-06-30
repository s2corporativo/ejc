# ── app/models/template.py ───────────────────────────────────────────────────
# Templates de peças com variáveis {{cliente_nome}}, {{numero_processo}}, etc.
from sqlalchemy import Column, String, Boolean, DateTime, Text, func
from app.core.database import Base


class DocTemplate(Base):
    __tablename__ = "doc_templates"

    id         = Column(String(36), primary_key=True)
    titulo     = Column(String(255), nullable=False)
    tipo_peca  = Column(String(50), nullable=False)   # mesmo domínio de PecaTipo
    area       = Column(String(30), nullable=True)
    descricao  = Column(Text, nullable=True)
    conteudo   = Column(Text, nullable=False)         # markdown com {{variaveis}}
    ativo      = Column(Boolean, default=True)
    created_by = Column(String(36), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
