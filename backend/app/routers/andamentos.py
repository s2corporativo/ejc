# ── app/routers/andamentos.py ─────────────────────────────────────────────────
# Etapa 13 (Gestão Inteligente) — andamentos oficiais do caso via API Pública
# do DataJud/CNJ (contrato documentado em services/datajud_service.py).
#
#   POST /casos/{case_id}/andamentos/sincronizar — consulta o DataJud pelo
#        número CNJ do caso e faz upsert idempotente em case_movimentos.
#        Ownership (verificar_acesso_caso) + rate limit 5/min por usuário.
#   GET  /casos/{case_id}/andamentos/status — booleans de habilitação/config
#        (sem segredos) + alias do tribunal derivado do número CNJ do caso.
#
# Integração externa é OPT-IN: com DATAJUD_ENABLED=false o sync responde 503
# claro (não é erro do usuário). LGPD: dados do DataJud são públicos, mas o
# corpo da resposta nunca é logado e a chave nunca aparece em log/erro.
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.user import User
from app.services import datajud_service

logger = logging.getLogger("ejc.andamentos")

router = APIRouter(prefix="/casos", tags=["Andamentos (DataJud)"])


@router.get("/{case_id}/andamentos/status")
async def status_andamentos(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Status da integração DataJud para o caso — booleans, sem segredos."""
    case = await verificar_acesso_caso(db, cu, case_id)
    s = get_settings()
    numero = (case.numero_processo or "").strip()
    return {
        "enabled": bool(s.DATAJUD_ENABLED),
        "configured": bool(s.DATAJUD_API_KEY),
        "numero_processo": numero or None,
        "tribunal_alias": datajud_service.alias_do_numero(numero) if numero else None,
    }


@router.post(
    "/{case_id}/andamentos/sincronizar",
    dependencies=[Depends(rate_limit("andamentos_sincronizar", 5))],
)
async def sincronizar_andamentos(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Consulta o DataJud pelo número CNJ do caso e importa movimentos novos.

    Upsert idempotente (dedup por hash data|descricao — reexecutar não
    duplica). Retorna {"novos": inseridos, "total": movimentos_recebidos}.
    """
    s = get_settings()
    if not s.DATAJUD_ENABLED:
        raise HTTPException(
            status_code=503,
            detail=(
                "Integração com o DataJud está desativada neste ambiente "
                "(DATAJUD_ENABLED=false). Peça ao administrador para habilitar "
                "no .env antes de sincronizar andamentos."
            ),
        )
    if not s.DATAJUD_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "Integração DataJud sem chave configurada (DATAJUD_API_KEY). "
                "O CNJ divulga a chave pública em datajud-wiki.cnj.jus.br."
            ),
        )

    case = await verificar_acesso_caso(db, cu, case_id)
    numero = (case.numero_processo or "").strip()
    if not numero:
        raise HTTPException(
            status_code=422,
            detail=(
                "Caso sem número de processo (CNJ). Preencha numero_processo "
                "no caso antes de sincronizar andamentos."
            ),
        )

    try:
        movimentos = await datajud_service.consultar_movimentos(numero)
    except datajud_service.TribunalNaoMapeadoError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except datajud_service.DataJudDesabilitadoError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except (httpx.HTTPError, ValueError) as e:
        # Erro curto, sem corpo de resposta e sem chave (LGPD/higiene de log).
        logger.warning(
            "[andamentos] DataJud indisponível p/ caso %s: %s",
            case_id, type(e).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="Falha ao consultar o DataJud. Tente novamente em instantes.",
        )

    novos, total = await datajud_service.upsert_movimentos_no_caso(db, case, movimentos)
    await criar_audit_log(
        db, cu.id, cu.role.value, "SYNC", "case_movimentos", case_id,
        dados_depois={"origem": "datajud", "novos": novos, "total": total},
    )
    await db.commit()
    return {"novos": novos, "total": total}
