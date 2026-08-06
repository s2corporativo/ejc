# ── app/routers/radar_legislativo.py ─────────────────────────────────────────
# Radar Legislativo (Câmara + Senado + ALMG) — consulta ao vivo + histórico do
# que o job diário já viu (tabela radar_legislativo_visto). O feed AGREGADO
# continua no Radar Regulatório (/regulatorio/digest-semanal), que recebe
# os alertas criados pelo job em diario_oficial_alertas.
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import require_roles
from app.models.user import User
from app.services import radar_legislativo as svc

router = APIRouter(prefix="/radar-legislativo", tags=["Radar Legislativo"])


@router.get(
    "/proposicoes",
    dependencies=[Depends(rate_limit("radar-legislativo-proposicoes", 20))],
)
async def proposicoes(
    fonte: str | None = Query(None, pattern="^(camara|senado|almg)$"),
    termo: str | None = Query(None, min_length=3, max_length=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["advogado"])),  # advogado+ (hierarquia)
):
    """Proposições legislativas monitoradas.

    - `termo` informado → busca AO VIVO nas fontes (todas ou a de `fonte`),
      com timeouts calibrados por fonte (Câmara 30s, ALMG 45s) e degradação:
      fonte fora do ar entra em `fontes_com_falha`, nunca derruba a resposta.
    - Sempre retorna também o `historico` persistido pelo job diário.
    """
    fontes = (fonte,) if fonte else svc.FONTES
    ao_vivo: list[dict] = []
    falhas: list[str] = []
    if termo:
        ao_vivo, falhas = await svc.buscar_ao_vivo(termo, fontes)
    historico = await svc.historico_visto(db, fonte=fonte, termo=termo)
    return {
        "fonte": fonte,
        "termo": termo,
        "ao_vivo": ao_vivo,
        "fontes_com_falha": falhas,
        "historico": historico,
    }
