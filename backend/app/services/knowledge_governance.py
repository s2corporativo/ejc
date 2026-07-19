"""Governança jurídica e operacional da Base de Conhecimento do EJC.

A camada mantém separadas quatro perguntas que não podem ser confundidas:

* o documento está autorizado para uso pelo RAG? (rag_status)
* a fonte possui qual autoridade jurídica? (authority_level)
* o texto está tecnicamente íntegro e recuperável? (quality)
* a norma está juridicamente vigente? (legal_status)

A política do escritório autoriza todos os documentos do módulo para recuperação,
mas isso não transforma material interno/doutrinário em fonte oficial nem presume a
vigência de uma norma que ainda não foi conferida.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Iterable
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import KnowledgeChunk, KnowledgeDoc


OFFICIAL_HOST_SUFFIXES = (
    "planalto.gov.br",
    "gov.br",
    "cnj.jus.br",
    "stf.jus.br",
    "stj.jus.br",
    "tst.jus.br",
    "tse.jus.br",
    "stm.jus.br",
    "trf1.jus.br",
    "trf2.jus.br",
    "trf3.jus.br",
    "trf4.jus.br",
    "trf5.jus.br",
    "trf6.jus.br",
    "tjmg.jus.br",
    "trt3.jus.br",
    "camara.leg.br",
    "senado.leg.br",
    "lexml.gov.br",
    "in.gov.br",
    "bcb.gov.br",
)

AUTHORITY_LABELS = {
    "oficial_normativa": "Oficial normativa",
    "precedente_vinculante": "Precedente vinculante/oficial",
    "jurisprudencia_oficial": "Jurisprudência oficial",
    "oficial_informativa": "Oficial informativa",
    "institucional_interna": "Institucional interna",
    "doutrinaria": "Doutrinária",
    "referencial": "Referencial",
}

AUTHORITY_WEIGHTS = {
    "oficial_normativa": 100,
    "precedente_vinculante": 96,
    "jurisprudencia_oficial": 90,
    "oficial_informativa": 80,
    "institucional_interna": 65,
    "doutrinaria": 55,
    "referencial": 40,
}

LEGAL_STATUS_VALUES = {
    "vigente",
    "parcialmente_revogada",
    "revogada",
    "suspensa",
    "vigencia_nao_verificada",
    "nao_aplicavel",
    "historica",
}

STANDARD_AREAS: dict[str, tuple[str, ...]] = {
    "Civil": ("civil", "cpc", "codigo civil", "responsabilidade civil", "contrato"),
    "Consumidor": ("consumidor", "cdc", "plano de saude", "telefonia", "negativacao"),
    "Trabalhista": ("trabalh", "clt", "tst", "trt", "empregado", "empregador"),
    "Penal": ("penal", "criminal", "cpp", "codigo penal", "crime"),
    "Empresarial": ("empres", "societ", "falencia", "recuperacao judicial"),
    "Tributário": ("tribut", "fiscal", "ctn", "carf", "receita federal"),
    "Administrativo": ("administrativ", "servidor", "ato administrativo"),
    "Ambiental": ("ambient", "ibama", "licenciamento", "sicar", "car "),
    "Previdenciário": ("previdenc", "inss", "beneficio", "aposentadoria"),
    "Família e Sucessões": ("familia", "sucess", "inventario", "divorcio", "alimentos"),
    "Imobiliário": ("imobili", "usucapiao", "locacao", "condominio"),
    "Bancário": ("bancari", "banco", "financiamento", "juros remuneratorios"),
    "Digital/LGPD": ("lgpd", "dados pessoais", "digital", "anpd"),
    "Licitações e Contratos": ("licit", "pregao", "pncp", "contrato administrativo"),
}

COVERAGE_DIMENSIONS = ("legislacao", "sumulas", "jurisprudencia", "modelos", "doutrina")

LEGAL_SMOKE_TESTS = (
    {
        "id": "tutela_urgencia",
        "pergunta": "requisitos da tutela de urgência probabilidade do direito perigo de dano",
        "termos": ("probabilidade", "perigo"),
    },
    {
        "id": "contestacao_cpc",
        "pergunta": "prazo para contestação no processo civil artigo 335 CPC",
        "termos": ("335", "contestação", "contestacao"),
    },
    {
        "id": "jec_fazenda_limite",
        "pergunta": "limite de competência do Juizado Especial da Fazenda Pública",
        "termos": ("60", "sessenta", "salários", "salarios"),
    },
    {
        "id": "responsabilidade_civil",
        "pergunta": "requisitos da responsabilidade civil dano nexo causal conduta",
        "termos": ("dano", "nexo"),
    },
    {
        "id": "vinculo_emprego",
        "pergunta": "requisitos do vínculo de emprego pessoalidade subordinação onerosidade habitualidade",
        "termos": ("subordinação", "subordinacao", "pessoalidade"),
    },
)


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _hostname(source: str | None) -> str:
    value = (source or "").strip()
    if not value.startswith(("http://", "https://")):
        return ""
    try:
        return (urlparse(value).hostname or "").lower()
    except ValueError:
        return ""


def fonte_oficial(source: str | None) -> bool:
    host = _hostname(source)
    return bool(host and any(host == suffix or host.endswith("." + suffix) for suffix in OFFICIAL_HOST_SUFFIXES))


def inferir_autoridade(
    categoria: str | None,
    fonte: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classifica autoridade sem confundir aprovação interna com força jurídica."""
    extra = dict(extra or {})
    explicit = _norm(extra.get("authority_level") or extra.get("nivel_autoridade"))
    if explicit in AUTHORITY_LABELS:
        code = explicit
    else:
        cat = _norm(categoria)
        official = bool(extra.get("source_official")) or fonte_oficial(fonte)
        if "legisl" in cat or "norma" in cat or "regulamento" in cat:
            code = "oficial_normativa" if official else "referencial"
        elif "sumula" in cat or "repercussao" in cat or "repetitivo" in cat:
            code = "precedente_vinculante" if official else "referencial"
        elif "juris" in cat or "acordao" in cat:
            code = "jurisprudencia_oficial" if official else "referencial"
        elif cat in {"peca_interna", "peca_escritorio", "precedente_interno", "tese_vitoriosa", "modelo_documento_juridico"}:
            code = "institucional_interna"
        elif "doutrina" in cat:
            code = "doutrinaria"
        elif official:
            code = "oficial_informativa"
        else:
            code = "referencial"
    return {
        "code": code,
        "label": AUTHORITY_LABELS[code],
        "weight": AUTHORITY_WEIGHTS[code],
        "official": code.startswith("oficial_") or code in {"precedente_vinculante", "jurisprudencia_oficial"},
    }


