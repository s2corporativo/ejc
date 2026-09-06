# ── app/services/ajuizamento/assinatura.py ───────────────────────────────────
# SigningProvider — abstração de assinatura da petição/anexos.
#
# A chave privada NUNCA entra no EJC (nem banco, nem disco do servidor). Os
# provedores que exigem chave local (A1 em arquivo), token (A3/PKCS#11) ou
# PSC em nuvem dependem de credencial/hardware fora do alcance do backend e
# respondem CONDITIONAL/REQUIRES_AUTHORIZATION com o que falta — sem fingir.
#
# O provedor SUPORTADO hoje é o registro de assinatura EXTERNA: o advogado
# assina com PJeOffice/A1/A3 na estação, sobe o PDF assinado (Document com
# sha256 calculado pelo pipeline de upload) e o EJC registra a evidência
# {certificate_subject, certificate_serial, provider, algorithm, signed_at,
# document_hash}, conferindo que o hash informado bate com o do documento.
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.ajuizamento.capacidades import EstadoCapacidade

PROVEDORES = ("registro_externo", "a1", "a3_pkcs11", "psc_nuvem", "pje_office")
ALGORITMOS = frozenset({"SHA256withRSA", "SHA256withECDSA", "SHA512withRSA"})


@dataclass(frozen=True)
class EvidenciaAssinatura:
    provider: str
    certificate_subject: str
    certificate_serial: str
    algorithm: str
    signed_at: datetime
    document_hash: str
    signed_document_id: str | None = None
    signature_type: str = "icp_brasil"
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider, "certificate_subject": self.certificate_subject,
            "certificate_serial": self.certificate_serial, "algorithm": self.algorithm,
            "signed_at": self.signed_at.isoformat(), "document_hash": self.document_hash,
            "signed_document_id": self.signed_document_id, "signature_type": self.signature_type,
            "extras": dict(self.extras),
        }


@dataclass
class ResultadoAssinatura:
    estado: EstadoCapacidade
    evidencia: EvidenciaAssinatura | None = None
    mensagem: str = ""

    @property
    def ok(self) -> bool:
        return self.estado == EstadoCapacidade.SUPPORTED and self.evidencia is not None


class SigningProvider(ABC):
    chave: str = ""

    @abstractmethod
    def estado(self) -> tuple[EstadoCapacidade, str]: ...

    @abstractmethod
    async def assinar(self, *, document_hash: str, dados: dict[str, Any]) -> ResultadoAssinatura: ...


class RegistroAssinaturaExternaProvider(SigningProvider):
    """Registra evidência de assinatura ICP-Brasil feita fora do EJC."""
    chave = "registro_externo"

    def estado(self) -> tuple[EstadoCapacidade, str]:
        return EstadoCapacidade.SUPPORTED, "registro de assinatura externa (PJeOffice/A1/A3 na estação)"

    async def assinar(self, *, document_hash: str, dados: dict[str, Any]) -> ResultadoAssinatura:
        faltando = [k for k in ("certificate_subject", "certificate_serial", "signed_document_hash") if not dados.get(k)]
        if faltando:
            return ResultadoAssinatura(EstadoCapacidade.CONDITIONAL, mensagem=f"campos obrigatórios ausentes: {', '.join(faltando)}")
        alg = dados.get("algorithm") or "SHA256withRSA"
        if alg not in ALGORITMOS:
            return ResultadoAssinatura(EstadoCapacidade.CONDITIONAL, mensagem=f"algoritmo não aceito: {alg}")
        h = str(dados["signed_document_hash"]).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", h):
            return ResultadoAssinatura(EstadoCapacidade.CONDITIONAL, mensagem="signed_document_hash deve ser SHA-256 hex (64)")
        # O hash informado precisa bater com o do Document assinado (calculado
        # pelo pipeline de upload) — é isso que impede "assinatura" de outro arquivo.
        hash_doc = (dados.get("document_sha256") or "").lower()
        if hash_doc and hash_doc != h:
            return ResultadoAssinatura(EstadoCapacidade.CONDITIONAL,
                                       mensagem="hash informado não confere com o SHA-256 do documento assinado enviado")
        serial = str(dados["certificate_serial"]).strip()
        if not re.fullmatch(r"[0-9A-Fa-f:]{4,80}", serial):
            return ResultadoAssinatura(EstadoCapacidade.CONDITIONAL, mensagem="certificate_serial inválido")
        ev = EvidenciaAssinatura(
            provider=str(dados.get("provider") or "pje_office"),
            certificate_subject=str(dados["certificate_subject"]).strip()[:300],
            certificate_serial=serial.upper(),
            algorithm=alg,
            signed_at=datetime.now(timezone.utc),
            document_hash=h,
            signed_document_id=dados.get("signed_document_id"),
            extras={"hash_original": document_hash},
        )
        return ResultadoAssinatura(EstadoCapacidade.SUPPORTED, evidencia=ev, mensagem="assinatura registrada")


class ProvedorDependenteDeCredencial(SigningProvider):
    """A1 (PFX no servidor), A3/PKCS#11 (token/leitora), PSC em nuvem —
    indisponíveis no backend por desenho (chave fora do EJC)."""

    def __init__(self, chave: str, motivo: str) -> None:
        self.chave = chave
        self._motivo = motivo

    def estado(self) -> tuple[EstadoCapacidade, str]:
        return EstadoCapacidade.REQUIRES_AUTHORIZATION, self._motivo

    async def assinar(self, *, document_hash: str, dados: dict[str, Any]) -> ResultadoAssinatura:
        return ResultadoAssinatura(EstadoCapacidade.REQUIRES_AUTHORIZATION, mensagem=self._motivo)


PROVEDORES_DISPONIVEIS: dict[str, SigningProvider] = {
    "registro_externo": RegistroAssinaturaExternaProvider(),
    "pje_office": RegistroAssinaturaExternaProvider(),
    "a1": ProvedorDependenteDeCredencial(
        "a1", "certificado A1 (.pfx) não é armazenado no servidor por política; assine na estação e registre"),
    "a3_pkcs11": ProvedorDependenteDeCredencial(
        "a3_pkcs11", "token A3/PKCS#11 só existe na estação do advogado; assine localmente e registre"),
    "psc_nuvem": ProvedorDependenteDeCredencial(
        "psc_nuvem", "PSC em nuvem exige contrato com prestadora credenciada ICP-Brasil e OAuth do titular"),
}


def provedor(chave: str | None) -> SigningProvider:
    return PROVEDORES_DISPONIVEIS.get(chave or "registro_externo", PROVEDORES_DISPONIVEIS["registro_externo"])


def matriz_assinatura() -> list[dict[str, Any]]:
    saida = []
    for chave, p in PROVEDORES_DISPONIVEIS.items():
        estado, motivo = p.estado()
        saida.append({"provider": chave, "estado": estado.value, "motivo": motivo})
    return saida
