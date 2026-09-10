"""M25 — auditoria somente leitura dos seeds legislativos do Planalto.

Este utilitário histórico não pode promover `legal_status='vigente'` apenas
porque o documento foi obtido de fonte oficial. Fonte oficial comprova
proveniência/autenticidade do texto consultado; vigência exige conferência
jurídica própria, auditável e sujeita à política canônica de curadoria do RAG.

Regras desta versão:
- não executa UPDATE, INSERT, DELETE nem backfill;
- não imprime conteúdo documental, URL completa, PII ou segredo;
- apenas lista metadados de vigência/revisão dos seeds selecionados;
- qualquer promoção futura de status deve ocorrer pelo fluxo canônico, com ator
  autorizado e trilha de auditoria.

Uso manual seguro:
    python scripts/inventory/m25_fix_vigencia_seeds.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _REPO_ROOT / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.database import AsyncSessionLocal  # noqa: E402

SLUGS = ("planalto:cpc", "planalto:cf88")

_SQL_AUDITORIA = text(
    """
    SELECT
        chave_origem,
        COALESCE(extra->>'legal_status', '') AS legal_status,
        COALESCE(extra->>'legal_status_origem', '') AS legal_status_origem,
        COALESCE(extra->>'legal_status_verificado_em', '') AS legal_status_verificado_em,
        (extra ? 'legal_status_inferido_em') AS possui_marcador_inferencia,
        revisado,
        revisado_em
    FROM knowledge_docs
    WHERE chave_origem = ANY(:slugs)
      AND deleted_at IS NULL
    ORDER BY chave_origem, versao DESC
    """
)


async def auditar() -> list[dict[str, object]]:
    """Lê somente metadados necessários à conferência de vigência."""
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(_SQL_AUDITORIA, {"slugs": list(SLUGS)})
        ).mappings().all()
        return [dict(row) for row in rows]


async def main() -> None:
    rows = await auditar()
    for row in rows:
        print(
            {
                "chave_origem": row["chave_origem"],
                "legal_status": row["legal_status"],
                "legal_status_origem": row["legal_status_origem"],
                "possui_verificacao": bool(row["legal_status_verificado_em"]),
                "possui_marcador_inferencia": row["possui_marcador_inferencia"],
                "revisado": row["revisado"],
                "possui_data_revisao": row["revisado_em"] is not None,
            }
        )
    print("total:", len(rows))


if __name__ == "__main__":
    asyncio.run(main())
