"""Unit of Work local para o lifecycle físico de documentos.

A transação de banco e o filesystem não compartilham atomicidade. Este módulo
reduz a janela de órfãos ao manter o arquivo sob um lifecycle explícito:

    staging -> promovido -> confirmado

Se o chamador sair do contexto antes de ``confirmar()``, o arquivo é compensado
automaticamente. A confirmação só deve ocorrer depois do commit de banco/audit.

O módulo é neutro: não conhece FastAPI, SQLAlchemy, caso, cliente, RBAC ou
AuditLog. Outbox durável para storage remoto permanece uma etapa separada.
"""
from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Self

from app.services.document_upload_stream import (
    StreamUploadAssincrono,
    UploadEmStaging,
    descartar_staging,
    promover_staging,
    receber_em_staging,
)

logger = logging.getLogger(__name__)


class EstadoStorageLocal(StrEnum):
    STAGING = "staging"
    PROMOVIDO = "promovido"
    CONFIRMADO = "confirmado"
    COMPENSADO = "compensado"


class EstadoStorageInvalidoError(RuntimeError):
    """Transição inválida do lifecycle físico."""


class CompensacaoStorageError(RuntimeError):
    """Cleanup local falhou quando não havia outra exceção em curso."""


class DocumentStorageUnitOfWork:
    """Lifecycle fail-closed de um único arquivo local.

    Uso esperado::

        async with await DocumentStorageUnitOfWork.iniciar(...) as storage:
            # validar hash/MIME e regras de domínio
            storage.promover()
            # criar Document + AuditLog
            await db.commit()
            storage.confirmar()

    Qualquer exceção antes de ``confirmar`` remove staging ou destino promovido.
    """

    def __init__(self, staging: UploadEmStaging, destino_final: Path) -> None:
        self._staging = staging
        self._destino_final = destino_final
        self._estado = EstadoStorageLocal.STAGING

    @classmethod
    async def iniciar(
        cls,
        upload: StreamUploadAssincrono,
        *,
        destino_final: Path,
        suffix: str,
        max_bytes: int,
    ) -> Self:
        staging = await receber_em_staging(
            upload,
            diretorio=destino_final.parent,
            suffix=suffix,
            max_bytes=max_bytes,
        )
        return cls(staging=staging, destino_final=destino_final)

    @property
    def estado(self) -> EstadoStorageLocal:
        return self._estado

    @property
    def sha256(self) -> str:
        return self._staging.sha256

    @property
    def size_bytes(self) -> int:
        return self._staging.size_bytes

    @property
    def amostra_inicial(self) -> bytes:
        return self._staging.amostra_inicial

    @property
    def destino_final(self) -> Path:
        return self._destino_final

    def promover(self) -> None:
        if self._estado is not EstadoStorageLocal.STAGING:
            raise EstadoStorageInvalidoError("storage não está em staging")
        promover_staging(self._staging, self._destino_final)
        self._estado = EstadoStorageLocal.PROMOVIDO

    def confirmar(self) -> None:
        if self._estado is not EstadoStorageLocal.PROMOVIDO:
            raise EstadoStorageInvalidoError("storage não está promovido")
        self._estado = EstadoStorageLocal.CONFIRMADO

    def compensar(self) -> bool:
        """Compensa de forma idempotente e sem expor path em erro/log.

        Retorna ``True`` quando o estado ficou seguro/compensado. Se o arquivo já
        foi confirmado, não o remove: confirmação representa commit de domínio.
        """

        if self._estado in {EstadoStorageLocal.CONFIRMADO, EstadoStorageLocal.COMPENSADO}:
            return True

        try:
            if self._estado is EstadoStorageLocal.STAGING:
                descartar_staging(self._staging)
            elif self._estado is EstadoStorageLocal.PROMOVIDO:
                try:
                    self._destino_final.unlink()
                except FileNotFoundError:
                    pass
            else:  # pragma: no cover - defesa para estado futuro desconhecido
                raise EstadoStorageInvalidoError("estado de storage desconhecido")
        except OSError:
            logger.error("Falha ao compensar storage documental local")
            return False

        self._estado = EstadoStorageLocal.COMPENSADO
        return True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if self._estado not in {EstadoStorageLocal.CONFIRMADO, EstadoStorageLocal.COMPENSADO}:
            compensado = self.compensar()
            if not compensado and exc_type is None:
                raise CompensacaoStorageError("falha ao compensar storage documental")
        # Nunca suprimir a exceção original do fluxo de domínio/DB.
        return False
