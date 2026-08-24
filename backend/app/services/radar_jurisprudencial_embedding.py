# ── app/services/radar_jurisprudencial_embedding.py ──────────────────────────
# Radar Jurisprudencial — Camada 2 (semântica) do PR 4 da série de
# consolidação do Banco de Teses Jurídicas.
#
# Embedding PRÉ-COMPUTADO por tese (coluna `Tese.embedding`, migração 149),
# não recalculado a cada rodada do radar: o texto da tese é majoritariamente
# estático, e recomputar N teses × M rodadas multiplicaria custo/latência à
# toa. O radar embeda só a DECISÃO nova (1 chamada por decisão) e compara
# contra os embeddings já calculados via pgvector, no mesmo padrão de
# `app/services/ai_service.py::buscar_contexto_rag` (SET LOCAL
# hnsw.ef_search, operador `<=>`, score = 1 - distância de cosseno).
#
# `gerar_embeddings` (embedding_service.py) NUNCA levanta exceção — é o
# fallback obrigatório deste módulo também: falha em gerar embedding nunca
# quebra a escrita da tese nem interrompe o radar; só significa que a tese
# fica fora da Camada 2 até a próxima tentativa bem-sucedida.
from __future__ import annotations

import logging

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tese import Tese
from app.services.embedding_service import gerar_embeddings

logger = logging.getLogger("ejc.radar_jurisprudencial")


def _texto_tese(tese: Tese) -> str:
    return " ".join(
        filter(None, [tese.titulo, tese.descricao, tese.fundamentacao, tese.jurisprudencia])
    )


async def atualizar_embedding_tese(db: AsyncSession, tese: Tese) -> None:
    """Recalcula `tese.embedding` a partir do texto relevante da tese.

    Não faz `db.commit()` — o chamador decide a transação (mesmo padrão do
    resto do repo para operações compostas). Falha ao gerar o vetor (provider
    indisponível, texto vazio) vira `embedding=None`, nunca uma exceção.
    """
    texto = _texto_tese(tese)
    if not texto.strip():
        tese.embedding = None
        return
    try:
        vetores = await gerar_embeddings([texto], modo="passage")
    except Exception as e:  # defensivo — gerar_embeddings já não deveria levantar
        logger.warning("Falha ao gerar embedding da tese %s: %s", tese.id, e)
        vetores = None
    tese.embedding = vetores[0] if vetores else None


async def atualizar_embedding_tese_job(tese_id: str) -> None:
    """Corpo de `BackgroundTasks`: recalcula e persiste o embedding de UMA
    tese pelo id, com sessão própria (a sessão do request já pode ter
    fechado quando o BackgroundTask roda). Nunca levanta — chamado a partir
    de `POST/PUT /teses` para não somar a latência de embedding ao request
    de escrita da tese."""
    from app.core.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            tese = (await db.execute(
                select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
            )).scalar_one_or_none()
            if tese is None:
                return
            await atualizar_embedding_tese(db, tese)
            await db.commit()
    except Exception as e:
        logger.warning("Job de embedding falhou para tese %s: %s", tese_id, e)


async def buscar_teses_similares(
    db: AsyncSession,
    texto_decisao: str,
    *,
    limite: int = 10,
    limiar: float = 0.75,
) -> list[dict]:
    """Teses cujo embedding é semanticamente próximo do texto da decisão.

    Score = 1 - distância de cosseno (mesmo cálculo de
    `ai_service.buscar_contexto_rag`). `limiar` é aplicado em Python, depois
    do `LIMIT` do SQL — o corte de candidatos que o pgvector varre não deve
    depender do piso semântico, só do teto de `limite`.

    Postgres-only (`<=>`, `hnsw.ef_search`) — falha (embeddings indisponíveis,
    índice ausente, erro de conexão) devolve lista vazia, nunca levanta: a
    Camada 2 é aditiva, uma falha aqui não deve derrubar o radar nem impedir
    a Camada 1 de gerar alerta.
    """
    if not texto_decisao or not texto_decisao.strip():
        return []
    try:
        vetores = await gerar_embeddings([texto_decisao], modo="query")
    except Exception as e:
        logger.warning("Falha ao gerar embedding da decisão para busca semântica: %s", e)
        return []
    if not vetores:
        return []
    vec = vetores[0]

    try:
        await db.execute(text("SET LOCAL hnsw.ef_search = 100"))
    except Exception:
        pass  # GUC ausente (índice não-HNSW/pgvector antigo) — segue igual

    sql = text("""
        SELECT id, titulo, area_juridica, (embedding <=> :vec) AS dist
        FROM teses
        WHERE embedding IS NOT NULL
          AND deleted_at IS NULL
          AND status_validacao IS DISTINCT FROM 'arquivada'
        ORDER BY embedding <=> :vec
        LIMIT :lim
    """)
    try:
        rows = await db.execute(sql, {"vec": str(vec), "lim": limite})
    except Exception as e:
        logger.warning("Busca semântica de teses falhou: %s", e)
        return []

    return [
        {"tese_id": r.id, "titulo": r.titulo, "area_juridica": r.area_juridica,
         "score_semantico": round(1 - r.dist, 4)}
        for r in rows
        if (1 - r.dist) >= limiar
    ]
