# ── app/routers/infosimples_tjmg.py ──────────────────────────────────────────
# Caso de uso Infosimples #1 — consulta PAGA de processo no TJMG
# (caminho tribunal/tjmg/processo) com merge opcional na timeline do caso.
#
#   POST /infosimples/tjmg/processo — advogado+ (require_roles), rate limit
#        10/min por usuário. Body: case_id OU numero_processo (CNJ, 20 díg.).
#        Com case_id, os movimentos NOVOS entram em case_movimentos pela MESMA
#        chave de dedup do DataJud ([dj:hash16] — reuso de
#        datajud_service.upsert_movimentos_no_caso; nunca duplica timeline).
#   GET  /infosimples/status — booleans + contador do teto diário, sem token.
#
# CUSTO: cada consulta executada é COBRADA — gates de flag/teto/cache ficam no
# infosimples_service. LGPD: número de processo é público; token nunca vaza.
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, require_roles
from app.models.audit_log import criar_audit_log
from app.models.user import User
from app.services import datajud_service, infosimples_service

logger = logging.getLogger("ejc.infosimples")

router = APIRouter(prefix="/infosimples", tags=["Infosimples (consultas pagas)"])

# advogado+ = advogado, socio, admin, superadmin (hierarquia ROLE_LEVEL).
_ADVOGADO_MAIS = require_roles(["advogado"])


class TJMGProcessoIn(BaseModel):
    """Consulta de processo TJMG — informe case_id OU numero_processo.

    • case_id: usa o numero_processo do caso e faz MERGE dos movimentos
      novos na timeline (case_movimentos), dedup compartilhada com o DataJud.
    • numero_processo: consulta avulsa (sem merge), número CNJ com ou sem
      máscara (NNNNNNN-DD.AAAA.J.TR.OOOO — 20 dígitos).
    """
    case_id: str | None = Field(default=None, description="ID do caso no EJC")
    numero_processo: str | None = Field(
        default=None, description="Número CNJ (20 dígitos, com ou sem máscara)"
    )

    @model_validator(mode="after")
    def _valida(self):
        if not self.case_id and not self.numero_processo:
            raise ValueError("Informe case_id ou numero_processo.")
        if self.numero_processo:
            digitos = re.sub(r"\D", "", self.numero_processo)
            if len(digitos) != 20:
                raise ValueError(
                    "numero_processo inválido: o número CNJ tem 20 dígitos "
                    "(formato NNNNNNN-DD.AAAA.J.TR.OOOO)."
                )
        return self


@router.get("/status")
async def status_infosimples(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Status da integração Infosimples — booleans e teto diário, sem token."""
    return await infosimples_service.status(db)


@router.post(
    "/tjmg/processo",
    dependencies=[Depends(rate_limit("infosimples_tjmg", 10))],
)
async def consultar_processo_tjmg(
    body: TJMGProcessoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_ADVOGADO_MAIS),
):
    """Consulta PAGA do processo no TJMG via Infosimples (+ merge no caso).

    Retorna dados normalizados (classe, assunto, partes, valor, situação,
    movimentos) e, quando case_id é fornecido, quantos movimentos NOVOS
    entraram na timeline (movimentos_novos). Cache do dia: repetir a mesma
    consulta hoje não gera nova cobrança ("cache": true).
    """
    case = None
    numero = (body.numero_processo or "").strip()
    if body.case_id:
        case = await verificar_acesso_caso(db, cu, body.case_id)
        numero = numero or (case.numero_processo or "").strip()
    if not numero or len(re.sub(r"\D", "", numero)) != 20:
        raise HTTPException(
            status_code=422,
            detail=(
                "Caso sem número de processo CNJ válido (20 dígitos). "
                "Preencha numero_processo no caso ou informe-o no body."
            ),
        )

    try:
        resultado = await infosimples_service.consultar(
            db, "tribunal/tjmg/processo",
            {"numero_processo": re.sub(r"\D", "", numero)},
            user_id=cu.id, user_role=getattr(cu.role, "value", str(cu.role)),
        )
    except (
        infosimples_service.IntegracaoDesligadaError,
        infosimples_service.LimiteDiarioAtingidoError,
        infosimples_service.InfosimplesConsultaError,
        infosimples_service.InfosimplesIndisponivelError,
    ) as e:
        status_code, detail = infosimples_service.http_status_para_erro(e)
        raise HTTPException(status_code=status_code, detail=detail)

    dados = resultado.get("data") or []
    if not dados:
        raise HTTPException(
            status_code=404,
            detail="Processo não localizado no TJMG pela Infosimples.",
        )
    processo = infosimples_service.normalizar_processo_tjmg(dados[0])

    movimentos_novos = 0
    if case is not None and processo["movimentos"]:
        # REUSO da dedup do DataJud: mesma chave [dj:hash16] → um movimento já
        # importado pelo DataJud (ou por consulta anterior) nunca duplica.
        movimentos_novos, _total = await datajud_service.upsert_movimentos_no_caso(
            db, case, processo["movimentos"]
        )
        await criar_audit_log(
            db, cu.id, getattr(cu.role, "value", str(cu.role)),
            "SYNC", "case_movimentos", case.id,
            dados_depois={
                "origem": "infosimples_tjmg",
                "novos": movimentos_novos,
                "total": len(processo["movimentos"]),
            },
        )
        await db.commit()

    return {
        **processo,
        "numero_processo": processo.get("numero_processo") or numero,
        "case_id": case.id if case is not None else None,
        "movimentos_novos": movimentos_novos,
        "cache": bool(resultado.get("cache")),
        "site_receipts": resultado.get("site_receipts") or [],
    }
