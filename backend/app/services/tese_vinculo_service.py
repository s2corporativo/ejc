# ── app/services/tese_vinculo_service.py ─────────────────────────────────────
# Write-path ÚNICO do vínculo tese <-> caso (Classe A do plano-mestre de
# padronização, Issue #1272). tese_caso_links é a fonte única do vínculo e,
# desde a consolidação jurimétrica de 21/09/2026, também a fonte canônica das
# métricas de desempenho da tese.
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import case as sa_case
from sqlalchemy import func, select

from app.models.tese import Tese, TeseCasoLink


RESULTADOS_TESE = frozenset({"procedente", "improcedente", "acordo", "pendente"})


def normalizar_resultado_tese(resultado: str | None) -> str:
    """Novos vínculos sem desfecho nascem explicitamente como pendentes."""
    r = (resultado or "pendente").strip().lower()
    if r not in RESULTADOS_TESE:
        raise ValueError(
            "resultado de tese deve ser procedente, improcedente, acordo ou pendente"
        )
    return r


async def reconciliar_metricas_tese(db, tese_id: str) -> Tese | None:
    """Recalcula agregados da tese a partir de tese_caso_links.

    A taxa judicial usa apenas procedente+improcedente. Acordo e pendente
    permanecem no total de vínculos, mas não contaminam o denominador.
    """
    await db.flush()
    row = (
        await db.execute(
            select(
                func.count(TeseCasoLink.id).label("total"),
                func.count(
                    sa_case((TeseCasoLink.resultado == "procedente", 1))
                ).label("venceu"),
                func.count(
                    sa_case((TeseCasoLink.resultado == "improcedente", 1))
                ).label("perdeu"),
            ).where(TeseCasoLink.tese_id == tese_id)
        )
    ).one()
    tese = (
        await db.execute(
            select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if tese is None:
        return None

    total = int(row.total or 0)
    venceu = int(row.venceu or 0)
    perdeu = int(row.perdeu or 0)
    decididos = venceu + perdeu
    tese.vezes_usada = total
    tese.vezes_venceu = venceu
    tese.vezes_perdeu = perdeu
    tese.taxa_sucesso = round(venceu / decididos, 4) if decididos else None
    return tese


async def vincular_tese_ao_caso(
    db,
    *,
    tese_id: str,
    case_id: str,
    resultado: str | None = None,
    observacao: str | None = None,
    created_by: str | None = None,
) -> TeseCasoLink:
    """Cria o vínculo e reconcilia os agregados da tese sem commit.

    Não é idempotente; os chamadores continuam responsáveis por impedir
    duplicidade de vínculo quando a regra de negócio assim exigir.
    """
    resultado_normalizado = normalizar_resultado_tese(resultado)
    link = TeseCasoLink(
        id=str(uuid4()),
        tese_id=tese_id,
        case_id=case_id,
        resultado=resultado_normalizado,
        observacao=observacao,
        created_by=created_by,
    )
    db.add(link)
    await reconciliar_metricas_tese(db, tese_id)
    return link


async def atualizar_resultado_vinculo(
    db,
    *,
    link: TeseCasoLink,
    resultado: str,
) -> TeseCasoLink:
    """Atualiza um desfecho e reconcilia a tese na mesma transação."""
    link.resultado = normalizar_resultado_tese(resultado)
    await reconciliar_metricas_tese(db, link.tese_id)
    return link
