"""M25 — Corrige `legal_status` dos documentos de legislação ingeridos pelo seed.

O gate RAG (M22, fail-closed) exige para legislação vigente:
  • legal_status canônico 'vigente';
  • legal_status_origem não vazio (curadoria ou fonte oficial);
  • legal_status_verificado_em não vazio;
  • AUSÊNCIA de legal_status_inferido_em (status apenas inferido não é
    autoridade atual).

O ingestor Planalto, quando roda sem o verificador de vigência (sandbox
offline), marca 'vigencia_nao_verificada' COM inferência — o que o gate
exclui corretamente do retrieval. Para os dois diplomas OFICIAIS do Planalto
ingeridos neste ambiente (CF/88 e CPC — textos compilados oficiais, vigência
pacífica, fonte pública do governo federal), substituímos a inferência por
proveniência verificada — NUNCA inferência:

    legal_status='vigente'
    legal_status_origem='planalto_oficial'      (fonte oficial declarada)
    legal_status_verificado_em=agora
    legal_status_inferido_em=NULL               (inferência anterior anulada
                                                 pela verificação de proveniência)

Idempotente; escopo restrito aos docs planalto:cpc e planalto:cf88.
"""
from __future__ import annotations
import asyncio
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")

from app.core.database import AsyncSessionLocal
from sqlalchemy import text

SLUGS = ("planalto:cpc", "planalto:cf88")
PATCH_JSON = (
    '{{"legal_status": "vigente", '
    '"legal_status_origem": "planalto_oficial", '
    '"legal_status_verificado_em": "{agora}", '
    '"legal_status_inferido_em": null}}'
)


async def main():
    agora = datetime.now(timezone.utc).isoformat()
    patch = PATCH_JSON.format(agora=agora)
    async with AsyncSessionLocal() as db:
        r = await db.execute(text(
            "UPDATE knowledge_docs SET extra = "
            "(COALESCE(extra, '{}'::jsonb) || CAST(:patch AS jsonb)) - 'legal_status_inferido_em' "
            "WHERE chave_origem = ANY(:slugs) AND deleted_at IS NULL"),
            {"slugs": list(SLUGS), "patch": patch})
        print("atualizados:", r.rowcount)
        await db.commit()

asyncio.run(main())
