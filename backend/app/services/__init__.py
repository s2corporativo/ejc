"""Inicialização dos serviços do EJC.

O import abaixo registra, por efeito colateral controlado, a política permanente
que mantém todos os documentos da Base de Conhecimento aprovados para uso pelo
RAG. O alias evita exposição acidental como API pública do pacote.
"""
from app.services import knowledge_autoapproval as _knowledge_autoapproval  # noqa: F401,E402
