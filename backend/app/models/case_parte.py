# ── app/models/case_parte.py ─────────────────────────────────────────────────
# Parte processual de um caso (autor, réu, terceiro, advogado, procurador).
# Model ORM para a tabela `case_partes` que JÁ EXISTE (antes manipulada por SQL
# cru). Mapeia exatamente as colunas reais; não cria/altera schema.
#
# PII (DB-03, migration 159): o CPF/CNPJ da parte passa a viver CIFRADO
# (`cpf_cnpj_enc`, Fernet) + índice cego (`cpf_cnpj_hash`, HMAC), como em
# `clients` (client.py:79-84). A coluna em texto puro `cpf_cnpj` ainda existe
# (o CONTRACT é migration futura) e é mapeada como `cpf_cnpj_plain`, lida só
# como FALLBACK. O atributo público `cpf_cnpj` é uma hybrid property:
#   - leitura: decifra `cpf_cnpj_enc`; se NULL, devolve a coluna em claro
#     (linha legada ainda não backfillada ou gravada pelo router de SQL cru);
#   - escrita: normaliza, cifra + hasheia e ZERA a coluna em claro — o ORM
#     nunca mais grava documento em texto puro;
#   - expressão SQL (nível de classe): a coluna em claro, para os filtros
#     existentes (`clients.py:333`, `search.py:167`) continuarem compilando
#     até migrarem para `cpf_cnpj_hash == hash_documento(...)`.
from __future__ import annotations
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Index, func, text
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from app.core.database import Base


class CaseParte(Base):
    __tablename__ = "case_partes"
    __table_args__ = (
        # Índice PARCIAL das partes vivas por caso (migration 160, DB-05).
        # Declarado no ORM para o autogenerate não emitir DROP INDEX (mesmo
        # motivo da 155 / #11).
        Index("ix_case_partes_vivas_case", "case_id",
              postgresql_where=text("deleted_at IS NULL")),
    )

    id      = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    tipo    = Column(String(30), nullable=False)   # autor|reu|terceiro|advogado|procurador
    papel_processual    = Column(String(100), nullable=True)
    nome    = Column(String(255), nullable=False)
    # Coluna FÍSICA `cpf_cnpj` (texto puro, legado). NÃO escrever aqui — use o
    # atributo `cpf_cnpj` (hybrid) que grava nas colunas cifradas.
    cpf_cnpj_plain = Column("cpf_cnpj", String(18), nullable=True)
    cpf_cnpj_enc   = Column(Text, nullable=True)                 # Fernet, não indexável
    # index=True declara o ix_case_partes_cpf_cnpj_hash da migration 159.
    cpf_cnpj_hash  = Column(String(64), nullable=True, index=True)  # HMAC-SHA256 — busca exata
    qualificacao = Column(Text, nullable=True)
    email   = Column(String(255), nullable=True)
    telefone = Column(String(20), nullable=True)
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
    # Soft-delete (migration 160, DB-05). NULL = viva. Nenhuma listagem filtra
    # por isto ainda — ver relatório do PR (routers a ajustar).
    deleted_at  = Column(DateTime(timezone=True), nullable=True)

    case = relationship("Case", back_populates="partes")

    # ── CPF/CNPJ: leitura decifrada com fallback, escrita cifrada ────────────
    @hybrid_property
    def cpf_cnpj(self) -> str | None:
        if self.cpf_cnpj_enc:
            # Import local (como em client.py): evita ciclo model→serviço.
            from app.models.client import _decifrar_para_exibicao
            return _decifrar_para_exibicao(self.cpf_cnpj_enc)
        return self.cpf_cnpj_plain

    @cpf_cnpj.inplace.setter
    def _cpf_cnpj_setter(self, valor: str | None) -> None:
        from app.services.pii_crypto import encrypt, hash_documento, normalizar_documento
        norm = normalizar_documento(valor)
        self.cpf_cnpj_enc = encrypt(norm) if norm else None
        self.cpf_cnpj_hash = hash_documento(norm) if norm else None
        # Nunca deixar texto puro para trás — inclusive o legado desta linha.
        self.cpf_cnpj_plain = None

    @cpf_cnpj.inplace.expression
    @classmethod
    def _cpf_cnpj_expression(cls):
        # Só a coluna em claro é comparável em SQL (Fernet é não determinístico).
        # Busca por documento deve usar `cpf_cnpj_hash == hash_documento(doc)`.
        return cls.cpf_cnpj_plain
