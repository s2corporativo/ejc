"""
RAG Jurídico — EJC Intelligence v3.0
Match de Casos com busca vetorial REAL (pgvector, via buscar_contexto_rag) e
explicação por LLM apenas sobre os trechos efetivamente recuperados.

Nota de honestidade: a antiga `ingestao_jurisprudencia` (que só logava
"em fila" sem ingerir nada) foi removida — a ingestão real é feita pelo
pipeline de app/services/ingestion_service.upsert_documento (router rag.py).
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_brain import ai_brain

logger = logging.getLogger("rag_juridico")


class RAGJuridico:
    def __init__(self):
        self.ai = ai_brain

    async def match_de_casos(self, texto_caso: str, area: str, db: AsyncSession) -> dict:
        """
        Match semântico REAL entre o caso novo e a base de conhecimento do
        escritório:
          1. Busca vetorial pgvector (cosine) via buscar_contexto_rag, com
             fallback textual quando não há embeddings.
          2. Só os top-N trechos recuperados são passados ao LLM, que explica
             a aderência de cada um ao caso — sem inventar precedentes.

        Retorna {"status", "casos_similares": [...], "analise": str|None}.
        Se nada for recuperado, retorna status "sem_resultados" (sem chamar o
        LLM, para não gerar "matches" alucinados).
        """
        from app.services.ai_service import buscar_contexto_rag

        similares = await buscar_contexto_rag(
            db, texto_caso, limite=5, modo_or=True
        )
        if not similares:
            return {
                "status": "sem_resultados",
                "mensagem": (
                    "Nenhum documento similar encontrado na base de "
                    "conhecimento do escritório para este caso."
                ),
                "casos_similares": [],
                "analise": None,
            }

        trechos = "\n\n".join(
            f"[{i+1}] (fonte: {c.get('fonte') or c.get('categoria') or 'interna'}, "
            f"score: {c.get('score')}) {c.get('titulo') or ''}\n"
            f"{(c.get('conteudo') or '')[:1200]}"
            for i, c in enumerate(similares)
        )
        prompt = (
            "Como assistente jurídico sênior, analise o Match de Casos abaixo.\n"
            f"Área: {area}\n"
            f"Caso novo: {texto_caso}\n\n"
            "Documentos recuperados da base interna (busca vetorial):\n"
            f"{trechos}\n\n"
            "Para cada documento numerado, explique em 1-2 frases por que é (ou "
            "não é) aplicável ao caso novo. Baseie-se APENAS nos trechos acima; "
            "não cite precedentes ou números de processo que não constem deles."
        )
        try:
            analise = await self.ai.generate(prompt, "principal")
        except Exception as e:
            logger.warning(f"[rag_juridico] LLM indisponível no match: {e}")
            analise = None

        return {
            "status": "success",
            "casos_similares": similares,
            "analise": analise,
        }


rag_juridico = RAGJuridico()
