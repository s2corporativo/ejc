# ── app/models/case_parte.py ─────────────────────────────────────────────────
# Parte processual de um caso (autor, réu, terceiro, advogado, procurador).
# Model ORM para a tabela `case_partes` que JÁ EXISTE (antes manipulada por SQL
# cru). Mapeia exatamente as colunas reais; não cria/altera schema.
from __future__ import annotations
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Index, func, text
from sqlalchemy.orm import relationship
from app.core.database import Base


class CaseParte(Base):
    __tablename__ = "case_partes"
    __table_args__ = (
        # Fase A do DB-03: dedup exato sem CPF/CNPJ em claro. O índice é por
        # caso porque a mesma pessoa pode legitimamente figurar em casos distintos.
        Index(
            "ux_case_partes_case_doc_hash_active",
            "case_id", "cpf_cnpj_hash",
            unique=True,
            postgresql_where=text("cpf_cnpj_hash IS NOT NULL AND ativo = true"),
        ),
    )

    id      = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    tipo    = Column(String(30), nullable=False)   # autor|reu|terceiro|advogado|procurador
    papel_processual    = Column(String(100), nullable=True)
    nome    = Column(String(255), nullable=False)
    # DB-03 / Fase A: mantém as colunas plaintext apenas como LEGADO de leitura
    # durante o rollout. Novas escritas usam as properties abaixo, que cifram e
    # limpam o legado. A Fase B remove fisicamente estas três colunas depois de
    # `legacy_plaintext_count=0` comprovado em produção.
    _cpf_cnpj_legacy = Column("cpf_cnpj", String(18), nullable=True)
    cpf_cnpj_enc = Column(Text, nullable=True)
    cpf_cnpj_hash = Column(String(64), nullable=True)
    qualificacao = Column(Text, nullable=True)
    _email_legacy = Column("email", String(255), nullable=True)
    email_enc = Column(Text, nullable=True)
    _telefone_legacy = Column("telefone", String(20), nullable=True)
    telefone_enc = Column(Text, nullable=True)
    representante_legal = Column(String(255), nullable=True)
    oab     = Column(String(20), nullable=True)
    # index=True declara o ix_case_partes_client_id criado na migration 076 (#11)
    client_id = Column(String, ForeignKey("clients.id", ondelete="SET NULL"),
                       nullable=True, index=True)
    ativo   = Column(Boolean, default=True)
    observacoes = Column(Text, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(),
                         onupdate=func.now())
    created_by  = Column(String, nullable=True)

    case = relationship("Case", back_populates="partes")

    @staticmethod
    def _decrypt_or_legacy(ciphertext: str | None, legacy: str | None) -> str | None:
        if not ciphertext:
            return legacy
        from app.services.pii_crypto import decrypt
        try:
            return decrypt(ciphertext)
        except (ValueError, RuntimeError):
            # Não cai silenciosamente para o plaintext se existe ciphertext:
            # isso mascararia corrupção/chave errada. Marcador visível evita 500
            # em listagem e não expõe o valor legado por engano.
            return "[dado indisponível]"

    @property
    def cpf_cnpj(self) -> str | None:
        return self._decrypt_or_legacy(self.cpf_cnpj_enc, self._cpf_cnpj_legacy)

    @cpf_cnpj.setter
    def cpf_cnpj(self, value: str | None) -> None:
        from app.services.pii_crypto import encrypt, hash_documento, normalizar_documento
        exibicao = value.strip() if isinstance(value, str) else None
        normalizado = normalizar_documento(exibicao)
        self.cpf_cnpj_enc = encrypt(exibicao) if normalizado else None
        self.cpf_cnpj_hash = hash_documento(normalizado) if normalizado else None
        self._cpf_cnpj_legacy = None

    @property
    def email(self) -> str | None:
        return self._decrypt_or_legacy(self.email_enc, self._email_legacy)

    @email.setter
    def email(self, value: str | None) -> None:
        from app.services.pii_crypto import encrypt
        limpo = value.strip() if isinstance(value, str) else None
        self.email_enc = encrypt(limpo or None)
        self._email_legacy = None

    @property
    def telefone(self) -> str | None:
        return self._decrypt_or_legacy(self.telefone_enc, self._telefone_legacy)

    @telefone.setter
    def telefone(self, value: str | None) -> None:
        from app.services.pii_crypto import encrypt
        limpo = value.strip() if isinstance(value, str) else None
        self.telefone_enc = encrypt(limpo or None)
        self._telefone_legacy = None
