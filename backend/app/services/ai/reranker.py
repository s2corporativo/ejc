# ── app/services/ai/reranker.py ──────────────────────────────────────────────
# RERANKING (cross-encoder) do RAG — Fase 1 da auditoria de IA (2026-07-17).
#
# O retrieval atual (ai_service.buscar_contexto_rag) recupera candidatos por
# pgvector cosine e funde com a perna lexical (pg_trgm) via RRF. Falta o passo
# que mais melhora a PRECISÃO do contexto em RAG jurídico: reordenar os
# candidatos com um cross-encoder que lê a CONSULTA e o TRECHO juntos e pontua a
# relevância real (não a mera proximidade de embeddings independentes).
#
# Estratégia: recuperar um POOL amplo (limite × MULT) e, após o rerank, entregar
# ao modelo só os `limite` melhores. Assim menos "contexto irrelevante" chega ao
# LLM — principal causa de raciocínio fraco e de alucinação por distração.
#
# Soberania de dados: usa fastembed (ONNX, sem torch), modelo LOCAL — o texto
# NUNCA sai do VPS (mesmo princípio do embedding_service).
#
# Fail-safe (idêntico ao embedding_service): fastembed ausente, modelo não
# suportado pela versão instalada, ou QUALQUER erro → mantém o ranking híbrido,
# aplicando apenas o pequeno bônus determinístico de autoridade jurídica.
from __future__ import annotations

import asyncio
import logging
import threading

from app.core.config import get_settings
from app.services.knowledge_governance import inferir_autoridade

logger = logging.getLogger("ejc.ai.reranker")
settings = get_settings()

# Cross-encoders têm janela curta; truncar cada trecho evita input excessivo
# (e mantém o rerank barato). O trecho completo segue no candidato original —
# aqui só pontuamos relevância.
_MAX_CHARS = 2000

_model = None
_model_lock = threading.Lock()
_IMPORTAVEL: bool | None = None


def habilitado() -> bool:
    """RAG_RERANK_ENABLED (config). Desligado → busca mantém ordem RRF atual."""
    return bool(getattr(settings, "RAG_RERANK_ENABLED", False))


def disponivel() -> bool:
    """True se o rerank está habilitado E o cross-encoder do fastembed é
    importável. Checagem barata e cacheada (não baixa o modelo — isso só
    acontece no 1º rerank real, em _try_get_model)."""
    global _IMPORTAVEL
    if not habilitado():
        return False
    if _IMPORTAVEL is None:
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            suportados = {m["model"] for m in TextCrossEncoder.list_supported_models()}
            _IMPORTAVEL = settings.RAG_RERANK_MODEL in suportados
            if not _IMPORTAVEL:
                logger.error(
                    "Reranker '%s' não é suportado pelo fastembed pinado",
                    settings.RAG_RERANK_MODEL,
                )
        except Exception:
            _IMPORTAVEL = False
            logger.info(
                "fastembed cross-encoder ausente — reranking desligado "
                "(RAG usa a ordem RRF do retrieval híbrido)"
            )
    return _IMPORTAVEL


def tamanho_pool(limite: int) -> int:
    """Nº de candidatos a recuperar ANTES do rerank (deve exceder o `limite`
    final para o cross-encoder ter o que reordenar)."""
    mult = max(1, int(getattr(settings, "RAG_RERANK_POOL_MULT", 5)))
    minimo = max(int(limite), int(getattr(settings, "RAG_RERANK_POOL_MIN", 20)))
    return max(int(limite) * mult, minimo)


def _try_get_model():
    """Singleton thread-safe. 1ª chamada baixa o modelo (runtime). Se o modelo
    não for suportado pela versão instalada do fastembed (ou falhar), marca o
    reranker como indisponível NESTE processo (não retenta a cada consulta) e
    devolve None → o chamador mantém a ordem RRF."""
    global _model, _IMPORTAVEL
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder
                nome = settings.RAG_RERANK_MODEL
                logger.info("Carregando reranker %s (1ª vez — download em runtime)...", nome)
                _model = TextCrossEncoder(model_name=nome)
                logger.info("[Reranker] %s carregado", nome)
            except Exception as e:
                _IMPORTAVEL = False  # não tenta de novo neste processo
                logger.warning(
                    "[Reranker] modelo '%s' indisponível (%s) — RAG mantém a "
                    "ordem RRF. Ajuste RAG_RERANK_MODEL para um suportado pela "
                    "versão do fastembed (ex.: BAAI/bge-reranker-base).",
                    getattr(settings, "RAG_RERANK_MODEL", "?"), str(e)[:200],
                )
                return None
    return _model


