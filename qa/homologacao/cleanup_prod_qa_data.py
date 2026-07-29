#!/usr/bin/env python3
"""Soft-delete estritamente a massa criada por uma rodada de homologação.

Exige marcadores completos (mín. 18 caracteres e prefixo HOMOLOG-FICTICIO). Não
remove AuditLog/AILog, preservando a trilha. Nunca toca registros sem o marcador.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

# O workflow copia este arquivo para /tmp; o pacote da aplicação vive em /app.
sys.path.insert(0, "/app")

from sqlalchemy import or_, select

from app.core.database import AsyncSessionLocal
from app.models.case import Case
from app.models.client import Client
from app.models.document import Document
from app.models.legal_doc import LegalDoc


def marcadores() -> list[str]:
    valores = [x.strip() for x in os.getenv("EJC_QA_MARKERS", "").split(",") if x.strip()]
    if not valores:
        raise SystemExit("EJC_QA_MARKERS ausente")
    for valor in valores:
        if not valor.startswith("HOMOLOG-FICTICIO") or len(valor) < 18:
            raise SystemExit(f"Marcador recusado pela barreira: {valor!r}")
    return valores


async def main() -> None:
    marks = marcadores()
    agora = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        cond_case = or_(*[
            or_(Case.titulo.ilike(f"%{m}%"), Case.descricao_fatos.ilike(f"%{m}%"))
            for m in marks
        ])
        cases = (await db.execute(select(Case).where(Case.deleted_at.is_(None), cond_case))).scalars().all()
        case_ids = [c.id for c in cases]

        cond_doc = or_(*[Document.titulo.ilike(f"%{m}%") for m in marks])
        docs_q = select(Document).where(Document.deleted_at.is_(None), cond_doc)
        if case_ids:
            docs_q = select(Document).where(
                Document.deleted_at.is_(None),
                or_(cond_doc, Document.case_id.in_(case_ids)),
            )
        docs = (await db.execute(docs_q)).scalars().all()

        cond_legal = or_(*[LegalDoc.titulo.ilike(f"%{m}%") for m in marks])
        legal_q = select(LegalDoc).where(LegalDoc.deleted_at.is_(None), cond_legal)
        if case_ids:
            legal_q = select(LegalDoc).where(
                LegalDoc.deleted_at.is_(None),
                or_(cond_legal, LegalDoc.case_id.in_(case_ids)),
            )
        legal_docs = (await db.execute(legal_q)).scalars().all()

        client_ids = {c.client_id for c in cases if c.client_id}
        cond_client = or_(*[
            or_(Client.nome.ilike(f"%{m}%"), Client.observacoes.ilike(f"%{m}%"))
            for m in marks
        ])
        clients_q = select(Client).where(Client.deleted_at.is_(None), cond_client)
        if client_ids:
            clients_q = select(Client).where(
                Client.deleted_at.is_(None),
                or_(cond_client, Client.id.in_(client_ids)),
            )
        clients = (await db.execute(clients_q)).scalars().all()

        for row in legal_docs:
            row.deleted_at = agora
        for row in docs:
            row.deleted_at = agora
        for row in cases:
            row.deleted_at = agora
        for row in clients:
            row.deleted_at = agora
        await db.commit()
        print(
            "QA_DATA_SOFT_DELETED "
            f"cases={len(cases)} clients={len(clients)} documents={len(docs)} legal_docs={len(legal_docs)}"
        )


if __name__ == "__main__":
    asyncio.run(main())