def inferir_autoridade_documento(doc: KnowledgeDoc) -> dict[str, Any]:
    return inferir_autoridade(doc.categoria, doc.fonte, doc.extra or {})


def inferir_situacao_juridica(doc: KnowledgeDoc) -> dict[str, Any]:
    extra = dict(doc.extra or {})
    if not bool(doc.vigente):
        code = "historica"
    else:
        explicit = _norm(
            extra.get("legal_status")
            or extra.get("situacao_normativa")
            or extra.get("vigencia_status")
        )
        aliases = {
            "parcialmente revogada": "parcialmente_revogada",
            "não aplicável": "nao_aplicavel",
            "nao aplicavel": "nao_aplicavel",
            "não verificada": "vigencia_nao_verificada",
            "nao verificada": "vigencia_nao_verificada",
        }
        code = aliases.get(explicit, explicit)
        if code not in LEGAL_STATUS_VALUES:
            code = "vigencia_nao_verificada" if "legisl" in _norm(doc.categoria) else "nao_aplicavel"
    labels = {
        "vigente": "Vigente",
        "parcialmente_revogada": "Parcialmente revogada",
        "revogada": "Revogada",
        "suspensa": "Suspensa",
        "vigencia_nao_verificada": "Vigência não verificada",
        "nao_aplicavel": "Não aplicável",
        "historica": "Versão histórica",
    }
    return {
        "code": code,
        "label": labels[code],
        "permite_fundamentacao_atual": code in {"vigente", "nao_aplicavel"},
        "requires_warning": code in {"parcialmente_revogada", "suspensa", "vigencia_nao_verificada", "historica"},
        "blocks_current_law": code == "revogada",
    }