def _rerank_sync(consulta: str, textos: list[str]) -> list[float]:
    model = _try_get_model()
    if model is None:
        return []
    return [float(s) for s in model.rerank(consulta, textos)]


def _confidence_bonus(candidate: dict) -> float:
    confidence = str(candidate.get("confianca") or "media").strip().lower()
    return {"alta": 0.015, "media": 0.0, "baixa": -0.015}.get(confidence, 0.0)


def _enrich(candidate: dict) -> tuple[dict, float]:
    """Anexa autoridade/citação e devolve bônus pequeno de governança.

    O bônus máximo é intencionalmente baixo: autoridade desempata fontes de
    relevância próxima, mas não faz uma lei oficial irrelevante superar um
    precedente diretamente relacionado à pergunta.
    """
    item = dict(candidate)
    authority = inferir_autoridade(
        item.get("categoria"),
        item.get("fonte"),
        item.get("extra") if isinstance(item.get("extra"), dict) else None,
    )
    bonus = max(0.0, (float(authority["weight"]) - 40.0) / 1000.0)
    bonus += _confidence_bonus(item)
    item["autoridade"] = authority
    item["citacao"] = {
        "documento_id": item.get("doc_id"),
        "chunk_id": item.get("chunk_id"),
        "titulo": item.get("titulo"),
        "categoria": item.get("categoria"),
        "fonte": item.get("fonte"),
        "versao": item.get("versao"),
        "autoridade": authority,
    }
    item["governance_bonus"] = round(bonus, 5)
    return item, bonus


def _prioritize_existing_order(candidates: list[dict], limit: int) -> list[dict]:
    """Preserva o RRF como sinal principal e usa autoridade apenas como desempate."""
    if not candidates:
        return candidates
    size = max(1, len(candidates))
    enriched = []
    for index, candidate in enumerate(candidates):
        item, bonus = _enrich(candidate)
        # Decaimento suave por posição: o bônus pode mover poucos lugares, nunca
        # inverter completamente um ranking de relevância bem definido.
        base = 1.0 - (index / size)
        item["governance_score"] = round(base + bonus, 5)
        enriched.append((item, base + bonus, index))
    enriched.sort(key=lambda row: (row[1], -row[2]), reverse=True)
    return [row[0] for row in enriched[:limit]]


async def rerank(
    consulta: str,
    candidatos: list[dict],
    limite: int,
    campo: str = "conteudo",
) -> list[dict]:
    """Reordena por relevância e aplica prioridade jurídica controlada.

    Toda saída recebe metadados estruturados de ``autoridade`` e ``citacao``.
    Quando o cross-encoder está ativo, o bônus de autoridade é somado ao score
    apenas como desempate. Quando está indisponível, a ordem RRF continua sendo o
    sinal principal e recebe o mesmo desempate determinístico.
    """
    if not candidatos:
        return candidatos
    if not disponivel() or len(candidatos) <= 1:
        return _prioritize_existing_order(candidatos, limite)
    try:
        textos = [((c.get(campo) or "")[:_MAX_CHARS]) for c in candidatos]
        scores = await asyncio.to_thread(_rerank_sync, consulta, textos)
        if not scores or len(scores) != len(candidatos):
            if scores:
                logger.warning(
                    "[Reranker] %d scores para %d candidatos — mantendo ordem RRF",
                    len(scores), len(candidatos),
                )
            return _prioritize_existing_order(candidatos, limite)

        ordered = []
        for index, (candidate, score) in enumerate(zip(candidatos, scores)):
            item, bonus = _enrich(candidate)
            item["rerank_score"] = round(float(score), 5)
            item["governance_score"] = round(float(score) + bonus, 5)
            ordered.append((item, float(score) + bonus, index))
        ordered.sort(key=lambda row: (row[1], -row[2]), reverse=True)
        return [row[0] for row in ordered[:limite]]
    except Exception as e:  # fail-safe: rerank nunca derruba o RAG
        logger.warning("[Reranker] falha no rerank (%s) — mantendo ordem RRF", str(e)[:200])
        return _prioritize_existing_order(candidatos, limite)
