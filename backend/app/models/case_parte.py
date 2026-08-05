# ── app/models/case_parte.py ─────────────────────────────────────────────────
# Parte processual de um caso (autor, réu, terceiro, advogado, procurador).
# Model ORM para a tabela `case_partes` que JÁ EXISTE (antes manipulada por SQL
# cru). Mapeia exatamente as colunas reais; não cria/altera schema.
from __future__ import annotations
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class CaseParte(Base):
    __tablename__ = "case_partes"

    id      = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    tipo    = Column(String(30), nullable=False)   # autor|reu|terceiro|advogado|procurador
    papel_processual    = Column(String(100), nullable=True)
    nome    = Column(String(255), nullable=False)
    # PII (LGPD) — padrão Bloco 6a, o MESMO de models/client.py. A migration 127
    # removeu `cpf_cnpj` em texto puro: o documento da parte agora existe SÓ
    # cifrado. Ler em claro é sob demanda, via `cpf_cnpj_plain`; buscar/cruzar
    # é pelo hash (índice cego), nunca pelo valor.
    cpf_cnpj_enc       = Column(Text, nullable=True)          # Fernet — não indexável
    # Índice ix_case_partes_cpf_cnpj_hash (migration 127) — NÃO único: a mesma
    # pessoa é parte legitimamente em vários casos.
    cpf_cnpj_hash      = Column(String(64), nullable=True, index=True)
    cpf_cnpj_mascarado = Column(String(32), nullable=True)    # exibição segura
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

    case = relationship("Case", back_populates="partes")

    @property
    def cpf_cnpj_plain(self) -> str | None:
        """Documento em claro, sob demanda (migration 127).

        Reusa `_decifrar_para_exibicao` de models/client.py em vez de repetir a
        lógica: a resiliência importa igual aqui — a listagem de partes decifra
        CADA linha, e um ciphertext corrompido (chave rotacionada) não pode
        derrubar a aba inteira. Degrada só a linha, com marcador VISÍVEL.
        """
        from app.models.client import _decifrar_para_exibicao

        return _decifrar_para_exibicao(self.cpf_cnpj_enc)