def _freshness_threshold_days(category: str | None) -> int:
    cat = _norm(category)
    if "legisl" in cat or "sumula" in cat:
        return 14
    if "juris" in cat or "proposicao" in cat:
        return 30
    if "oficial" in cat or "regulator" in cat:
        return 45
    return 180


def avaliar_frescor(doc: KnowledgeDoc, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    extra = dict(doc.extra or {})
    reference = (
        _parse_datetime(extra.get("last_verified_at"))
        or _parse_datetime(extra.get("verificado_em"))
        or _parse_datetime(doc.atualizado_em)
        or _parse_datetime(doc.created_at)
    )
    threshold = _freshness_threshold_days(doc.categoria)
    if reference is None:
        return {"status": "sem_data", "days": None, "threshold_days": threshold, "reference_at": None}
    days = max(0, (now - reference).days)
    return {
        "status": "desatualizado" if days > threshold else "atual",
        "days": days,
        "threshold_days": threshold,
        "reference_at": reference.isoformat(),
    }


def avaliar_qualidade(
    doc: KnowledgeDoc,
    *,
    chunks: int,
    chars: int,
    embedded_chunks: int,
) -> dict[str, Any]:
    extra = dict(doc.extra or {})
    issues: list[str] = []
    score = 100
    min_chars = 80 if "sumula" in _norm(doc.categoria) else 300

    if chunks <= 0:
        issues.append("Documento sem trechos indexáveis")
        score -= 60
    if chars < min_chars:
        issues.append(f"Texto curto ou extração incompleta ({chars} caracteres)")
        score -= 25
    if doc.status_indexacao != "indexado":
        issues.append(f"Vetorização em estado '{doc.status_indexacao or 'desconhecido'}'")
        score -= 20
    elif chunks and embedded_chunks < chunks:
        issues.append(f"{chunks - embedded_chunks} trecho(s) sem embedding")
        score -= 20

    ocr = extra.get("ocr") if isinstance(extra.get("ocr"), dict) else {}
    pages = int(ocr.get("paginas") or 0)
    ocr_pages = int(ocr.get("paginas_ocr") or 0)
    if pages and ocr_pages == pages and not bool(ocr.get("ocr_disponivel", True)):
        issues.append("PDF aparentemente escaneado sem OCR disponível")
        score -= 35
    if extra.get("extraction_warning"):
        issues.append(str(extra["extraction_warning"])[:180])
        score -= 15

    score = max(0, min(100, score))
    status = "integro" if score >= 85 else "com_ressalva" if score >= 60 else "incompleto"
    return {"score": score, "status": status, "issues": issues}


def detectar_area(doc: KnowledgeDoc) -> str:
    extra = dict(doc.extra or {})
    explicit = str(extra.get("area_juridica") or extra.get("area") or "").strip()
    if explicit:
        return explicit
    haystack = _norm(f"{doc.categoria} {doc.titulo} {doc.fonte or ''}")
    for area, terms in STANDARD_AREAS.items():
        if any(term in haystack for term in terms):
            return area
    return "Geral"


def dimensao_cobertura(doc: KnowledgeDoc) -> str | None:
    cat = _norm(doc.categoria)
    if "legisl" in cat or "norma" in cat or "regulamento" in cat:
        return "legislacao"
    if "sumula" in cat or "repetitivo" in cat or "repercussao" in cat:
        return "sumulas"
    if "juris" in cat or "acordao" in cat:
        return "jurisprudencia"
    if any(term in cat for term in ("peca", "modelo", "precedente", "tese")):
        return "modelos"
    if "doutrina" in cat:
        return "doutrina"
    return None


def citacao_estruturada(doc: KnowledgeDoc, *, chunk_index: int | None = None) -> dict[str, Any]:
    authority = inferir_autoridade_documento(doc)
    legal = inferir_situacao_juridica(doc)
    return {
        "documento_id": doc.id,
        "titulo": doc.titulo,
        "categoria": doc.categoria,
        "fonte": doc.fonte,
        "tribunal": doc.tribunal,
        "versao": doc.versao,
        "chunk_index": chunk_index,
        "atualizado_em": (doc.atualizado_em or doc.created_at).isoformat() if (doc.atualizado_em or doc.created_at) else None,
        "autoridade": authority,
        "situacao_juridica": legal,
    }


async def _chunk_metrics(db: AsyncSession) -> dict[str, dict[str, int]]:
    rows = (
        await db.execute(
            select(
                KnowledgeChunk.doc_id,
                func.count(KnowledgeChunk.id),
                func.coalesce(func.sum(func.length(KnowledgeChunk.conteudo)), 0),
                func.count(KnowledgeChunk.embedding),
            ).group_by(KnowledgeChunk.doc_id)
        )
    ).all()
    return {
        str(doc_id): {"chunks": int(count or 0), "chars": int(chars or 0), "embedded": int(embedded or 0)}
        for doc_id, count, chars, embedded in rows
    }


async def _active_docs(db: AsyncSession, *, include_history: bool = True) -> list[KnowledgeDoc]:
    query = select(KnowledgeDoc).where(KnowledgeDoc.deleted_at.is_(None))
    if not include_history:
        query = query.where(KnowledgeDoc.vigente.is_(True))
    return list((await db.execute(query)).scalars().all())


def _duplicate_key(doc: KnowledgeDoc) -> tuple[str, str]:
    return (_norm(doc.categoria), _norm(doc.titulo))


def detectar_duplicidades(docs: Iterable[KnowledgeDoc]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_hash: dict[str, list[KnowledgeDoc]] = defaultdict(list)
    by_title: dict[tuple[str, str], list[KnowledgeDoc]] = defaultdict(list)
    for doc in docs:
        if doc.hash_conteudo:
            by_hash[str(doc.hash_conteudo)].append(doc)
        by_title[_duplicate_key(doc)].append(doc)

    duplicates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for digest, group in by_hash.items():
        current = [d for d in group if d.vigente]
        if len(current) > 1:
            duplicates.append({
                "hash": digest,
                "documentos": [{"id": d.id, "titulo": d.titulo, "versao": d.versao} for d in current],
            })
    for (category, title), group in by_title.items():
        current = [d for d in group if d.vigente]
        hashes = {d.hash_conteudo for d in current if d.hash_conteudo}
        if len(current) > 1 and len(hashes) > 1:
            conflicts.append({
                "categoria": category,
                "titulo": title,
                "documentos": [{"id": d.id, "hash": d.hash_conteudo, "versao": d.versao} for d in current],
            })
    return duplicates, conflicts


async def health_snapshot(db: AsyncSession) -> dict[str, Any]:
    docs = await _active_docs(db, include_history=True)
    current_docs = [d for d in docs if d.vigente]
    metrics = await _chunk_metrics(db)
    duplicates, conflicts = detectar_duplicidades(current_docs)

    counts = Counter()
    alerts: list[dict[str, Any]] = []
    for doc in current_docs:
        metric = metrics.get(doc.id, {"chunks": 0, "chars": 0, "embedded": 0})
        quality = avaliar_qualidade(doc, chunks=metric["chunks"], chars=metric["chars"], embedded_chunks=metric["embedded"])
        fresh = avaliar_frescor(doc)
        legal = inferir_situacao_juridica(doc)
        authority = inferir_autoridade_documento(doc)
        approved = _norm((doc.extra or {}).get("rag_status")) == "aprovado"

        counts["approved"] += int(approved)
        counts["vectorized_docs"] += int(doc.status_indexacao == "indexado")
        counts["usable_docs"] += int(approved and metric["chunks"] > 0 and quality["status"] != "incompleto")
        counts["chunks"] += metric["chunks"]
        counts["embedded_chunks"] += metric["embedded"]
        counts["ocr_issues"] += int(any("OCR" in issue for issue in quality["issues"]))
        counts["stale"] += int(fresh["status"] in {"desatualizado", "sem_data"})
        counts["legal_unverified"] += int(legal["code"] == "vigencia_nao_verificada")

        if quality["status"] != "integro":
            alerts.append({
                "severity": "critical" if quality["status"] == "incompleto" else "warning",
                "code": "quality",
                "doc_id": doc.id,
                "title": doc.titulo,
                "detail": "; ".join(quality["issues"]) or "Qualidade técnica com ressalva",
            })
        if fresh["status"] == "desatualizado" and authority["official"]:
            alerts.append({
                "severity": "warning",
                "code": "stale_source",
                "doc_id": doc.id,
                "title": doc.titulo,
                "detail": f"Fonte oficial sem conferência há {fresh['days']} dias (limite {fresh['threshold_days']}).",
            })
        if legal["code"] == "vigencia_nao_verificada":
            alerts.append({
                "severity": "warning",
                "code": "legal_status",
                "doc_id": doc.id,
                "title": doc.titulo,
                "detail": "Versão atual no EJC, mas vigência jurídica ainda não foi registrada.",
            })

    for group in duplicates:
        alerts.append({
            "severity": "warning",
            "code": "duplicate",
            "doc_id": group["documentos"][0]["id"],
            "title": group["documentos"][0]["titulo"],
            "detail": f"{len(group['documentos'])} cópias vigentes com o mesmo hash.",
        })
    for group in conflicts:
        alerts.append({
            "severity": "critical",
            "code": "conflict",
            "doc_id": group["documentos"][0]["id"],
            "title": group["titulo"],
            "detail": "Existem versões vigentes conflitantes com o mesmo título/categoria.",
        })

    total = len(current_docs)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_docs": total,
            "historical_versions": len(docs) - total,
            "approved_docs": counts["approved"],
            "usable_docs": counts["usable_docs"],
            "vectorized_docs": counts["vectorized_docs"],
            "total_chunks": counts["chunks"],
            "embedded_chunks": counts["embedded_chunks"],
            "chunks_without_embedding": max(0, counts["chunks"] - counts["embedded_chunks"]),
            "ocr_issues": counts["ocr_issues"],
            "duplicate_groups": len(duplicates),
            "conflict_groups": len(conflicts),
            "stale_sources": counts["stale"],
            "legal_status_unverified": counts["legal_unverified"],
            "usable_percent": round((counts["usable_docs"] / total * 100), 1) if total else 0.0,
            "vectorized_percent": round((counts["vectorized_docs"] / total * 100), 1) if total else 0.0,
        },
        "alerts": sorted(alerts, key=lambda a: 0 if a["severity"] == "critical" else 1)[:100],
        "duplicates": duplicates[:30],
        "conflicts": conflicts[:30],
    }


