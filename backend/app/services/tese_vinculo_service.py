# ── app/services/tese_vinculo_service.py ─────────────────────────────────────
# Write-path ÚNICO do vínculo tese <-> caso (Classe A do plano-mestre de
# padronização, Issue #1272). Antes desta extração, `POST
# /teses/{id}/vincular-caso` (routers/teses.py) e a aprovação de
# ThesisCandidate na matriz (services/matriz_teses_service.py) tinham dois
# caminhos disjuntos para o mesmo fato — o segundo nunca existia, é a lacuna
# que este módulo fecha. `tese_caso_links` é a fonte única do vínculo
# (decisão D1 da pauta do titular, docs/PAUTA_DECISOES_TITULAR.md).
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from app.models.tese import Tese, TeseCasoLink


async def vincular_tese_ao_caso(
    db,
    *,
    tese_id: str,
    case_id: str,
    resultado: str | None = None,
    observacao: str | None = None,
    created_by: str | None = None,
) -> TeseCasoLink:
    """Cria o vínculo em `tese_caso_links` e atualiza os contadores de
    desempenho da tese (`vezes_usada`/`vezes_venceu`/`vezes_perdeu`/
    `taxa_sucesso`). Não commita -- o chamador decide a transação.

    Não é idempotente (mesmo comportamento do endpoint que substitui):
    chamar duas vezes para o mesmo par tese/caso cria dois vínculos. Cada
    chamador já garante que só chama uma vez (o endpoint por ação explícita
    do advogado; `aprovar_tese` porque `ThesisCandidate` só aprova uma vez —
    409 em decisão repetida).
    """
    link = TeseCasoLink(
        id=str(uuid4()), tese_id=tese_id, case_id=case_id,
        resultado=resultado, observacao=observacao, created_by=created_by,
    )
    db.add(link)

    t = (await db.execute(
        select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
    )).scalar_one_or_none()
    if t is not None:
        t.vezes_usada = (t.vezes_usada or 0) + 1
        if resultado == "procedente":
            t.vezes_venceu = (t.vezes_venceu or 0) + 1
        elif resultado == "improcedente":
            t.vezes_perdeu = (t.vezes_perdeu or 0) + 1
        t.taxa_sucesso = (
            round((t.vezes_venceu or 0) / t.vezes_usada, 4)
            if t.vezes_usada else None
        )

    return link
