"""Contrato da Sala Jurídica sobre a persistência única de preliminares."""

from sqlalchemy.orm import synonym

from app.models.preliminar import (
    Preliminar,
    PreliminarDocumento,
    PreliminarEstado,
    PreliminarMensagem,
)

# Status do ciclo de vida da sessão (espelha os filtros da coluna esquerda).
SESSION_STATUS = {
    "em_analise",
    "aguardando_documentos",
    "pronta_para_caso",
    "convertida_em_caso",
    "arquivada",
}

# Modos rápidos de atuação (seletor ao lado do campo de mensagem).
CHAT_MODOS = {
    "conversa_livre",
    "organizar_fatos",
    "analisar_provas",
    "detectar_contradicoes",
    "estrategia_da_parte",
    "simular_defesa",
    "julgar_caso",
    "pesquisar_direito",
    "elaborar_documento",
    "revisar_documento",
}


class LegalChatSession(Preliminar):
    __mapper_args__ = {"polymorphic_identity": "sala_juridica"}
    cliente_potencial = synonym("potencial_cliente")
    area_sugerida = synonym("area")
    anexos = synonym("documentos")

    def __init__(self, **kwargs):
        kwargs.setdefault("status", "em_analise")
        super().__init__(**kwargs)


LegalChatAttachment = PreliminarDocumento
LegalChatMessage = PreliminarMensagem
LegalChatStateVersion = PreliminarEstado
