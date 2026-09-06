# ── app/services/ajuizamento/conectores/base.py ──────────────────────────────
# Interface ÚNICA dos conectores judiciais. Toda operação devolve um
# ResultadoOperacao com estado explícito; a implementação padrão responde
# UNSUPPORTED sem I/O — cada conector sobrescreve só o que oferece de fato.
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.services.ajuizamento.canonico import CanonicalJudicialCase
from app.services.ajuizamento.capacidades import (
    ContextoConector, EstadoCapacidade, MatrizCapacidades, montar_matriz,
)


class ErroConector(RuntimeError):
    """Falha de transporte/protocolo no conector (sem PII/token na mensagem)."""


class TimeoutConector(ErroConector):
    """Timeout remoto — o chamador deve consultar o retorno anterior antes de reenviar."""


@dataclass
class ResultadoOperacao:
    estado: EstadoCapacidade
    dados: dict[str, Any] = field(default_factory=dict)
    mensagem: str = ""
    response_hash: str | None = None

    @property
    def ok(self) -> bool:
        return self.estado == EstadoCapacidade.SUPPORTED

    def to_dict(self) -> dict[str, Any]:
        return {"estado": self.estado.value, "mensagem": self.mensagem,
                "dados": self.dados, "response_hash": self.response_hash}


@dataclass
class ResultadoEnvio(ResultadoOperacao):
    """Resultado de file_new_case/append_petition (PdpjFilingResult e afins)."""
    protocol_number: str | None = None
    cnj_number: str | None = None
    external_process_id: str | None = None
    distribution_unit: str | None = None
    receipt: dict[str, Any] | None = None
    timestamp: datetime | None = None
    confirmado: bool = False

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update({
            "protocol_number": self.protocol_number, "cnj_number": self.cnj_number,
            "external_process_id": self.external_process_id,
            "distribution_unit": self.distribution_unit, "receipt": self.receipt,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "confirmado": self.confirmado,
        })
        return base


def hash_payload(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _unsupported(op: str) -> ResultadoOperacao:
    return ResultadoOperacao(EstadoCapacidade.UNSUPPORTED, mensagem=f"{op} não oferecida por este conector")


class ConectorJudicial(ABC):
    chave: str = ""
    sistema: str = ""

    # ── Capacidades ──────────────────────────────────────────────────────
    @abstractmethod
    def declaradas(self, ctx: ContextoConector) -> dict[str, tuple[EstadoCapacidade, str]]:
        """Capacidades que o conector oferece ANTES das regras transversais
        (homologação/credencial) — ver capacidades.montar_matriz."""

    def capacidades(self, ctx: ContextoConector) -> MatrizCapacidades:
        return montar_matriz(conector=self.chave, sistema=self.sistema, ctx=ctx, declaradas=self.declaradas(ctx))

    def can(self, ctx: ContextoConector, operacao: str) -> bool:
        return self.capacidades(ctx).pode(operacao)

    # ── Operações (default: UNSUPPORTED, sem I/O) ────────────────────────
    async def validate_target(self, ctx: ContextoConector, canonico: CanonicalJudicialCase) -> ResultadoOperacao:
        return _unsupported("validate_target")

    async def list_jurisdictions(self, ctx: ContextoConector) -> ResultadoOperacao:
        return _unsupported("list_jurisdictions")

    async def list_competences(self, ctx: ContextoConector) -> ResultadoOperacao:
        return _unsupported("list_competences")

    async def list_classes(self, ctx: ContextoConector) -> ResultadoOperacao:
        return _unsupported("list_classes")

    async def list_subjects(self, ctx: ContextoConector) -> ResultadoOperacao:
        return _unsupported("list_subjects")

    async def file_new_case(self, ctx: ContextoConector, canonico: CanonicalJudicialCase,
                            *, idempotency_key: str) -> ResultadoEnvio:
        return ResultadoEnvio(EstadoCapacidade.UNSUPPORTED, mensagem="file_new_case não oferecida por este conector")

    async def append_petition(self, ctx: ContextoConector, canonico: CanonicalJudicialCase,
                              *, numero_cnj: str, idempotency_key: str) -> ResultadoEnvio:
        return ResultadoEnvio(EstadoCapacidade.UNSUPPORTED, mensagem="append_petition não oferecida por este conector")

    async def read_process(self, ctx: ContextoConector, numero_cnj: str) -> ResultadoOperacao:
        return _unsupported("read_process")

    async def read_movements(self, ctx: ContextoConector, numero_cnj: str) -> ResultadoOperacao:
        return _unsupported("read_movements")

    async def read_notices(self, ctx: ContextoConector) -> ResultadoOperacao:
        return _unsupported("read_notices")

    async def download_document(self, ctx: ContextoConector, numero_cnj: str, id_documento: str) -> ResultadoOperacao:
        return _unsupported("download_document")

    async def receive_callback(self, ctx: ContextoConector, payload: dict[str, Any]) -> ResultadoOperacao:
        return _unsupported("receive_callback")

    async def get_receipt(self, ctx: ContextoConector, *, idempotency_key: str,
                          external_protocol: str | None = None) -> ResultadoOperacao:
        return _unsupported("get_receipt")

    async def sign(self, ctx: ContextoConector, *, document_hash: str) -> ResultadoOperacao:
        return _unsupported("sign")

    # ── Utilitário comum ─────────────────────────────────────────────────
    def _bloqueio_escrita(self, ctx: ContextoConector, operacao: str) -> ResultadoEnvio | None:
        """Responde REQUIRES_AUTHORIZATION/CONDITIONAL SEM chamada remota quando a
        matriz não libera a operação de escrita."""
        matriz = self.capacidades(ctx)
        estado = matriz.estado(operacao)
        if estado == EstadoCapacidade.SUPPORTED:
            return None
        motivo = matriz.itens[operacao].motivo if operacao in matriz.itens else ""
        return ResultadoEnvio(
            estado, mensagem=motivo or f"{operacao} indisponível",
            dados={"requisitos_autorizacao": matriz.requisitos_autorizacao},
        )
