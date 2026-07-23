# ── app/services/embedding_service.py ────────────────────────────────────────
# Embeddings locais (soberania de dados) via fastembed (ONNX, sem torch).
# Modelo/dimensão CONFIGURÁVEIS (auditoria IA 2026-07-17, O-2):
#   default intfloat/multilingual-e5-large (1024d, suportado pelo fastembed
#   pinado) — casa com a coluna
#   knowledge_chunks.embedding vector(1024) da migration 096. Trocar a dimensão
#   exige migration + reindex (scripts.reembedar_chunks_orfaos). Revertível por
#   env (EMBEDDINGS_MODEL/EMBEDDINGS_DIM).
# Protocolo E5 (prefixos "query: "/"passage: ") só se aplica a modelos E5 (ex.:
#   multilingual-e5-large); outros modelos não usam prefixo (detectado por _prefixo).
# Lazy-load + singleton: o modelo (~2,3 GB no 1º download) só carrega no
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

# Configuráveis por env. Default multilingual-e5-large (1024d). DEVE casar com a coluna
# knowledge_chunks.embedding vector(EMBED_DIM) — ver migration 096 e o runbook.
MODEL_NAME = settings.EMBEDDINGS_MODEL or "intfloat/multilingual-e5-large"
EMBED_DIM  = int(settings.EMBEDDINGS_DIM or 1024)

# Pooling FIXO por REPRODUTIBILIDADE do RAG. Os modelos E5 (intfloat/*-e5-*) são
# treinados com pooling por MÉDIA (mean) das últimas hidden states — NÃO CLS. O
# fastembed PINADO (==0.8.0, ver requirements.txt) já aplica o pooling correto
# embutido no registro ONNX do modelo; explicitamos aqui para que uma futura
# troca de versão/modelo seja avaliada contra esta premissa — o e5 chegou a
# mudar de CLS→média entre versões upstream, alterando os vetores e a ordenação
# do retrieval. Não é um parâmetro que reconfigure o encode (o fastembed 0.8.0
# não expõe pooling na TextEmbedding); é o CONTRATO documentado que o pin garante.
POOLING_ESPERADO = "mean"  # E5 = média; trocar de modelo exige reavaliar isto

_model = None
_model_lock = threading.Lock()
_DISPONIVEL: bool | None = None


def validar_modelo_local() -> tuple[bool, str]:
    """Valida nome e dimensão sem baixar pesos.

    Este gate impede que uma configuração não suportada passe pelo healthcheck,
    pelo scheduler ou pelo CI e só falhe depois de a coluna vetorial ter sido
    migrada. Provider HTTP é validado pelo contrato de dimensão da resposta.
    """
    if _provider() != "local":
        return True, "provider http: dimensão validada na resposta"
    try:
        from fastembed import TextEmbedding
        modelos = {m["model"]: int(m["dim"]) for m in TextEmbedding.list_supported_models()}
    except Exception as exc:
        return False, f"fastembed indisponível: {exc}"
    dimensao = modelos.get(MODEL_NAME)
    if dimensao is None:
        return False, f"modelo não suportado pelo fastembed pinado: {MODEL_NAME}"
    if dimensao != EMBED_DIM:
        return False, f"dimensão declarada {EMBED_DIM} != dimensão do modelo {dimensao}"
    return True, f"{MODEL_NAME} ({dimensao}d)"


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
        _DISPONIVEL, detalhe = validar_modelo_local()
        if not _DISPONIVEL:
            logger.error("Embeddings locais bloqueados: %s", detalhe)
    return _DISPONIVEL


def _get_model():
    """Singleton thread-safe; 1ª chamada baixa o modelo (~1GB) em runtime."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from fastembed import TextEmbedding
                logger.info(f"Carregando {MODEL_NAME} (primeira vez — download ~2,3 GB)...")
                _model = TextEmbedding(model_name=MODEL_NAME)
                logger.info(
                    f"[Embeddings] {MODEL_NAME} carregado "
                    f"({EMBED_DIM}d, pooling={POOLING_ESPERADO}, fastembed pinado)"
                )
    return _model


def _prefixo(modo: str) -> str:
    # Prefixos query:/passage: são protocolo dos modelos E5; mpnet não usa.
    return f"{modo}: " if "e5" in MODEL_NAME.lower() else ""


def _embed_sync(textos: list[str], prefix: str) -> list[list[float]]:
    model = _get_model()
    entradas = [prefix + t for t in textos]
    return [vec.tolist() for vec in model.embed(entradas)]


def _validar_dimensao(vetores: list[list[float]] | None) -> list[list[float]] | None:
    """Garante que os vetores casam com a dimensão configurada no pgvector."""
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


# Cache LRU em memória para embeddings de QUERY única (buscas repetidas: mesmo
# termo por vários usuários no mesmo dia). Só o caminho de consulta é cacheado —
# ingestão (passage) é one-shot e volumosa. Limite pequeno; evicção FIFO/LRU.
from collections import OrderedDict

_QUERY_CACHE: "OrderedDict[tuple[str, str], list[float]]" = OrderedDict()
_QUERY_CACHE_MAX = 256


def _cache_query_get(modo: str, texto: str) -> list[float] | None:
    chave = (modo, texto)
    vec = _QUERY_CACHE.get(chave)
    if vec is not None:
        _QUERY_CACHE.move_to_end(chave)  # LRU: marca como recém-usado
    return vec


def _cache_query_put(modo: str, texto: str, vec: list[float]) -> None:
    chave = (modo, texto)
    _QUERY_CACHE[chave] = vec
    _QUERY_CACHE.move_to_end(chave)  # necessário só no caminho de sobrescrita
    while len(_QUERY_CACHE) > _QUERY_CACHE_MAX:
        _QUERY_CACHE.popitem(last=False)  # remove o menos recentemente usado


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
    # Fast path: query única já vista → devolve o vetor cacheado (sem recomputar).
    cacheavel = modo == "query" and len(textos) == 1
    if cacheavel:
        vec = _cache_query_get(modo, textos[0])
        if vec is not None:
            return [vec]
    if _provider() == "http":
        vetores = await _embed_http(textos, modo)
    else:
        try:
            vetores = await asyncio.to_thread(_embed_sync, textos, _prefixo(modo))
            vetores = _validar_dimensao(vetores)
        except Exception as e:
            logger.warning(f"Falha ao gerar embeddings: {e}")
            vetores = None
    # Contagem: um provider (sobretudo o HTTP, serviço externo fora do nosso
    # controle) pode devolver MENOS vetores do que textos pedidos — sem isto,
    # o chamador casaria vetores com chunks por POSIÇÃO (zip/index) e deixaria
    # os chunks finais sem embedding, mesmo o doc sendo marcado "indexado"
    # (achado da auditoria RAG: 26k chunks órfãos com doc status='indexado').
    # Tudo-ou-nada: contagem errada é falha total, cai para o textual.
    if vetores is not None and len(vetores) != len(textos):
        logger.warning(
            "Embeddings: provider devolveu %d vetores para %d textos — "
            "descartando o lote (contagem não bate)", len(vetores), len(textos),
        )
        vetores = None
    if cacheavel and vetores:
        _cache_query_put(modo, textos[0], vetores[0])
    return vetores
