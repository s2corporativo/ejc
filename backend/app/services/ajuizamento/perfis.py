# ── app/services/ajuizamento/perfis.py ───────────────────────────────────────
# JudicialIntegrationProfile — cadastro por administrador do perfil de cada
# tribunal/sistema/ambiente. É a ÚNICA fonte de endpoint remoto dos
# conectores; por isso a URL passa por guarda anti-SSRF (https, sem IP
# literal privado/loopback/link-local, sem credencial embutida).
from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ajuizamento import JudicialIntegrationProfile, SistemaJudicial

SISTEMAS = frozenset(s.value for s in SistemaJudicial)
SEGMENTOS = frozenset({"estadual", "federal", "trabalhista", "eleitoral", "militar", "superior"})
AMBIENTES = frozenset({"homologacao", "producao"})
TIPOS_INTEGRACAO = frozenset({"rest", "soap", "portal"})
TIPOS_AUTH = frozenset({"none", "oidc_client_credentials", "mni_consultante", "certificado", "api_key"})
_HOSTS_PROIBIDOS = frozenset({"localhost", "localhost.localdomain", "metadata.google.internal"})


class BaseUrlInvalida(ValueError):
    pass


def validar_base_url(url: str | None) -> str | None:
    """https obrigatório; host não pode ser IP privado/loopback/link-local nem
    localhost; sem usuário:senha; sem query/fragment. Retorna a URL limpa."""
    if url is None or not str(url).strip():
        return None
    u = str(url).strip()
    partes = urlsplit(u)
    if partes.scheme != "https":
        raise BaseUrlInvalida("base_url deve usar https")
    if partes.username or partes.password:
        raise BaseUrlInvalida("base_url não pode conter credenciais")
    if partes.query or partes.fragment:
        raise BaseUrlInvalida("base_url não pode conter query string ou fragmento")
    host = (partes.hostname or "").lower()
    if not host or host in _HOSTS_PROIBIDOS or host.endswith(".local") or host.endswith(".internal"):
        raise BaseUrlInvalida("host da base_url não permitido")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        or ip.is_multicast or ip.is_unspecified
    ):
        raise BaseUrlInvalida("base_url não pode apontar para IP privado/reservado")
    if "." not in host and ip is None:
        raise BaseUrlInvalida("host da base_url deve ser um FQDN")
    return u.rstrip("/")


def calcular_status(p: JudicialIntegrationProfile) -> str:
    if not p.ativo:
        return "UNSUPPORTED"
    if p.authorized and p.homologated_at and p.production_endpoint_verified and p.credentials_valid:
        return "SUPPORTED"
    if p.authorized or p.homologated_at:
        return "CONDITIONAL"
    return "REQUIRES_AUTHORIZATION"


_CAMPOS_EDITAVEIS = (
    "tribunal_nome", "segment", "degree", "system", "environment", "integration_type",
    "base_url", "api_version", "auth_type", "client_id_ref", "certificate_ref",
    "certificate_required", "filing_supported", "append_petition_supported",
    "process_query_supported", "movement_query_supported", "document_download_supported",
    "notice_query_supported", "callback_supported", "authorized",
    "production_endpoint_verified", "credentials_valid", "homologation_checklist",
    "homologated_at", "documentation_url", "ativo",
)


def _validar_dominios(dados: dict[str, Any]) -> None:
    if "system" in dados and dados["system"] not in SISTEMAS:
        raise ValueError(f"system inválido (use {sorted(SISTEMAS)})")
    if "segment" in dados and dados["segment"] not in SEGMENTOS:
        raise ValueError(f"segment inválido (use {sorted(SEGMENTOS)})")
    if "environment" in dados and dados["environment"] not in AMBIENTES:
        raise ValueError("environment deve ser homologacao|producao")
    if "integration_type" in dados and dados["integration_type"] not in TIPOS_INTEGRACAO:
        raise ValueError("integration_type deve ser rest|soap|portal")
    if "auth_type" in dados and dados["auth_type"] not in TIPOS_AUTH:
        raise ValueError(f"auth_type inválido (use {sorted(TIPOS_AUTH)})")
    for ref in ("client_id_ref", "certificate_ref"):
        v = dados.get(ref)
        if v and (":" not in v or len(v) > 120):
            raise ValueError(f"{ref} deve ser referência 'provider_key:field_key' ao cofre, nunca o valor")


