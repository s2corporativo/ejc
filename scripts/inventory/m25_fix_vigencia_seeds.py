"""M25 — auditoria somente leitura dos seeds legislativos do Planalto.

Este utilitário histórico não pode promover `legal_status='vigente'` apenas
porque o documento foi obtido de fonte oficial. Fonte oficial comprova
proveniência/autenticidade do texto consultado; vigência exige conferência
jurídica própria, auditável e sujeita à política canônica de curadoria do RAG.

Regras desta versão:
- não executa UPDATE, INSERT, DELETE nem backfill;
- limita-se à base RAG pública/global (`client_id`/`case_id` nulos);
- não imprime conteúdo documental, URL completa, PII ou segredo;
- inclui versão/flag vigente para distinguir histórico da versão ativa;
- normaliza a origem da vigência para categoria, sem expor ID do curador;
- usa a mesma semântica do gate RAG para o marcador efetivo de inferência;
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
        versao,
        vigente,
        COALESCE(extra->>'legal_status', '') AS legal_status,
        CASE
            WHEN COALESCE(extra->>'legal_status_origem', '') LIKE 'curadoria:%'
                THEN 'curadoria'
            ELSE COALESCE(extra->>'legal_status_origem', '')
        END AS legal_status_origem_categoria,
        COALESCE(extra->>'legal_status_verificado_em', '') AS legal_status_verificado_em,
        (
            NULLIF(btrim(COALESCE(extra->>'legal_status_inferido_em', '')), '')
            IS NOT NULL
        ) AS possui_marcador_inferencia,
        revisado,
        revisado_em
    FROM knowledge_docs
    WHERE chave_origem = ANY(:slugs)
      AND client_id IS NULL
      AND case_id IS NULL
      AND base_rag = 'publica'
      AND deleted_at IS NULL
    ORDER BY chave_origem, versao DESC
    """
)


async def auditar() -> list[dict[str, object]]:
    """Lê somente metadados públicos necessários à conferência de vigência."""
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
                "versao": row["versao"],
                "vigente": row["vigente"],
                "legal_status": row["legal_status"],
                "legal_status_origem_categoria": row[
                    "legal_status_origem_categoria"
                ],
                "possui_verificacao": bool(row["legal_status_verificado_em"]),
                "possui_marcador_inferencia": row["possui_marcador_inferencia"],
                "revisado": row["revisado"],
                "possui_data_revisao": row["revisado_em"] is not None,
            }
        )
    print("total:", len(rows))


if __name__ == "__main__":
    asyncio.run(main())
