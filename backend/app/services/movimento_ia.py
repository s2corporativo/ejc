"""
movimento_ia.py — Tradução de andamentos processuais para linguagem simples (IA).

Pega a descrição técnica de um CaseMovimento (ex.: "Conclusos para decisão") e
gera um resumo curto e claro, que o cliente entende. REUSA o ai_gateway
(Anthropic→Maritaca→Groq, com fallback) e SANITIZA PII antes de qualquer envio externo (LGPD).
Resultado é RASCUNHO — revisão humana (OAB) continua valendo.

Idempotente: não retraduz se já houver resumo_ia (salvo forcar=True).
"""
from __future__ import annotations
import logging

from sqlalchemy import select

from app.models.case import CaseMovimento
from app.services import ai_gateway
from app.services.sanitizer import sanitizar_pii

logger = logging.getLogger("ejc.movimento_ia")

_SYS = (
    "Você explica andamentos processuais em linguagem simples para um cliente leigo. "
    "Em 1 a 2 frases, diga o que o andamento significa na prática e, se houver, qual a "
    "consequência ou próximo passo típico. NÃO invente prazos, valores, nomes ou fatos "
    "que não estejam no texto. NÃO prometa resultado. Seja direto, claro e objetivo."
)


async def traduzir_movimento(db, movimento_id: str, forcar: bool = False) -> str | None:
    """Gera e persiste o resumo em linguagem simples de um andamento.

    Args:
        db: sessão async já aberta (do request ou do event_bus).
        movimento_id: id do CaseMovimento.
        forcar: se True, retraduz mesmo que já exista resumo_ia.
    Returns:
        O resumo (str) ou None se não foi possível gerar.
    """
    mov = (await db.execute(
        select(CaseMovimento).where(CaseMovimento.id == str(movimento_id))
    )).scalar_one_or_none()
    if not mov:
        return None
    if mov.resumo_ia and not forcar:
        return mov.resumo_ia

    texto = (mov.descricao or "").strip()
    if len(texto) < 8:
        return None
    texto_limpo, _ = sanitizar_pii(texto)

    try:
        resp = await ai_gateway.chat(
            messages=[
                {"role": "system", "content": _SYS},
                {"role": "user",
                 "content": f"ANDAMENTO:\n{texto_limpo}\n\nExplique em linguagem simples:"},
            ],
            task_type="resumo",
            temperature=0.2,
            max_tokens=220,
        )
    except Exception as e:
        logger.warning(f"[movimento_ia] IA falhou p/ {movimento_id}: {e}")
        return None

    resumo = (resp.texto or "").strip()
    if not resumo:
        return None
    mov.resumo_ia = resumo
    await db.commit()
    logger.info(
        f"[movimento_ia] andamento {movimento_id} traduzido "
        f"({resp.provedor}/{resp.modelo})"
    )
    return resumo