async def criar_perfil(db: AsyncSession, dados: dict[str, Any], *, created_by: str | None) -> JudicialIntegrationProfile:
    _validar_dominios(dados)
    tribunal = (dados.get("tribunal_code") or "").strip().upper()
    if not tribunal or len(tribunal) > 10:
        raise ValueError("tribunal_code obrigatório (ex.: TJMG, TRF6)")
    p = JudicialIntegrationProfile(
        id=str(uuid4()), tribunal_code=tribunal, created_by=created_by,
        segment=dados.get("segment", "estadual"), degree=str(dados.get("degree") or "1"),
        system=dados["system"], environment=dados.get("environment", "homologacao"),
        integration_type=dados.get("integration_type", "rest"),
        auth_type=dados.get("auth_type", "none"),
    )
    _aplicar(p, dados)
    p.status = calcular_status(p)
    db.add(p)
    return p


async def atualizar_perfil(db: AsyncSession, perfil_id: str, dados: dict[str, Any]) -> JudicialIntegrationProfile | None:
    p = (await db.execute(
        select(JudicialIntegrationProfile).where(JudicialIntegrationProfile.id == perfil_id)
    )).scalar_one_or_none()
    if p is None:
        return None
    _validar_dominios(dados)
    _aplicar(p, dados)
    p.status = calcular_status(p)
    p.updated_at = datetime.now(timezone.utc)
    return p


def _aplicar(p: JudicialIntegrationProfile, dados: dict[str, Any]) -> None:
    for campo in _CAMPOS_EDITAVEIS:
        if campo not in dados:
            continue
        valor = dados[campo]
        if campo == "base_url":
            valor = validar_base_url(valor)
        if campo == "degree" and valor is not None:
            valor = str(valor)
        setattr(p, campo, valor)


async def listar_perfis(db: AsyncSession, *, somente_ativos: bool = False) -> list[JudicialIntegrationProfile]:
    stmt = select(JudicialIntegrationProfile).order_by(
        JudicialIntegrationProfile.tribunal_code, JudicialIntegrationProfile.system,
        JudicialIntegrationProfile.degree, JudicialIntegrationProfile.environment,
    )
    if somente_ativos:
        stmt = stmt.where(JudicialIntegrationProfile.ativo.is_(True))
    return list((await db.execute(stmt)).scalars().all())


async def resolver_perfil(
    db: AsyncSession, *, tribunal_code: str | None, system: str | None,
    degree: str | None = "1", environment: str | None = None,
) -> JudicialIntegrationProfile | None:
    if not tribunal_code or not system:
        return None
    stmt = select(JudicialIntegrationProfile).where(
        JudicialIntegrationProfile.tribunal_code == tribunal_code.upper(),
        JudicialIntegrationProfile.system == system,
        JudicialIntegrationProfile.ativo.is_(True),
    )
    if degree:
        stmt = stmt.where(JudicialIntegrationProfile.degree == str(degree))
    if environment:
        stmt = stmt.where(JudicialIntegrationProfile.environment == environment)
    # Produção prevalece sobre homologação quando ambos existem e o ambiente não foi fixado.
    perfis = list((await db.execute(stmt)).scalars().all())
    if not perfis:
        return None
    perfis.sort(key=lambda p: (p.environment != "producao", p.created_at or datetime.min.replace(tzinfo=timezone.utc)))
    return perfis[0]


def perfil_para_dict(p: JudicialIntegrationProfile) -> dict[str, Any]:
    return {
        "id": p.id, "tribunal_code": p.tribunal_code, "tribunal_nome": p.tribunal_nome,
        "segment": p.segment, "degree": p.degree, "system": p.system, "environment": p.environment,
        "integration_type": p.integration_type, "base_url": p.base_url, "api_version": p.api_version,
        "auth_type": p.auth_type, "client_id_ref": p.client_id_ref, "certificate_ref": p.certificate_ref,
        "certificate_required": p.certificate_required,
        "filing_supported": p.filing_supported, "append_petition_supported": p.append_petition_supported,
        "process_query_supported": p.process_query_supported, "movement_query_supported": p.movement_query_supported,
        "document_download_supported": p.document_download_supported, "notice_query_supported": p.notice_query_supported,
        "callback_supported": p.callback_supported, "authorized": p.authorized,
        "production_endpoint_verified": p.production_endpoint_verified, "credentials_valid": p.credentials_valid,
        "homologation_checklist": p.homologation_checklist,
        "homologated_at": p.homologated_at.isoformat() if p.homologated_at else None,
        "status": calcular_status(p), "documentation_url": p.documentation_url, "ativo": p.ativo,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
