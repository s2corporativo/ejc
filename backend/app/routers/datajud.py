"""DataJud CNJ public API endpoints."""
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, require_roles
from app.models.case import Case
from app.services import datajud_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/datajud", tags=["datajud"])

# [B4] Proxy de consulta CNJ arbitrária → piso advogado+.
_ADVOGADO_MAIS = require_roles(["advogado"])


def _prazos_datajud_bloqueados() -> dict[str, object]:
    """Contrato transitório enquanto o motor auditável de prazos não é canônico.

    DataJud pode alimentar movimentações e contexto processual, mas não deve
    materializar prazo fatal a partir da data genérica de movimento. Mantemos o
    campo ``prazos`` na resposta do sync por compatibilidade, explicitando que a
    criação automática está suspensa até candidato + cálculo + HITL.
    """
    return {
        "criados": 0,
        "ignorados": 0,
        "bloqueado": True,
        "motivo": "prazo_datajud_requer_motor_canonico_e_hitl",
    }


@router.get(
    "/process/{numero_cnj}",
    dependencies=[Depends(rate_limit("datajud_process", 20))],
)
async def lookup_process(
    numero_cnj: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(_ADVOGADO_MAIS),
):
    """Busca processo pelo número CNJ."""
    del db, current_user
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
    """Sincroniza somente movimentações/contexto de um caso com o DataJud.

    A sincronização automática de prazos foi retirada deste fluxo. O contrato
    ainda devolve ``prazos`` com estado bloqueado para que consumidores atuais
    não precisem inferir ausência do campo como sucesso.
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
    try:
        synced = await datajud_service.sincronizar_caso(db, case)
        await db.commit()
        return {
            "synced": synced,
            "numero_processo": case.numero_processo,
            "prazos": _prazos_datajud_bloqueados(),
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
    """Compatibilidade: endpoint preservado, mas materialização está bloqueada.

    O acesso ao caso é validado antes da resposta para não transformar esta rota
    em oráculo de existência. O retorno 409 é deliberado: o cliente precisa
    tratar o estado como operação indisponível, nunca como sincronização vazia
    bem-sucedida.
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
    raise HTTPException(
        status_code=409,
        detail=(
            "Sincronização automática de prazos via DataJud suspensa: "
            "o prazo precisa passar pelo motor canônico de cálculo e revisão humana."
        ),
    )
