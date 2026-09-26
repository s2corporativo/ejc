"""Aplicação humana de divergências DataJud previamente sinalizadas."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import CaseMovimento
from app.models.process import Process
from app.models.saneamento import DatajudSnapshot, Divergencia
from app.schemas.process import ProcessUpdate
from app.services.process_provenance_service import registrar_proveniencia
from app.services.processo_service import atualizar_processo
from app.services.saneamento.reconciliacao import TipoDivergencia


def rotulo_datajud(valor) -> str | None:
    if isinstance(valor, str):
        txt = valor.strip()
        return txt if txt and not txt.isdigit() else None
    if isinstance(valor, dict):
        for chave in ("nome", "descricao", "nomeClasse", "nomeOrgao"):
            txt = str(valor.get(chave) or "").strip()
            if txt:
                return txt
    return None


async def aplicar_divergencia(
    db: AsyncSession,
    *,
    divergencia: Divergencia,
    user_id: str,
) -> dict:
    """Aplica apenas campos representáveis com segurança no Process canônico."""
    digitos = func.regexp_replace(Process.numero_cnj, r"\D", "", "g")
    processos = (
        await db.execute(
            select(Process).where(
                digitos == divergencia.numero_cnj,
                Process.deleted_at.is_(None),
                Process.status != "arquivado",
            )
        )
    ).scalars().all()

    principais = [p for p in processos if p.is_principal]
    processo = principais[0] if len(principais) == 1 else (
        processos[0] if len(processos) == 1 else None
    )
    if processo is None:
        raise HTTPException(
            status_code=409,
            detail="Processo canônico ambíguo; revisão manual necessária.",
        )

    snapshot = (
        await db.execute(
            select(DatajudSnapshot)
            .where(DatajudSnapshot.numero_cnj == divergencia.numero_cnj)
            .order_by(DatajudSnapshot.coletado_em.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status_code=409, detail="Snapshot DataJud não encontrado.")
    if int(snapshot.nivel_sigilo or 0) > 0:
        raise HTTPException(
            status_code=422,
            detail="Processo sigiloso não pode ser atualizado por este fluxo.",
        )

    payload = snapshot.payload or {}
    campos: dict[str, object] = {}
    if divergencia.tipo == TipoDivergencia.CLASSE_DIVERGENTE.value:
        rotulo = rotulo_datajud(payload.get("classe"))
        if not rotulo:
            raise HTTPException(
                status_code=422,
                detail="DataJud sem rótulo textual seguro para classe.",
            )
        campos["classe"] = rotulo
    elif divergencia.tipo == TipoDivergencia.ORGAO_DIVERGENTE.value:
        rotulo = rotulo_datajud(payload.get("orgaoJulgador"))
        if not rotulo:
            raise HTTPException(
                status_code=422,
                detail="DataJud sem rótulo textual seguro para órgão julgador.",
            )
        campos["vara"] = rotulo
    elif divergencia.tipo == TipoDivergencia.DATA_AJUIZAMENTO_DIVERGENTE.value:
        if not snapshot.data_ajuizamento:
            raise HTTPException(
                status_code=422,
                detail="Snapshot DataJud sem data de ajuizamento válida.",
            )
        campos["data_ajuizamento"] = snapshot.data_ajuizamento
    else:
        raise HTTPException(
            status_code=422,
            detail="Divergência apenas informativa; aplicação indisponível.",
        )

    antes = {campo: getattr(processo, campo, None) for campo in campos}
    await atualizar_processo(processo.id, ProcessUpdate(**campos), db)
    await registrar_proveniencia(
        db,
        process_id=processo.id,
        campos=campos,
        source_type="datajud",
        source_ref=f"saneamento_divergencia:{divergencia.id}",
        source_date=snapshot.coletado_em,
        confidence="oficial",
        confirmed_by=user_id,
    )

    divergencia.tratada = True
    divergencia.tratada_por = user_id
    divergencia.tratada_em = datetime.now(timezone.utc)

    db.add(
        CaseMovimento(
            id=str(uuid4()),
            case_id=processo.case_id,
            tipo="nota",
            descricao=(
                "Metadado processual atualizado após comparação assistida "
                f"com DataJud: {', '.join(campos)}."
            ),
            created_by=user_id,
        )
    )

    return {
        "process_id": processo.id,
        "case_id": processo.case_id,
        "campos": campos,
        "antes": antes,
    }