async def coverage_matrix(db: AsyncSession) -> dict[str, Any]:
    docs = await _active_docs(db, include_history=False)
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for doc in docs:
        dimension = dimensao_cobertura(doc)
        if dimension:
            counts[detectar_area(doc)][dimension] += 1

    areas = list(STANDARD_AREAS.keys())
    extras = sorted(area for area in counts if area not in areas and area != "Geral")
    rows = []
    for area in areas + extras + (["Geral"] if counts.get("Geral") else []):
        dims = counts.get(area, Counter())
        present = sum(1 for key in COVERAGE_DIMENSIONS if dims[key] > 0)
        score = round(present / len(COVERAGE_DIMENSIONS) * 100)
        if dims["legislacao"] and dims["jurisprudencia"] and dims["modelos"] and present >= 4:
            status = "boa"
        elif present >= 2:
            status = "atencao"
        else:
            status = "critica"
        rows.append({
            "area": area,
            **{key: int(dims[key]) for key in COVERAGE_DIMENSIONS},
            "score": score,
            "status": status,
            "lacunas": [key for key in COVERAGE_DIMENSIONS if dims[key] == 0],
        })
    rows.sort(key=lambda item: (item["score"], item["area"]))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dimensions": list(COVERAGE_DIMENSIONS),
        "areas": rows,
    }


