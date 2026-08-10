"""Contrato de domínio para operações assíncronas de storage documental.

Este módulo NÃO é persistência e NÃO cria uma outbox por si só. Ele define os
estados/transições que a futura tabela/worker deverá obedecer para reconciliar
PostgreSQL com storage remoto sem fingir atomicidade distribuída.

Nenhum erro livre de provider faz parte do contrato. O alvo remoto é tratado
como valor opaco e nunca entra no contexto seguro de auditoria/log.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from enum import StrEnum


class StorageBackend(StrEnum):
    DRIVE = "drive"


class TipoOperacaoStorage(StrEnum):
    EXCLUIR_OBJETO = "delete_object"


class StatusOperacaoStorage(StrEnum):
    PENDENTE = "pending"
    PROCESSANDO = "processing"
    AGUARDANDO_RETRY = "retry_pending"
    CONCLUIDA = "succeeded"
    FALHA_TERMINAL = "failed_terminal"


class ResultadoExecucaoStorage(StrEnum):
    SUCESSO = "success"
    JA_AUSENTE = "already_absent"
    FALHA_TRANSITORIA = "retryable_failure"
    FALHA_TERMINAL = "terminal_failure"


class CodigoErroStorage(StrEnum):
    INDISPONIVEL = "unavailable"
    TIMEOUT = "timeout"
    PERMISSAO = "permission_denied"
    RESPOSTA_INVALIDA = "invalid_response"
    ERRO_DESCONHECIDO = "unknown"


class TransicaoOutboxInvalidaError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ComandoStorage:
    document_id: str
    backend: StorageBackend
    operacao: TipoOperacaoStorage
    alvo_opaco: str

    def __post_init__(self) -> None:
        if not self.document_id or len(self.document_id) > 64:
            raise ValueError("document_id inválido para operação de storage")
        if not self.alvo_opaco or len(self.alvo_opaco) > 1024:
            raise ValueError("alvo de storage inválido")

    @property
    def chave_idempotencia(self) -> str:
        """Hash determinístico sem expor alvo/IDs em logs ou índices textuais."""

        material = "\x1f".join(
            (
                self.backend.value,
                self.operacao.value,
                self.document_id,
                self.alvo_opaco,
            )
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def contexto_seguro(self) -> dict[str, str]:
        """Contexto adequado a AuditLog/telemetria; exclui o alvo remoto."""

        return {
            "backend": self.backend.value,
            "operacao": self.operacao.value,
            "chave_idempotencia": self.chave_idempotencia,
        }


@dataclass(frozen=True, slots=True)
class EstadoOperacaoStorage:
    status: StatusOperacaoStorage = StatusOperacaoStorage.PENDENTE
    tentativas: int = 0
    erro_codigo: CodigoErroStorage | None = None

    def __post_init__(self) -> None:
        if self.tentativas < 0:
            raise ValueError("tentativas não pode ser negativo")
        if self.status in {
            StatusOperacaoStorage.PENDENTE,
            StatusOperacaoStorage.PROCESSANDO,
            StatusOperacaoStorage.CONCLUIDA,
        } and self.erro_codigo is not None:
            raise ValueError("estado não aceita erro_codigo")
        if self.status in {
            StatusOperacaoStorage.AGUARDANDO_RETRY,
            StatusOperacaoStorage.FALHA_TERMINAL,
        } and self.erro_codigo is None:
            raise ValueError("estado de falha exige erro_codigo")

    def iniciar_tentativa(self) -> "EstadoOperacaoStorage":
        if self.status not in {
            StatusOperacaoStorage.PENDENTE,
            StatusOperacaoStorage.AGUARDANDO_RETRY,
        }:
            raise TransicaoOutboxInvalidaError("operação não está disponível para claim")
        return replace(
            self,
            status=StatusOperacaoStorage.PROCESSANDO,
            tentativas=self.tentativas + 1,
            erro_codigo=None,
        )

    def aplicar_resultado(
        self,
        resultado: ResultadoExecucaoStorage,
        *,
        erro_codigo: CodigoErroStorage | None = None,
        max_tentativas: int,
    ) -> "EstadoOperacaoStorage":
        if self.status is not StatusOperacaoStorage.PROCESSANDO:
            raise TransicaoOutboxInvalidaError("resultado exige operação em processamento")
        if max_tentativas < 1:
            raise ValueError("max_tentativas deve ser positivo")

        if resultado in {
            ResultadoExecucaoStorage.SUCESSO,
            ResultadoExecucaoStorage.JA_AUSENTE,
        }:
            if erro_codigo is not None:
                raise ValueError("sucesso não aceita erro_codigo")
            return replace(
                self,
                status=StatusOperacaoStorage.CONCLUIDA,
                erro_codigo=None,
            )

        if erro_codigo is None:
            raise ValueError("falha exige erro_codigo")

        if resultado is ResultadoExecucaoStorage.FALHA_TERMINAL:
            return replace(
                self,
                status=StatusOperacaoStorage.FALHA_TERMINAL,
                erro_codigo=erro_codigo,
            )

        if resultado is ResultadoExecucaoStorage.FALHA_TRANSITORIA:
            status = (
                StatusOperacaoStorage.FALHA_TERMINAL
                if self.tentativas >= max_tentativas
                else StatusOperacaoStorage.AGUARDANDO_RETRY
            )
            return replace(self, status=status, erro_codigo=erro_codigo)

        raise ValueError("resultado de storage desconhecido")
