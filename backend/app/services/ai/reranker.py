# ── app/services/ai/reranker.py ──────────────────────────────────────────────
# RERANKING jurídico multifatorial do RAG.
#
# O retrieval recupera candidatos por pgvector e os funde com a perna lexical
# via RRF. Esta camada reordena os candidatos combinando relevância, autoridade,
# confiança, situação jurídica, verificação recente e aderência de área/tribunal.
from __future__ import annotations

import asyncio
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.rag import KnowledgeDoc
from app.services.knowledge_governance import inferir_autoridade

logger = logging.getLogger("ejc.ai.reranker")
settings = get_settings()

_MAX_CHARS = 2000
_model = None
_model_lock = threading.Lock()
_IMPORTAVEL: bool | None = None

_LEGAL_PENALTIES = {
    "vigente": 0.0,
    "nao_aplicavel": 0.0,
    "vigencia_nao_verificada": -0.02,
    "parcialmente_revogada": -0.03,
    "suspensa": -0.04,
    "historica": -0.05,
    "revogada": -0.08,
}

_LEGAL_LABELS = {
    "vigente": "Vigente",
    "nao_aplicavel": "Não aplicável",
    "vigencia_nao_verificada": "Vigência não verificada",
    "parcialmente_revogada": "Parcialmente revogada",
    "suspensa": "Suspensa",
    "historica": "Versão histórica",
    "revogada": "Revogada",
}

_TRIBUNAIS = (
    "STF", "STJ", "TST", "TSE", "STM", "TJMG", "TRF1", "TRF2", "TRF3",
    "TRF4", "TRF5", "TRF6", "TRT3", "TCU",
)
_AREA_ALIASES = {
    "tributario": ("tribut", "fiscal", "ctn"),
    "ambiental": ("ambient", "ibama", "licenciamento"),
    "administrativo": ("administrativ", "ato administrativo", "servidor"),
    "licitacoes": ("licit", "pregao", "14.133", "contratacao publica"),
    "empresarial": ("empres", "societ", "recuperacao judicial", "falencia"),
    "consumidor_bancario": ("consumidor", "bancari", "banco", "cdc", "pix"),
    "trabalhista_empresarial": ("trabalh", "clt", "empregado", "empregador"),
    "processual_civil": ("processual", "cpc", "tutela", "recurso"),
}


def habilitado() -> bool:
    return bool(getattr(settings, "RAG_RERANK_ENABLED", False))


def disponivel() -> bool:
    """True quando o cross-encoder local está habilitado e importável."""
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
                "fastembed cross-encoder ausente — RAG mantém a ordem híbrida RRF"
            )
    return _IMPORTAVEL


def tamanho_pool(limite: int) -> int:
    mult = max(1, int(getattr(settings, "RAG_RERANK_POOL_MULT", 5)))
    minimo = max(int(limite), int(getattr(settings, "RAG_RERANK_POOL_MIN", 20)))
    return max(int(limite) * mult, minimo)


def _try_get_model():
    global _model, _IMPORTAVEL
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder

                nome = settings.RAG_RERANK_MODEL
                logger.info("Carregando reranker %s...", nome)
                _model = TextCrossEncoder(model_name=nome)
                logger.info("[Reranker] %s carregado", nome)
            except Exception as exc:
                _IMPORTAVEL = False
                logger.warning(
                    "[Reranker] modelo '%s' indisponível (%s) — mantendo RRF",
                    getattr(settings, "RAG_RERANK_MODEL", "?"),
                    str(exc)[:200],
                )
                return None
    return _model


def _rerank_sync(consulta: str, textos: list[str]) -> list[float]:
    model = _try_get_model()
    if model is None:
        return []
    return [float(score) for score in model.rerank(consulta, textos)]


def _normalizar_status_legal(extra: dict[str, Any], vigente_no_ejc: bool) -> str:
    raw = str(
        extra.get("legal_status")
        or extra.get("situacao_normativa")
        or extra.get("vigencia_status")
        or ""
    ).strip().lower()
    aliases = {
        "parcialmente revogada": "parcialmente_revogada",
        "não aplicável": "nao_aplicavel",
        "nao aplicavel": "nao_aplicavel",
        "não verificada": "vigencia_nao_verificada",
        "nao verificada": "vigencia_nao_verificada",
    }
    status = aliases.get(raw, raw)
    if not vigente_no_ejc:
        return "historica"
    if status in _LEGAL_LABELS:
        return status
    return (
        "vigencia_nao_verificada"
        if extra.get("authority_level") == "oficial_normativa"
        else "nao_aplicavel"
    )


