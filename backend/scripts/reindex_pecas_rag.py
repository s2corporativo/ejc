# scripts/reindex_pecas_rag.py
# Re-indexa TODAS as peças jurídicas ativas no RAG, aplicando retroativamente:
#   - mascaramento de PII (nomes do cliente + parte contrária) antes de vetorizar
#   - escopo de isolamento (client_id/case_id) gravado em knowledge_docs
#
# Seguro/idempotente: indexar_peca_rag faz upsert por chave_origem=legaldoc:{id}
# (atualiza o doc existente, troca os chunks). Não cria duplicatas.
#
# Uso (dentro do container backend):
#   docker compose exec -T backend python scripts/reindex_pecas_rag.py
#
# LGPD/EOAB: corrige peças já vetorizadas que ainda continham nomes identificáveis
# na base GLOBAL (laudo RAG-02) e que ficavam fora do escopo do dono.
import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.legal_doc import LegalDoc
from app.services.case_intel import indexar_peca_rag


async def main() -> None:
    async with AsyncSessionLocal() as db:
        ids = (await db.execute(
            select(LegalDoc.id).where(LegalDoc.deleted_at.is_(None))
        )).scalars().all()

    total = len(ids)
    print(f"[reindex] {total} peça(s) ativa(s) para re-indexar.")
    if total == 0:
        print("[reindex] nada a fazer.")
        return

    ok = 0
    erros = 0
    for i, did in enumerate(ids, 1):
        try:
            await indexar_peca_rag(did)
            ok += 1
            print(f"[reindex] {i}/{total} OK   {did}")
        except Exception as e:  # noqa: BLE001 — log e segue (não aborta o lote)
            erros += 1
            print(f"[reindex] {i}/{total} ERRO {did}: {str(e)[:160]}")

    print(f"[reindex] concluído: {ok} ok, {erros} erro(s) de {total}.")


if __name__ == "__main__":
    asyncio.run(main())
