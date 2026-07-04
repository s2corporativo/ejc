# ── app/services/embedding_service.py ────────────────────────────────────────
# Embeddings locais (soberania de dados) via fastembed (ONNX, sem torch):
#   sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (768d),
#   multilíngue (~50 idiomas, PT-BR incluído) — casa com a coluna
#   knowledge_chunks.embedding vector(768) do pgvector (migration 013).
# Protocolo E5 (prefixos "query: "/"passage: ") só se aplica a modelos E5;
# o mpnet não usa prefixo — mantemos o parâmetro `modo` pela API HTTP.
# Lazy-load + singleton: o modelo (~1GB no 1º download) só carrega no
# primeiro uso, nunca no boot; encode roda em thread (asyncio.to_thread).
# Provider local: fastembed no mesmo processo.
# Provider http: backend leve chama um serviço interno de embeddings.
# Qualquer falha → retorna None e a busca cai para o caminho textual.
from __future__ import annotations
import asyncio
import logging
import threading
import httpx
from app.core.config import get_settings

logger = logging.getLogger("ejc.embeddings")
settings = get_settings()

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
EMBED_DIM  = 768  # deve casar com vector(768) de knowledge_chunks.embedding

_model = None
_model_lock = threading.Lock()
_DISPONIVEL: bool | None = None


def _provider() -> str:
    return (settings.EMBEDDINGS_PROVIDER or "local").strip().lower()


def disponivel() -> bool:
    """True se embeddings estão habilitados e o provider está configurado."""
    global _DISPONIVEL
    if not settings.EMBEDDINGS_ENABLED:
        return False
    if _provider() == "http":
        return bool(settings.EMBEDDINGS_API_URL)
    if _DISPONIVEL is None:
        try:
            import fastembed  # noqa: F401
            _DISPONIVEL = True
        except ImportError:
            _DISPONIVEL = False
            logger.info("fastembed ausente — busca semântica off")
    return _DISPONIVEL


def _get_model():
    """Singleton thread-safe; 1ª chamada baixa o modelo (~1GB) em runtime."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from fastembed import TextEmbedding
                logger.info(f"Carregando {MODEL_NAME} (primeira vez — download ~1GB)...")
                _model = TextEmbedding(model_name=MODEL_NAME)
                logger.info(f"[Embeddings] {MODEL_NAME} carregado ({EMBED_DIM}d)")
    return _model


def _prefixo(modo: str) -> str:
    # Prefixos query:/passage: são protocolo dos modelos E5; mpnet não usa.
    return f"{modo}: " if "e5" in MODEL_NAME.lower() else ""


def _embed_sync(textos: list[str], prefix: str) -> list[list[float]]:
    model = _get_model()
    entradas = [prefix + t for t in textos]
    return [vec.tolist() for vec in model.embed(entradas)]


def _validar_dimensao(vetores: list[list[float]] | None) -> list[list[float]] | None:
    """Garante que os vetores casam com a coluna pgvector vector(768)."""
    if not vetores:
        return None
    dim = len(vetores[0])
    if dim != EMBED_DIM:
        logger.warning(
            f"Embedding com dimensão {dim} != {EMBED_DIM} esperada pelo "
            "pgvector — descartando (busca cai para textual)"
        )
        return None
    return vetores


async def _embed_http(textos: list[str], modo: str) -> list[list[float]] | None:
    payload = {"textos": textos, "modo": modo}
    try:
        async with httpx.AsyncClient(timeout=settings.EMBEDDINGS_TIMEOUT) as client:
            resp = await client.post(settings.EMBEDDINGS_API_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return _validar_dimensao(data.get("embeddings"))
    except Exception as e:
        logger.warning(f"Serviço HTTP de embeddings indisponível: {e}")
        return None


async def gerar_embeddings(
    textos: list[str], modo: str = "passage"
) -> list[list[float]] | None:
    """
    Gera embeddings via provider local (fastembed) ou serviço HTTP interno.

    modo="passage" → ingestão de documentos no RAG
    modo="query"   → busca semântica por consulta
    (com modelos E5 o modo vira prefixo; no mpnet atual é ignorado)

    Nunca levanta exceção: qualquer falha retorna None e o chamador
    usa a busca textual (fallback gracioso).
    """
    if not disponivel() or not textos:
        return None
    if _provider() == "http":
        return await _embed_http(textos, modo)
    try:
        vetores = await asyncio.to_thread(_embed_sync, textos, _prefixo(modo))
        return _validar_dimensao(vetores)
    except Exception as e:
        logger.warning(f"Falha ao gerar embeddings: {e}")
        return None
