# ── app/services/embedding_service.py ────────────────────────────────────────
# Embeddings locais (soberania de dados): intfloat/multilingual-e5-base (768d).
# Multilingual — adequado para textos jurídicos em português.
# Protocolo E5: consultas levam prefixo "query: ";
#               documentos (ingestão) levam prefixo "passage: ".
# Lazy-load: o modelo (~450MB) só carrega no primeiro uso.
# Se sentence-transformers não estiver instalado → busca cai p/ textual.
# Instalação: pip install -r requirements-ml.txt
from __future__ import annotations
import asyncio
import logging
from app.core.config import get_settings

logger = logging.getLogger("ejc.embeddings")
settings = get_settings()

MODEL_NAME = "intfloat/multilingual-e5-base"
EMBED_DIM  = 768  # dimensão do multilingual-e5-base

_model = None
_DISPONIVEL: bool | None = None


def disponivel() -> bool:
    """True se a lib está instalada E a flag habilitada."""
    global _DISPONIVEL
    if not settings.EMBEDDINGS_ENABLED:
        return False
    if _DISPONIVEL is None:
        try:
            import sentence_transformers  # noqa
            _DISPONIVEL = True
        except ImportError:
            _DISPONIVEL = False
            logger.info("sentence-transformers ausente — busca semântica off")
    return _DISPONIVEL


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Carregando {MODEL_NAME} (primeira vez — ~450MB)...")
        _model = SentenceTransformer(MODEL_NAME)
        logger.info(f"[Embeddings] {MODEL_NAME} carregado ({EMBED_DIM}d)")
    return _model


def _embed_sync(textos: list[str], prefix: str) -> list[list[float]]:
    model = _get_model()
    entradas = [prefix + t for t in textos]
    return model.encode(entradas, normalize_embeddings=True).tolist()


async def gerar_embeddings(
    textos: list[str], modo: str = "passage"
) -> list[list[float]] | None:
    """
    Async wrapper (CPU-bound → to_thread). None se indisponível.

    modo="passage" → prefixo "passage: " (ingestão de documentos no RAG)
    modo="query"   → prefixo "query: "   (busca semântica por consulta)
    """
    if not disponivel() or not textos:
        return None
    prefix = f"{modo}: "
    try:
        return await asyncio.to_thread(_embed_sync, textos, prefix)
    except Exception as e:
        logger.warning(f"Falha ao gerar embeddings: {e}")
        return None