async def document_details(db: AsyncSession, doc_id: str) -> dict[str, Any] | None:
    doc = (
        await db.execute(
            select(KnowledgeDoc).where(KnowledgeDoc.id == doc_id, KnowledgeDoc.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not doc:
        return None
    metrics = await _chunk_metrics(db)
    metric = metrics.get(doc.id, {"chunks": 0, "chars": 0, "embedded": 0})
    if doc.chave_origem:
        versions = list(
            (
                await db.execute(
                    select(KnowledgeDoc)
                    .where(KnowledgeDoc.chave_origem == doc.chave_origem, KnowledgeDoc.deleted_at.is_(None))
                    .order_by(KnowledgeDoc.versao.desc())
                )
            ).scalars().all()
        )
    else:
        versions = [doc]
    return {
        "id": doc.id,
        "titulo": doc.titulo,
        "categoria": doc.categoria,
        "fonte": doc.fonte,
        "tribunal": doc.tribunal,
        "versao": doc.versao,
        "vigente_no_ejc": bool(doc.vigente),
        "status_indexacao": doc.status_indexacao,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "atualizado_em": doc.atualizado_em.isoformat() if doc.atualizado_em else None,
        "extra": dict(doc.extra or {}),
        "autoridade": inferir_autoridade_documento(doc),
        "situacao_juridica": inferir_situacao_juridica(doc),
        "frescor": avaliar_frescor(doc),
        "qualidade": avaliar_qualidade(doc, chunks=metric["chunks"], chars=metric["chars"], embedded_chunks=metric["embedded"]),
        "metricas": metric,
        "citacao": citacao_estruturada(doc),
        "versoes": [
            {
                "id": version.id,
                "versao": version.versao,
                "vigente": bool(version.vigente),
                "atualizado_em": (version.atualizado_em or version.created_at).isoformat() if (version.atualizado_em or version.created_at) else None,
            }
            for version in versions
        ],
    }


async def _document_text(db: AsyncSession, doc_id: str) -> str:
    chunks = list(
        (
            await db.execute(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.doc_id == doc_id)
                .order_by(KnowledgeChunk.chunk_index)
            )
        ).scalars().all()
    )
    return "\n\n".join(chunk.conteudo for chunk in chunks)


def _legal_sections(text: str) -> dict[str, str]:
    text = (text or "").strip()
    if not text:
        return {}
    matches = list(re.finditer(r"(?im)^\s*(art\.?\s*\d+[\wº°-]*[^\n]*)", text))
    if not matches:
        parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        return {f"bloco_{idx + 1}": part for idx, part in enumerate(parts)}
    sections: dict[str, str] = {}
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        header = _norm(match.group(1))[:120]
        sections[header] = text[start:end].strip()
    return sections


async def compare_versions(
    db: AsyncSession,
    doc_id: str,
    previous_id: str | None = None,
) -> dict[str, Any] | None:
    current = (
        await db.execute(
            select(KnowledgeDoc).where(KnowledgeDoc.id == doc_id, KnowledgeDoc.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not current:
        return None
    previous = None
    if previous_id:
        previous = (
            await db.execute(
                select(KnowledgeDoc).where(KnowledgeDoc.id == previous_id, KnowledgeDoc.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
    elif current.versao_anterior_id:
        previous = (
            await db.execute(select(KnowledgeDoc).where(KnowledgeDoc.id == current.versao_anterior_id))
        ).scalar_one_or_none()
    elif current.chave_origem and current.versao and current.versao > 1:
        previous = (
            await db.execute(
                select(KnowledgeDoc)
                .where(
                    KnowledgeDoc.chave_origem == current.chave_origem,
                    KnowledgeDoc.versao < current.versao,
                    KnowledgeDoc.deleted_at.is_(None),
                )
                .order_by(KnowledgeDoc.versao.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if not previous:
        return {
            "current": {"id": current.id, "titulo": current.titulo, "versao": current.versao},
            "previous": None,
            "available": False,
            "detail": "Não existe versão anterior disponível para comparação.",
        }

    current_text = await _document_text(db, current.id)
    previous_text = await _document_text(db, previous.id)
    current_sections = _legal_sections(current_text)
    previous_sections = _legal_sections(previous_text)
    added_keys = [key for key in current_sections if key not in previous_sections]
    removed_keys = [key for key in previous_sections if key not in current_sections]
    changed = []
    for key in current_sections.keys() & previous_sections.keys():
        before = previous_sections[key]
        after = current_sections[key]
        ratio = SequenceMatcher(None, before, after).ratio()
        if ratio < 0.995:
            changed.append({
                "secao": key,
                "similaridade": round(ratio, 4),
                "antes": before[:900],
                "depois": after[:900],
            })
    return {
        "available": True,
        "current": {"id": current.id, "titulo": current.titulo, "versao": current.versao},
        "previous": {"id": previous.id, "titulo": previous.titulo, "versao": previous.versao},
        "summary": {
            "secoes_adicionadas": len(added_keys),
            "secoes_removidas": len(removed_keys),
            "secoes_alteradas": len(changed),
            "similaridade_global": round(SequenceMatcher(None, previous_text, current_text).ratio(), 4),
        },
        "added": [{"secao": key, "texto": current_sections[key][:900]} for key in added_keys[:100]],
        "removed": [{"secao": key, "texto": previous_sections[key][:900]} for key in removed_keys[:100]],
        "changed": sorted(changed, key=lambda item: item["similaridade"])[:100],
    }


async def test_document_retrieval(
    db: AsyncSession,
    doc_id: str,
    question: str | None = None,
    limit: int = 8,
) -> dict[str, Any] | None:
    doc = (
        await db.execute(
            select(KnowledgeDoc).where(KnowledgeDoc.id == doc_id, KnowledgeDoc.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not doc:
        return None
    if doc.categoria in {"peca_interna", "peca_escritorio", "precedente_interno", "comunicacao_processual"} and doc.client_id:
        return {
            "documento_id": doc.id,
            "pergunta": question,
            "recuperado": False,
            "detail": "Documento restrito: o teste deve ser executado dentro do caso/cliente correspondente.",
            "resultados": [],
        }
    query = (question or f"{doc.titulo} {doc.tribunal or ''}").strip()
    from app.services.ai_service import buscar_contexto_rag

    results = await buscar_contexto_rag(
        db,
        query,
        limite=max(1, min(limit, 20)),
        categorias=[doc.categoria],
        incluir_historico=not bool(doc.vigente),
    )
    rank = next((idx + 1 for idx, item in enumerate(results) if item.get("doc_id") == doc.id), None)
    target_hits = [item for item in results if item.get("doc_id") == doc.id]
    return {
        "documento_id": doc.id,
        "titulo": doc.titulo,
        "pergunta": query,
        "recuperado": rank is not None,
        "posicao": rank,
        "top_score": max((float(item.get("score") or item.get("rerank_score") or 0) for item in target_hits), default=None),
        "pipeline": "hibrida_governada",
        "citacao": citacao_estruturada(doc),
        "resultados": results,
        "diagnostico": (
            "Documento recuperado pelo mesmo pipeline utilizado pela IA."
            if rank is not None
            else "Documento não apareceu no conjunto recuperado; revisar título, conteúdo, chunks e embeddings."
        ),
    }


async def run_legal_smoke_tests(db: AsyncSession) -> dict[str, Any]:
    from app.services.ai_service import buscar_contexto_rag

    results = []
    for test in LEGAL_SMOKE_TESTS:
        hits = await buscar_contexto_rag(db, test["pergunta"], limite=5)
        combined = _norm(" ".join(str(hit.get("conteudo") or "") for hit in hits))
        matched_terms = [term for term in test["termos"] if _norm(term) in combined]
        passed = bool(hits and matched_terms)
        results.append({
            "id": test["id"],
            "pergunta": test["pergunta"],
            "status": "aprovado" if passed else "falhou",
            "fontes_encontradas": len(hits),
            "termos_confirmados": matched_terms,
            "top_resultados": hits[:3],
        })
    approved = sum(1 for item in results if item["status"] == "aprovado")
    return {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "approved": approved,
        "failed": len(results) - approved,
        "score_percent": round(approved / len(results) * 100, 1) if results else 0.0,
        "status": "saudavel" if approved == len(results) else "atencao",
        "tests": results,
    }