def _candidato_normativo(candidate: dict) -> bool:
    """Identifica material que não pode seguir sem governança canônica."""
    categoria = str(candidate.get("categoria") or "").strip().lower()
    extra = candidate.get("extra") if isinstance(candidate.get("extra"), dict) else {}
    autoridade = str(
        extra.get("authority_level") or extra.get("nivel_autoridade") or ""
    ).strip().lower()
    return (
        "legisl" in categoria
        or "norma" in categoria
        or "regulamento" in categoria
        or autoridade == "oficial_normativa"
    )


async def _hidratar_governanca(candidatos: list[dict]) -> list[dict]:
    """Carrega metadados jurídicos e elimina quarentena/revogação do ranking."""
    ids = {str(item.get("doc_id")) for item in candidatos if item.get("doc_id")}
    if not ids:
        return [item for item in candidatos if not _candidato_normativo(item)]
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(
                        KnowledgeDoc.id,
                        KnowledgeDoc.extra,
                        KnowledgeDoc.vigente,
                        KnowledgeDoc.tribunal,
                        KnowledgeDoc.atualizado_em,
                    ).where(
                        KnowledgeDoc.id.in_(ids),
                        KnowledgeDoc.deleted_at.is_(None),
                    )
                )
            ).all()
        metadata = {
            str(doc_id): (dict(extra or {}), bool(vigente), tribunal, atualizado_em)
            for doc_id, extra, vigente, tribunal, atualizado_em in rows
        }
        hydrated: list[dict] = []
        for candidate in candidatos:
            item = dict(candidate)
            extra, vigente, tribunal, atualizado_em = metadata.get(
                str(item.get("doc_id")),
                (dict(item.get("extra") or {}), True, item.get("tribunal"), None),
            )
            if bool(extra.get("quarantine_active")):
                logger.info(
                    "RAG excluiu documento em quarentena ativa: doc_id=%s",
                    item.get("doc_id"),
                )
                continue
            status = _normalizar_status_legal(extra, vigente)
            item["extra"] = extra
            item["tribunal"] = (
                tribunal or item.get("tribunal") or extra.get("tribunal")
            )
            item["atualizado_em"] = atualizado_em
            item["vigente_no_ejc"] = vigente
            item["situacao_juridica"] = {
                "code": status,
                "label": _LEGAL_LABELS[status],
                "warning": status in {
                    "vigencia_nao_verificada",
                    "parcialmente_revogada",
                    "suspensa",
                    "historica",
                    "revogada",
                },
            }
            if status == "revogada" and vigente:
                logger.info(
                    "RAG excluiu norma revogada da fundamentação atual: doc_id=%s",
                    item.get("doc_id"),
                )
                continue
            hydrated.append(item)
        return hydrated
    except Exception as exc:
        seguros = [item for item in candidatos if not _candidato_normativo(item)]
        logger.warning(
            "Governança documental indisponível no reranking (%s) — mantendo apenas candidatos não normativos",
            str(exc)[:180],
        )
        return seguros


def _confidence_bonus(candidate: dict) -> float:
    confidence = str(candidate.get("confianca") or "media").strip().lower()
    return {
        "alta": 0.015,
        "media": 0.0,
        "baixa": -0.015,
        "bloqueado": -0.10,
    }.get(confidence, 0.0)


def _explicit_authority_bonus(extra: dict[str, Any]) -> float:
    """Usa score_autoridade canônico sem deixar metadado dominar relevância."""
    try:
        score = max(0.0, min(100.0, float(extra.get("score_autoridade"))))
    except (TypeError, ValueError):
        return 0.0
    return (score - 50.0) / 2000.0


def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    raw = str(value).strip()
    for candidate in (raw, raw.replace("Z", "+00:00")):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    match = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", raw)
    if match:
        return datetime(
            int(match.group(3)),
            int(match.group(2)),
            int(match.group(1)),
            tzinfo=timezone.utc,
        )
    return None


def _verification_freshness_bonus(candidate: dict, extra: dict[str, Any]) -> float:
    """Premia verificação recente, não a idade do precedente em si."""
    dt = (
        _parse_date(extra.get("last_verified_at"))
        or _parse_date(extra.get("legal_status_verificado_em"))
        or _parse_date(extra.get("data_pesquisa"))
        or _parse_date(candidate.get("atualizado_em"))
    )
    if not dt:
        return -0.005
    days = max(0, (datetime.now(timezone.utc) - dt).days)
    if days <= 90:
        return 0.012
    if days <= 365:
        return 0.006
    if days <= 1095:
        return 0.0
    return -0.006


