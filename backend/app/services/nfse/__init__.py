# ── app/services/nfse/__init__.py ────────────────────────────────────────────
# Fachada do módulo de NFS-e. get_provider() é o GATE central: recusa quando o
# módulo está desligado (NFSE_ENABLED=false → 503) ou o provedor é desconhecido.
# O gate de credenciais faltando (→ 422) fica no adapter (_exigir_config), para
# que GET /nfse/status possa reportar `configured` sem levantar erro.
from __future__ import annotations

from app.core.config import get_settings

from .base import (
    NFSeConfigError,
    NFSeDesabilitadaError,
    NFSeError,
    NFSePedidoEmissao,
    NFSeProvider,
    NFSeProviderError,
    NFSeResultado,
    NFSeTomador,
    http_status_para_erro,
)
from .nuvem_fiscal import NuvemFiscalProvider

__all__ = [
    "NFSeProvider", "NFSePedidoEmissao", "NFSeTomador", "NFSeResultado",
    "NFSeError", "NFSeDesabilitadaError", "NFSeConfigError", "NFSeProviderError",
    "http_status_para_erro", "NuvemFiscalProvider",
    "get_provider", "configurado", "status_atual",
]


def get_provider() -> NFSeProvider:
    """Devolve o adapter conforme NFSE_PROVEDOR.

    Levanta:
      • NFSeDesabilitadaError — módulo desligado (router → 503);
      • NFSeConfigError — provedor não suportado (router → 422).
    """
    s = get_settings()
    if not s.NFSE_ENABLED:
        raise NFSeDesabilitadaError(
            "Módulo de NFS-e desativado (NFSE_ENABLED=false). A emissão fiscal "
            "nasce DESLIGADA e em homologação — a ativação é uma decisão do dono."
        )
    provedor = (s.NFSE_PROVEDOR or "").strip().lower()
    if provedor == "nuvemfiscal":
        return NuvemFiscalProvider()
    raise NFSeConfigError(
        f"Provedor de NFS-e '{provedor or '(vazio)'}' não suportado. "
        "Defina NFSE_PROVEDOR=nuvemfiscal."
    )


def configurado() -> bool:
    """True se as credenciais/empresa mínimas estão presentes (sem tocar rede)."""
    s = get_settings()
    return bool(
        s.NFSE_NUVEMFISCAL_CLIENT_ID
        and s.NFSE_NUVEMFISCAL_CLIENT_SECRET
        and s.NFSE_EMITENTE_CNPJ
    )


def status_atual() -> dict:
    """Status para a UF/gate do frontend — booleans/ambiente, sem segredos."""
    s = get_settings()
    return {
        "enabled": bool(s.NFSE_ENABLED),
        "configured": configurado(),
        "ambiente": "producao" if (s.NFSE_MODO or "").lower() == "producao" else "homologacao",
        "provedor": s.NFSE_PROVEDOR,
    }
