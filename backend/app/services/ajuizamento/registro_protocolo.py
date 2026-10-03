# ── app/services/ajuizamento/registro_protocolo.py ───────────────────────────
# ProtocolRegistry — registro persistido de todo protocolo (eletrônico ou
# manual), sem segredo/token. Também faz a VINCULAÇÃO AO CASO: processo
# principal (services canônicos), peça (PATCH de protocolo equivalente) e
# movimento na timeline — numa única transação (commit do chamador).
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ajuizamento import JudicialFiling, JudicialProtocol
from app.models.case import Case, CaseMovimento
from app.models.legal_doc import LegalDoc, PecaStatus
from app.services.case_integrity_service import sincronizar_processo_principal_do_caso
from app.services.validators_service import normalizar_cnj, validar_cnj


def formatar_cnj(numero: str | None) -> str | None:
    """20 dígitos → NNNNNNN-DD.AAAA.J.TR.OOOO; outro formato volta como veio (trim)."""
    if not numero:
        return None
    d = normalizar_cnj(numero)
    if len(d) != 20:
        return numero.strip()[:30]
    return f"{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:]}"


async def registrar_protocolo(
    db: AsyncSession, *, filing: JudicialFiling, attempt_id: str | None, connector: str,
    idempotency_key: str | None, external_protocol: str | None, external_process_id: str | None,
    cnj_number: str | None, distribution_unit: str | None, status: str,
    receipt_document_id: str | None, request_hash: str | None, response_hash: str | None,
    confirmado: bool, created_by: str | None,
) -> JudicialProtocol:
    agora = datetime.now(timezone.utc)
    cnj_fmt = formatar_cnj(cnj_number)
    if cnj_fmt and len(normalizar_cnj(cnj_fmt)) == 20 and not validar_cnj(cnj_fmt):
        raise ValueError("Número CNJ inválido (dígito verificador não confere)")
    reg = JudicialProtocol(
        id=str(uuid4()), case_id=filing.case_id, filing_id=filing.id, attempt_id=attempt_id,
        tribunal=filing.tribunal_code, system=filing.system or "manual", environment=filing.environment,
        connector=connector, idempotency_key=idempotency_key,
        external_protocol=(external_protocol or "")[:120] or None,
        external_process_id=(external_process_id or "")[:120] or None,
        cnj_number=cnj_fmt, distribution_unit=(distribution_unit or "")[:200] or None,
        status=status, receipt_document_id=receipt_document_id,
        request_hash=request_hash, response_hash=response_hash,
        submitted_at=agora, confirmed_at=agora if confirmado else None,
        created_by=created_by, created_at=agora,
    )
    db.add(reg)
    filing.numero_cnj = cnj_fmt or filing.numero_cnj
    filing.protocolado_em = filing.protocolado_em or agora
    return reg


async def vincular_ao_caso(
    db: AsyncSession, *, filing: JudicialFiling, protocolo: JudicialProtocol, ator_id: str | None,
) -> dict[str, Any]:
    """Processo principal ← número CNJ/tribunal/valor; peça ← comprovante;
    timeline ← movimento 'peticao'. Commit do chamador (mesma transação)."""
    resultado: dict[str, Any] = {}
    case = (await db.execute(select(Case).where(Case.id == filing.case_id))).scalar_one_or_none()
    if case is None:
        return resultado
    if protocolo.cnj_number:
        proc = await sincronizar_processo_principal_do_caso(
            db, case_id=case.id, numero_processo=protocolo.cnj_number,
            tribunal=filing.tribunal_code, comarca=filing.jurisdicao,
            vara=protocolo.distribution_unit,
            valor_causa=Decimal(str(filing.valor_causa)) if filing.valor_causa is not None else None,
            tipo="judicial",
        )
        if proc:
            filing.process_id = proc.get("id")
            resultado["process_id"] = proc.get("id")
        case.has_judicial_process = True
    if filing.peticao_legal_doc_id:
        peca = (await db.execute(
            select(LegalDoc).where(LegalDoc.id == filing.peticao_legal_doc_id, LegalDoc.deleted_at.is_(None))
        )).scalar_one_or_none()
        if peca is not None:
            peca.numero_protocolo = (protocolo.external_protocol or protocolo.cnj_number or "")[:120] or peca.numero_protocolo
            peca.protocolo_tribunal = (filing.tribunal_code or "")[:120] or peca.protocolo_tribunal
            peca.protocolado_em = protocolo.confirmed_at or protocolo.submitted_at
            if protocolo.receipt_document_id:
                peca.protocolo_comprovante_doc_id = protocolo.receipt_document_id
            if peca.status in (PecaStatus.aprovada, PecaStatus.final):
                peca.status = PecaStatus.protocolada
            resultado["legal_doc_id"] = peca.id
    descricao = (
        f"Petição inicial protocolada via {protocolo.connector} "
        f"({filing.tribunal_code or 'tribunal não informado'})"
        + (f" — processo {protocolo.cnj_number}" if protocolo.cnj_number else "")
        + (f" — protocolo {protocolo.external_protocol}" if protocolo.external_protocol else "")
    )
    db.add(CaseMovimento(
        id=str(uuid4()), case_id=case.id, tipo="peticao", descricao=descricao[:2000],
        data_evento=protocolo.confirmed_at or protocolo.submitted_at, created_by=ator_id,
    ))
    resultado["movimento"] = descricao
    return resultado


async def listar_protocolos(db: AsyncSession, *, case_id: str | None = None, filing_id: str | None = None) -> list[JudicialProtocol]:
    stmt = select(JudicialProtocol).order_by(JudicialProtocol.created_at.desc())
    if case_id:
        stmt = stmt.where(JudicialProtocol.case_id == case_id)
    if filing_id:
        stmt = stmt.where(JudicialProtocol.filing_id == filing_id)
    return list((await db.execute(stmt)).scalars().all())


def protocolo_para_dict(p: JudicialProtocol) -> dict[str, Any]:
    return {
        "id": p.id, "case_id": p.case_id, "filing_id": p.filing_id, "attempt_id": p.attempt_id,
        "tribunal": p.tribunal, "system": p.system, "environment": p.environment, "connector": p.connector,
        "external_protocol": p.external_protocol, "external_process_id": p.external_process_id,
        "cnj_number": p.cnj_number, "distribution_unit": p.distribution_unit, "status": p.status,
        "receipt_document_id": p.receipt_document_id, "request_hash": p.request_hash,
        "response_hash": p.response_hash,
        "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
        "confirmed_at": p.confirmed_at.isoformat() if p.confirmed_at else None,
        "created_by": p.created_by,
    }
