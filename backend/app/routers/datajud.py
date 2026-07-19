"""DataJud CNJ public API endpoints"""
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import verificar_acesso_caso
from app.services import datajud_service
from app.models.case import Case

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/datajud", tags=["datajud"])


@router.get("/process/{numero_cnj}")
async def lookup_process(
    numero_cnj: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Busca processo pelo número CNJ"""
    try:
        result = await datajud_service.consultar_processo(numero_cnj)
        if result is None:
            raise HTTPException(404, "Processo não localizado no DataJud")
        return result
    except HTTPException:
        raise
    except datajud_service.DataJudDesabilitadoError as exc:
        raise HTTPException(503, str(exc))
    except datajud_service.TribunalNaoMapeadoError as exc:
        raise HTTPException(422, str(exc))
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else None
        log.warning(
            "DataJud recusou consulta (tipo=%s status=%s)",
            type(exc).__name__, status,
        )
        if status in (401, 403):
            raise HTTPException(
                503,
                "Chave pública do DataJud ausente, inválida ou rotacionada pelo CNJ.",
            )
        if status == 429:
            raise HTTPException(503, "DataJud temporariamente limitado. Tente novamente.")
        raise HTTPException(502, "DataJud indisponível. Tente novamente.")
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        log.warning("DataJud indisponível (tipo=%s)", type(exc).__name__)
        raise HTTPException(502, "DataJud indisponível. Tente novamente.")
    except Exception as exc:
        # Contrato defensivo do endpoint: sem corpo, número CNJ ou segredo no log.
        log.error("Falha inesperada no DataJud (tipo=%s)", type(exc).__name__)
        raise HTTPException(502, "DataJud indisponível. Tente novamente.")


@router.post("/cases/{case_id}/sync")
async def sync_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Sincroniza movimentações de um caso com o DataJud"""
    result = await db.execute(select(Case).where(Case.id == case_id, Case.deleted_at.is_(None)))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Case not found")
    await verificar_acesso_caso(db, current_user, case_id)
    if not case.numero_processo:
        raise HTTPException(400, "Case has no numero_processo")
    try:
        synced = await datajud_service.sincronizar_caso(db, case)
        # BUG-16: ao sincronizar o caso, também sincroniza os PRAZOS (rascunho/HITL).
        prazos = await datajud_service.sincronizar_prazos_datajud(
            case.id, case.numero_processo, db
        )
        await db.commit()
        return {
            "synced": synced,
            "numero_processo": case.numero_processo,
            "prazos": prazos,
        }
    except datajud_service.DataJudDesabilitadoError as exc:
        await db.rollback()
        raise HTTPException(503, str(exc))
    except datajud_service.TribunalNaoMapeadoError as exc:
        await db.rollback()
        raise HTTPException(422, str(exc))
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        await db.rollback()
        log.warning("Falha no sync DataJud (tipo=%s)", type(exc).__name__)
        raise HTTPException(502, "Erro ao sincronizar com o DataJud")
    except Exception as exc:
        await db.rollback()
        log.error("Falha inesperada no sync DataJud (tipo=%s)", type(exc).__name__)
        raise HTTPException(502, "Erro ao sincronizar com o DataJud")


@router.post("/cases/{case_id}/sync-prazos")
async def sync_prazos(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """BUG-16: sincronização MANUAL de prazos do caso a partir do DataJud.

    Cria prazos (deadlines) preliminares — rascunho, exigem revisão do advogado
    (HITL/OAB). Dedup por referencia_datajud: reexecutar não duplica.
    """
    result = await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Case not found")
    await verificar_acesso_caso(db, current_user, case_id)
    if not case.numero_processo:
        raise HTTPException(400, "Case has no numero_processo")
    prazos = await datajud_service.sincronizar_prazos_datajud(
        case.id, case.numero_processo, db
    )
    await db.commit()
    return {"numero_processo": case.numero_processo, "prazos": prazos}
