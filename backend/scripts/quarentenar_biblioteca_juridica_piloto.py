#!/usr/bin/env python3
"""Coloca o lote piloto da Biblioteca Jurídica em quarentena no banco do EJC.

Motivo: auditoria de 14/08/2026 encontrou ao menos um registro anteriormente
classificado como oficial/ALTA contendo referência simulada e metadados jurídicos
incorretos. Corrigir o arquivo-fonte não neutraliza uma versão já aprovada no
PostgreSQL; este script rebaixa os registros do lote para revisão humana.

Dry-run por padrão. Use ``--execute`` para persistir. Não apaga documento, chunk,
embedding nem histórico e não altera documentos fora dos canonical_ids listados.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone


CANONICAL_IDS = (
    "TESE-TRIB-000001", "JUR-TRIB-000002", "JUR-TRIB-000003", "JUR-TRIB-000004",
    "JUR-TRIB-000005", "JUR-TRIB-000006", "TESE-AMBI-000007", "TESE-AMBI-000008",
    "TESE-ADMI-000009", "JUR-ADMI-000010", "TESE-LICI-000011", "TESE-LICI-000012",
    "TESE-LICI-000013", "TESE-EMPR-000014", "JUR-EMPR-000015", "JUR-CONS-000016",
    "JUR-CONS-000017", "JUR-CONS-000018", "JUR-CONS-000019", "JUR-TRAB-000020",
    "TESE-TRAB-000021", "TESE-PROC-000022", "TESE-PROC-000023", "JUR-PROC-000024",
)
MOTIVO = (
    "Quarentena preventiva da Biblioteca Jurídica: auditoria de 14/08/2026 "
    "revogou a homologação do lote piloto e exige revalidação individual de proveniência."
)


def aplicar_quarentena_extra(extra: dict | None, *, quando: str) -> tuple[dict, bool]:
    """Transformação pura e idempotente do JSONB de governança."""
    anterior = dict(extra or {})
    novo = dict(anterior)
    # Uma recusa humana é mais restritiva e nunca deve ser rebaixada para pendente.
    if str(anterior.get("rag_status") or "").lower() != "recusado":
        novo["rag_status"] = "pendente"
    novo["requires_human_review"] = True
    novo["human_reviewed"] = False
    novo["quarantine_active"] = True
    novo["quarantine_reason"] = MOTIVO
    novo["quarantined_at"] = quando
    novo["quarantined_by"] = "quarentenar_biblioteca_juridica_piloto.py"
    return novo, novo != anterior


def _bootstrap_backend() -> None:
    candidatos = [
        "/app",
        "/opt/ejc/backend",
        "/home/ubuntu/ejc/backend",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ]
    for c in candidatos:
        if os.path.isdir(os.path.join(c, "app")):
            if c not in sys.path:
                sys.path.insert(0, c)
            return


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="Persiste a quarentena no PostgreSQL")
    args = ap.parse_args()
    _bootstrap_backend()

    import asyncio
    from sqlalchemy import or_, select
    from app.core.database import AsyncSessionLocal
    from app.models.rag import KnowledgeDoc

    async def run() -> tuple[int, int, list[str]]:
        encontrados = alterados = 0
        ids: list[str] = []
        agora = datetime.now(timezone.utc).isoformat()
        async with AsyncSessionLocal() as db:
            q = select(KnowledgeDoc).where(
                KnowledgeDoc.deleted_at.is_(None),
                or_(
                    KnowledgeDoc.chave_origem.in_(CANONICAL_IDS),
                    KnowledgeDoc.extra["canonical_id"].astext.in_(CANONICAL_IDS),
                ),
            )
            docs = (await db.execute(q)).scalars().all()
            encontrados = len(docs)
            for doc in docs:
                canonical = str((doc.extra or {}).get("canonical_id") or doc.chave_origem or doc.id)
                ids.append(canonical)
                novo, mudou = aplicar_quarentena_extra(doc.extra, quando=agora)
                if mudou:
                    alterados += 1
                    if args.execute:
                        doc.extra = novo
            if args.execute:
                await db.commit()
            else:
                await db.rollback()
        return encontrados, alterados, sorted(ids)

    encontrados, alterados, ids = asyncio.run(run())
    modo = "EXECUTADO" if args.execute else "DRY-RUN"
    print(f"[{modo}] registros encontrados={encontrados} | que mudariam/mudaram={alterados}")
    for canonical in ids:
        print(f"  - {canonical}")
    faltantes = sorted(set(CANONICAL_IDS) - set(ids))
    if faltantes:
        print(f"[INFO] {len(faltantes)} canonical_id(s) não estão atualmente no banco.")
    if not args.execute:
        print("Nenhuma alteração foi persistida. Execute novamente com --execute para aplicar.")


if __name__ == "__main__":
    main()
