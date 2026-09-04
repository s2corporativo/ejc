"""Hardening transitório de acesso a LegalDoc de admissão (#1460).

O mesmo documento de procuração/contrato de admissão podia ser negado pela rota
`/clients/{id}/pecas-geradas` (advogado+) e lido por `/legal-docs/*` por papéis
com visão ampla de CRM. Como o conteúdo contém qualificação completa do cliente,
o piso conservador é advogado+ também nas leituras/mutações de LegalDoc marcado
com `client_admission_kind`.

O adapter preserva o nome/assinatura lógica da dependency existente e altera o
Dependant já compilado nas rotas do APIRouter. Deve ser removido quando a regra
for internalizada diretamente em `routers/legal_docs.py`.
"""
from __future__ import annotations

import functools
import logging

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ownership import cliente_id_visivel
from app.core.database import get_db
from app.core.security import get_current_user, requer_advogado
from app.models.legal_doc import LegalDoc
from app.models.user import User

logger = logging.getLogger("ejc.legal_doc.access_hardening")
_INSTALADO = False


async def _gate_admissao_advogado(
    request: Request,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
) -> None:
    """404 para ownership; advogado+ para conteúdo de peça de admissão."""
    doc_id = request.path_params.get("doc_id")
    if not doc_id:
        return

    row = (
        await db.execute(
            select(LegalDoc.client_id, LegalDoc.client_admission_kind).where(
                LegalDoc.id == doc_id,
                LegalDoc.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        return

    client_id, admission_kind = row
    if client_id and not await cliente_id_visivel(db, cu, client_id):
        raise HTTPException(status_code=404, detail="Peça não encontrada")

    if admission_kind:
        requer_advogado(
            cu,
            detail="Conteúdo de documento de admissão restrito à equipe jurídica",
        )


def _substituir_dependencia(dependant, original, novo) -> int:
    """Troca recursivamente a dependency sem relaxar as demais."""
    total = 0
    if dependant is None:
        return total
    for dep in getattr(dependant, "dependencies", ()) or ():
        if getattr(dep, "call", None) is original:
            dep.call = novo
            total += 1
        total += _substituir_dependencia(dep, original, novo)
    return total


def instalar() -> None:
    global _INSTALADO
    if _INSTALADO:
        return

    from app.routers import legal_docs

    if getattr(legal_docs.router, "_ejc_admission_access_installed", False):
        _INSTALADO = True
        return

    original = legal_docs._enforce_client_legal_doc_scope

    # Preserva o nome da dependency no OpenAPI/gates e a superfície esperada.
    @functools.wraps(original)
    async def gate_hardened(
        request: Request,
        db: AsyncSession = Depends(get_db),
        cu: User = Depends(get_current_user),
    ) -> None:
        await _gate_admissao_advogado(request, db, cu)

    substituicoes = 0
    for route in legal_docs.router.routes:
        substituicoes += _substituir_dependencia(
            getattr(route, "dependant", None), original, gate_hardened
        )

    # O APIRouter também preserva a lista de Depends para rotas registradas
    # posteriormente. Ajustá-la evita que uma rota futura volte ao gate antigo.
    for dep in getattr(legal_docs.router, "dependencies", ()) or ():
        if getattr(dep, "dependency", None) is original:
            dep.dependency = gate_hardened
            substituicoes += 1

    if substituicoes == 0:
        raise RuntimeError(
            "Dependency _enforce_client_legal_doc_scope não localizada para hardening"
        )

    legal_docs._enforce_client_legal_doc_scope = gate_hardened
    setattr(legal_docs.router, "_ejc_admission_access_installed", True)
    _INSTALADO = True
    logger.info(
        "Acesso a LegalDoc de admissão alinhado ao piso advogado+ (%s dependências)",
        substituicoes,
    )
