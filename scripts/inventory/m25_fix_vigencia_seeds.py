"""M25 — auditoria somente leitura dos seeds legislativos do Planalto.

HISTÓRICO
O script original alterava diretamente `knowledge_docs.extra` para declarar
`planalto:cpc` e `planalto:cf88` como `legal_status='vigente'` apenas porque o
conteúdo vinha do texto compilado oficial do Planalto. Esse comportamento foi
retirado: fonte oficial comprova proveniência/autenticidade do texto consultado,
mas não substitui uma conferência jurídica individual e auditável de vigência.

POLÍTICA ATUAL
- este utilitário NÃO executa UPDATE, INSERT, DELETE nem backfill;
- lista somente metadados operacionais necessários à conferência;
- não imprime conteúdo, URL completa, PII ou segredo;
- qualquer promoção de `legal_status` deve ocorrer pelo fluxo canônico de
  curadoria RAG, com ator autorizado e trilha de auditoria;
- proposição legislativa e texto oficial sem vigência conferida permanecem fora
  da fundamentação de direito atual quando o gate estrito estiver habilitado.

Uso: execução manual, somente para diagnóstico controlado.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core.database import AsyncSessionLocal

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
    """Retorna metadados de vigência dos seeds sem modificar o banco."""
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(_SQL_AUDITORIA, {"slugs": list(SLUGS)})).mappings().all()
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
