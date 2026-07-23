# ── app/models/user.py ───────────────────────────────────────────────────────
from __future__ import annotations
from sqlalchemy import Column, String, Boolean, DateTime, Enum as SAEnum, func, ForeignKey, Numeric, Index, text
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class UserRole(str, enum.Enum):
    superadmin     = "superadmin"
    admin          = "admin"
    socio          = "socio"
    advogado       = "advogado"
    advogado_auxiliar = "advogado_auxiliar"
    financeiro     = "financeiro"
    estagiario     = "estagiario"
    secretaria     = "secretaria"
    cliente_externo = "cliente_externo"


class User(Base):
    __tablename__ = "users"

    # Unicidade de email é imposta pelo ÍNDICE ÚNICO PARCIAL uq_users_email_active
    # (migration 075): só entre usuários ATIVOS (deleted_at IS NULL), permitindo
    # recadastrar um e-mail liberado por soft-delete. Por isso email NÃO usa
    # unique=True — o índice UNIQUE CHEIO da migration 058 (uq_users_email) foi
    # DROPADO pela 075, que o substituiu por este parcial. BANCO É FONTE DA
    # VERDADE: reintroduzir unique=True aqui recriaria divergência (o autogenerate
    # proporia um UNIQUE que o banco real não tem). O `index=True` da coluna mapeia
    # o índice NÃO-único ix_users_email, que segue existindo no banco.
    __table_args__ = (
        Index("uq_users_email_active", "email", unique=True,
              postgresql_where=text("deleted_at IS NULL")),
    )

    id             = Column(String(36), primary_key=True)   # UUID string
    email          = Column(String(255), nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name      = Column(String(255), nullable=False)
    role           = Column(SAEnum(UserRole), nullable=False, default=UserRole.advogado)
    phone          = Column(String(30),  nullable=True)
    oab_number     = Column(String(50),  nullable=True)
    avatar_url     = Column(String(500), nullable=True)
    # Portal do Cliente: se role=cliente_externo, vincula ao cadastro
    client_id      = Column(String(36), ForeignKey("clients.id"), nullable=True, index=True)
    # DJEN: OAB p/ captura automática de intimações (job diário)
    djen_oab_numero = Column(String(10), nullable=True)
    djen_oab_uf     = Column(String(2),  nullable=True)
    # Rentabilidade: custo/hora do profissional (R$). NULL = não parametrizado.
    custo_hora     = Column(Numeric(10, 2), nullable=True)
    # Segurança: força troca de senha no 1º login (seed define True p/ usuários novos)
    must_change_password = Column(Boolean, default=False, nullable=False)
    # Cifrado em repouso (Fernet/pii_crypto — migr. 086): o token Fernet de um
    # segredo base32 tem ~140 chars; 255 dá folga. Legado em claro (<=64) ainda
    # cabe e é re-cifrado oportunisticamente no uso (routers/auth.py).
    totp_secret        = Column(String(255), nullable=True)
    totp_enabled       = Column(Boolean, default=False, nullable=False)
    # BANCO É FONTE DA VERDADE: a migration 001 cria is_active SEM NOT NULL
    # (só server_default 'true'), então a coluna PERMITE NULL no banco real. O
    # ORM declarava nullable=False (drift) — alinhado a nullable=True para o
    # autogenerate não propor um ALTER COLUMN ... SET NOT NULL espúrio. O
    # default=True continua preenchendo os inserts feitos pelo app.
    is_active      = Column(Boolean, default=True, nullable=True)

    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at     = Column(DateTime(timezone=True), nullable=True)
    last_login_at  = Column(DateTime(timezone=True), nullable=True)

    # Relacionamentos
    refresh_tokens       = relationship("RefreshToken",    back_populates="user", cascade="all, delete-orphan")
    cases_responsible    = relationship("Case", foreign_keys="Case.advogado_responsavel_id", back_populates="advogado_responsavel")
    deadlines            = relationship("Deadline", foreign_keys="Deadline.responsavel_id", back_populates="responsavel")
    audit_logs           = relationship("AuditLog", back_populates="user")
    ai_logs              = relationship("AILog",    foreign_keys="AILog.user_id", back_populates="user")
    legal_docs_revisados = relationship("LegalDoc", foreign_keys="LegalDoc.revisor_id", back_populates="revisor")

    def __repr__(self):
        return f"<User {self.email} [{self.role}]>"


class RefreshToken(Base):
    """
    Refresh tokens revogáveis com JTI único.
    Correção v2: antes os refresh tokens eram irrevogáveis (sem tabela).
    """
    __tablename__ = "refresh_tokens"

    id         = Column(String(36), primary_key=True)   # UUID
    user_id    = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    jti        = Column(String(36), unique=True, nullable=False)  # JWT ID único
    expires_at = Column(DateTime(timezone=True), nullable=False)
    # BANCO É FONTE DA VERDADE: a migration 001 cria revoked SEM NOT NULL (só
    # server_default 'false') — a coluna PERMITE NULL no banco real. O ORM
    # declarava nullable=False (drift); alinhado a nullable=True para o
    # autogenerate não emitir SET NOT NULL espúrio. O default=False segue
    # cobrindo os inserts do app.
    revoked    = Column(Boolean, default=False, nullable=True)
    # Janela de graça anti-corrida multi-aba (migr. 088): quando a rotação
    # revoga este token, grava QUANDO (revoked_at) e POR QUAL jti ele foi
    # substituído (replaced_by_jti). Reuso do token da ÚLTIMA rotação dentro
    # da graça (~60s) = corrida benigna entre abas → 401 simples; fora dela
    # (ou token de rotação mais antiga) = replay → revoga todas as sessões.
    revoked_at      = Column(DateTime(timezone=True), nullable=True)
    replaced_by_jti = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="refresh_tokens")
