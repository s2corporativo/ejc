from __future__ import annotations

import asyncio
import csv
import os
from datetime import datetime

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.document_format import padronizar_documento_juridico


OUTPUT = os.getenv(
    "OUTPUT",
    f"/opt/ejc/reports/legal_docs_sanitization_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
)
LIMIT = int(os.getenv("LIMIT", "5000"))


def has_issue(value: str | None) -> bool:
    if not value:
        return False
    cleaned = padronizar_documento_juridico(value)
    return cleaned != value.strip()


async def main() -> None:
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT id, titulo, status, ai_generated, human_reviewed, conteudo
                    FROM legal_docs
                    WHERE deleted_at IS NULL
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": LIMIT},
            )
        ).mappings().all()

    total = 0
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id",
            "titulo_atual",
            "status",
            "ai_generated",
            "human_reviewed",
            "titulo_mudaria",
            "conteudo_mudaria",
            "preview_titulo_limpo",
            "preview_conteudo_inicio_limpo",
        ])
        for row in rows:
            titulo = row["titulo"] or ""
            conteudo = row["conteudo"] or ""
            titulo_limpo = padronizar_documento_juridico(titulo)
            conteudo_limpo = padronizar_documento_juridico(conteudo)
            titulo_mudaria = titulo_limpo != titulo.strip()
            conteudo_mudaria = conteudo_limpo != conteudo.strip()
            if not titulo_mudaria and not conteudo_mudaria:
                continue
            total += 1
            writer.writerow([
                row["id"],
                titulo,
                row["status"],
                row["ai_generated"],
                row["human_reviewed"],
                titulo_mudaria,
                conteudo_mudaria,
                titulo_limpo[:255],
                conteudo_limpo[:600],
            ])

    print(f"Documentos avaliados: {len(rows)}")
    print(f"Documentos com alteracao sugerida: {total}")
    print(f"Preview salvo em: {OUTPUT}")
    print("Nenhuma alteracao foi aplicada ao banco.")


if __name__ == "__main__":
    asyncio.run(main())
