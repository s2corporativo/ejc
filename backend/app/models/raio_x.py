"""Adaptadores do contrato Raio-X sobre a persistência única de preliminares."""

from app.models.preliminar import Preliminar, PreliminarDocumento


class RaioXAnalise(Preliminar):
    __mapper_args__ = {"polymorphic_identity": "raio_x"}

    def __init__(self, **kwargs):
        kwargs.setdefault("status", "novo")
        super().__init__(**kwargs)


RaioXDocumento = PreliminarDocumento