def _compactar_sigla(value: Any) -> str:
    """Normaliza `TRF-6`, `TRF 6` e `TRF6` para a mesma chave de ranking."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _query_alignment_bonus(candidate: dict, extra: dict[str, Any], consulta: str) -> float:
    q = re.sub(r"\s+", " ", (consulta or "").upper())
    q_compact = _compactar_sigla(q)
    bonus = 0.0
    tribunal = _compactar_sigla(
        candidate.get("tribunal") or extra.get("tribunal") or ""
    )
    tribunais_query = {
        tribunal_id for tribunal_id in _TRIBUNAIS if tribunal_id in q_compact
    }
    if tribunais_query:
        bonus += (
            0.012
            if any(tribunal.startswith(tribunal_id) for tribunal_id in tribunais_query)
            else -0.004
        )

    q_lower = q.lower()
    area = str(extra.get("area_juridica") or "").strip().lower()
    if area and area in _AREA_ALIASES:
        aliases = _AREA_ALIASES[area]
        if any(alias in q_lower for alias in aliases):
            bonus += 0.01
    return bonus


def _enrich(candidate: dict, consulta: str = "") -> tuple[dict, float]:
    """Anexa governança e devolve ajuste multifatorial pequeno e auditável."""
    item = dict(candidate)
    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    authority = inferir_autoridade(
        item.get("categoria"), item.get("fonte"), extra
    )
    legal = (
        item.get("situacao_juridica")
        if isinstance(item.get("situacao_juridica"), dict)
        else None
    )
    status = str((legal or {}).get("code") or "nao_aplicavel")

    fatores = {
        "autoridade_inferida": max(
            0.0, (float(authority["weight"]) - 40.0) / 1000.0
        ),
        "score_autoridade": _explicit_authority_bonus(extra),
        "confianca": _confidence_bonus(item),
        "situacao_juridica": _LEGAL_PENALTIES.get(status, -0.01),
        "verificacao_recente": _verification_freshness_bonus(item, extra),
        "aderencia_jurisdicao_area": _query_alignment_bonus(item, extra, consulta),
    }
    bonus = sum(fatores.values())

    item["autoridade"] = authority
    item["situacao_juridica"] = legal or {
        "code": status,
        "label": _LEGAL_LABELS.get(status, "Não classificada"),
        "warning": status not in {"vigente", "nao_aplicavel"},
    }
    item["citacao"] = {
        "documento_id": item.get("doc_id"),
        "chunk_id": item.get("chunk_id"),
        "titulo": item.get("titulo"),
        "categoria": item.get("categoria"),
        "fonte": item.get("fonte"),
        "versao": item.get("versao"),
        "autoridade": authority,
        "situacao_juridica": item["situacao_juridica"],
    }
    item["governance_factors"] = {
        key: round(value, 5) for key, value in fatores.items()
    }
    item["governance_bonus"] = round(bonus, 5)
    return item, bonus


def _prioritize_existing_order(
    candidates: list[dict], limit: int, consulta: str = ""
) -> list[dict]:
    if not candidates:
        return candidates
    size = max(1, len(candidates))
    enriched = []
    for index, candidate in enumerate(candidates):
        item, bonus = _enrich(candidate, consulta)
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
    """Reordena por relevância + governança, com degradação segura."""
    if not candidatos:
        return candidatos

    candidatos = await _hidratar_governanca(candidatos)
    if not candidatos:
        return []

    if not disponivel() or len(candidatos) <= 1:
        return _prioritize_existing_order(candidatos, limite, consulta)
    try:
        textos = [
            ((candidate.get(campo) or "")[:_MAX_CHARS])
            for candidate in candidatos
        ]
        scores = await asyncio.to_thread(_rerank_sync, consulta, textos)
        if not scores or len(scores) != len(candidatos):
            if scores:
                logger.warning(
                    "[Reranker] %d scores para %d candidatos — mantendo RRF",
                    len(scores),
                    len(candidatos),
                )
            return _prioritize_existing_order(candidatos, limite, consulta)

        ordered = []
        for index, (candidate, score) in enumerate(zip(candidatos, scores)):
            item, bonus = _enrich(candidate, consulta)
            item["rerank_score"] = round(float(score), 5)
            item["governance_score"] = round(float(score) + bonus, 5)
            ordered.append((item, float(score) + bonus, index))
        ordered.sort(key=lambda row: (row[1], -row[2]), reverse=True)
        return [row[0] for row in ordered[:limite]]
    except Exception as exc:
        logger.warning(
            "[Reranker] falha (%s) — mantendo ordem híbrida RRF",
            str(exc)[:200],
        )
        return _prioritize_existing_order(candidatos, limite, consulta)
