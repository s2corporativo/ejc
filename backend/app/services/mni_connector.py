# ── app/services/mni_connector.py ────────────────────────────────────────────
# Cliente SOAP genérico para o Modelo Nacional de Interoperabilidade (MNI)
# 2.2.2 — Issue #762, Fase A (SOMENTE LEITURA).
#
# NUNCA chamar de dentro de uma request HTTP síncrona do usuário: o WSDL do
# tribunal pode responder lentamente ou ficar indisponível, e isso bloquearia
# o event loop/worker da API. Todo uso real fica dentro de tasks Celery
# (app/tasks/processo_eletronico_tasks.py).
#
# `entregarManifestacaoProcessual` (peticionamento) está DELIBERADAMENTE fora
# desta classe — não implementar nem criar stub, é escopo de fase futura.
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from zeep import Client, Settings
from zeep.transports import Transport

logger = logging.getLogger("ejc.mni")

# Timeout generoso — tribunais MNI costumam responder devagar; nunca chamado
# em request síncrona, então o custo de esperar cabe aqui.
TIMEOUT_PADRAO_SEGUNDOS = 60.0


class MNIConnectorError(Exception):
    """Erro de comunicação/protocolo com o serviço MNI do tribunal."""


@dataclass
class MNICredencial:
    """Credencial já decifrada (só existe em memória, dentro da task; nunca
    persiste nem loga em claro)."""
    id_consultante: str
    senha_consultante: str


@dataclass
class ConsultaProcessoResultado:
    numero_processo: str
    dados_basicos: dict[str, Any] = field(default_factory=dict)
    movimentos: list[dict[str, Any]] = field(default_factory=list)
    documentos: list[dict[str, Any]] = field(default_factory=list)
    sucesso: bool = True
    mensagem: str | None = None


class MNIConnector:
    """Cliente SOAP para um endpoint MNI 2.2.2 de um tribunal específico.

    Uma instância é por (endpoint_wsdl, credencial) — não compartilhar entre
    tribunais/advogados diferentes."""

    def __init__(
        self,
        endpoint_wsdl: str,
        credencial: MNICredencial,
        timeout: float = TIMEOUT_PADRAO_SEGUNDOS,
    ) -> None:
        self.endpoint_wsdl = endpoint_wsdl
        self._credencial = credencial
        self._timeout = timeout
        self._client: Client | None = None

    def _get_client(self) -> Client:
        if self._client is None:
            transport = Transport(timeout=self._timeout, operation_timeout=self._timeout)
            # forbid_external: WSDL/XSD do tribunal não pode arrastar
            # import/include/DTD externo para outra URL (SSRF via WSDL
            # malicioso/comprometido) — defesa em profundidade além do
            # pin de versão (PYSEC-2026-2323 exige zeep>=4.3.3).
            settings = Settings(forbid_external=True)
            self._client = Client(self.endpoint_wsdl, transport=transport, settings=settings)
        return self._client

    def consultar_processo(
        self,
        numero_processo: str,
        movimentos: bool = True,
        incluir_cabecalho: bool = True,
        documento: str | None = None,
    ) -> ConsultaProcessoResultado:
        """consultarProcesso do MNI. `documento` opcional restringe a consulta
        a um único idDocumento (download individual); None traz metadados de
        todos os documentos sem o conteúdo binário."""
        cliente = self._get_client()
        try:
            resposta = cliente.service.consultarProcesso(
                idConsultante=self._credencial.id_consultante,
                senhaConsultante=self._credencial.senha_consultante,
                numeroProcesso=numero_processo,
                movimentos=movimentos,
                incluirCabecalho=incluir_cabecalho,
                documento=documento,
            )
        except Exception as e:  # noqa: BLE001 — erro de transporte/protocolo SOAP
            logger.error(
                "[MNI] consultarProcesso falhou (processo=%s): %s",
                numero_processo, e,
            )
            raise MNIConnectorError(
                f"Falha ao consultar processo no MNI: {e}"
            ) from e

        sucesso = getattr(resposta, "sucesso", True)
        if not sucesso:
            mensagem = getattr(resposta, "mensagem", "Consulta recusada pelo tribunal")
            return ConsultaProcessoResultado(
                numero_processo=numero_processo, sucesso=False, mensagem=mensagem,
            )

        dados_basicos = _serializar(getattr(resposta, "dadosBasicos", None))
        movs = [
            _serializar(m)
            for m in (getattr(getattr(resposta, "dadosBasicos", None), "movimento", None) or [])
        ]
        docs = [
            _serializar(d)
            for d in (getattr(getattr(resposta, "dadosBasicos", None), "documento", None) or [])
        ]
        return ConsultaProcessoResultado(
            numero_processo=numero_processo,
            dados_basicos=dados_basicos,
            movimentos=movs,
            documentos=docs,
            sucesso=True,
        )

    def consultar_avisos_pendentes(
        self, data_referencia: date | None = None,
    ) -> list[dict[str, Any]]:
        """consultarAvisosPendentes — intimações/comunicações pendentes de
        ciência do advogado neste tribunal."""
        cliente = self._get_client()
        try:
            resposta = cliente.service.consultarAvisosPendentes(
                idConsultante=self._credencial.id_consultante,
                senhaConsultante=self._credencial.senha_consultante,
                dataReferencia=data_referencia,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("[MNI] consultarAvisosPendentes falhou: %s", e)
            raise MNIConnectorError(
                f"Falha ao consultar avisos pendentes no MNI: {e}"
            ) from e
        avisos = getattr(resposta, "avisoPendente", None) or getattr(resposta, "aviso", None) or []
        return [_serializar(a) for a in avisos]

    def consultar_teor_comunicacao(self, identificador_aviso: str) -> dict[str, Any]:
        """consultarTeorComunicacao — conteúdo de uma intimação/comunicação
        específica, identificada pelo aviso retornado em consultar_avisos_pendentes."""
        cliente = self._get_client()
        try:
            resposta = cliente.service.consultarTeorComunicacao(
                idConsultante=self._credencial.id_consultante,
                senhaConsultante=self._credencial.senha_consultante,
                identificadorAviso=identificador_aviso,
            )
        except Exception as e:  # noqa: BLE001
            logger.error(
                "[MNI] consultarTeorComunicacao falhou (aviso=%s): %s",
                identificador_aviso, e,
            )
            raise MNIConnectorError(
                f"Falha ao consultar teor da comunicação no MNI: {e}"
            ) from e
        return _serializar(resposta)


def _serializar(obj: Any) -> Any:
    """Converte objetos zeep (CompoundValue) em dict/list Python puro,
    recursivamente — para não vazar tipos zeep para as camadas de domínio."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_serializar(i) for i in obj]
    if hasattr(obj, "__values__"):  # zeep.xsd.CompoundValue
        return {k: _serializar(v) for k, v in obj.__values__.items()}
    if isinstance(obj, dict):
        return {k: _serializar(v) for k, v in obj.items()}
    return str(obj)
