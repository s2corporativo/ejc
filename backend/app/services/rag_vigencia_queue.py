"""Fila read-only de normas públicas cuja vigência ainda exige conferência.

A fila não promove metadados, não aceita decisão em lote e não devolve conteúdo
jurídico/chunks. A decisão continua no fluxo administrativo individual de
``rag_governance``, com ator autorizado e AuditLog.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import BaseRag, KnowledgeDoc
from app.services.knowledge_governance import (
    inferir_autoridade_documento,
    inferir_situacao_juridica,
)


def _normalizar(valor: Any) -> str:
    """Normaliza metadado textual sem inferir conteúdo jurídico."""
    return " ".join(str(valor or "").strip().lower().split())


def vigencia_normativa_confirmada(extra: dict[str, Any] | None) -> bool:
    """Exige prova positiva de vigência; mera origem oficial não basta."""
    dados = dict(extra or {})
    status = _normalizar(dados.get("legal_status"))
    origem = str(dados.get("legal_status_origem") or "").strip()
    verificado_em = str(dados.get("legal_status_verificado_em") or "").strip()
    inferido_em = str(dados.get("legal_status_inferido_em") or "").strip()
    return bool(
        status == "vigente"
        and origem
        and verificado_em
        and not inferido_em
    )


def eh_pendencia_vigencia(doc: KnowledgeDoc) -> bool:
    """Seleciona somente norma pública atual que exige conferência humana."""
    categoria = _normalizar(getattr(doc, "categoria", None))
    if "propos" in categoria:
        return False
    if not any(token in categoria for token in ("legisl", "norma", "regulamento")):
        return False

    base_raw = getattr(doc, "base_rag", None)
    base = getattr(base_raw, "value", base_raw)
    if str(base or "") != BaseRag.publica.value:
        return False
    if not bool(getattr(doc, "vigente", False)):
        return False
    if getattr(doc, "deleted_at", None) is not None:
        return False
    if (
        getattr(doc, "client_id", None) is not None
        or getattr(doc, "case_id", None) is not None
    ):
        return False
    return not vigencia_normativa_confirmada(getattr(doc, "extra", None))


def _data_iso(valor: Any) -> str | None:
    """Serializa datas da fila sem incluir conteúdo documental."""
    return valor.isoformat() if hasattr(valor, "isoformat") else None


async def listar_pendencias_vigencia(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Retorna fila paginada de legislação pública ainda não comprovada.

    O primeiro recorte já ocorre no banco (público, global, ativo, legislação).
    O predicado Python repete as invariantes de segurança e exige prova positiva
    de vigência. O volume esperado é pequeno e a dupla checagem evita que uma
    evolução de query transforme conteúdo privado/histórico em fila administrativa.
    """
    docs = list(
        (
            await db.execute(
                select(KnowledgeDoc)
                .where(
                    KnowledgeDoc.deleted_at.is_(None),
                    KnowledgeDoc.vigente.is_(True),
                    KnowledgeDoc.client_id.is_(None),
                    KnowledgeDoc.case_id.is_(None),
                    KnowledgeDoc.base_rag == BaseRag.publica,
                    KnowledgeDoc.categoria.ilike("%legisl%"),
                )
                .order_by(
                    KnowledgeDoc.chave_origem.asc().nullslast(),
                    KnowledgeDoc.titulo.asc(),
                )
            )
        ).scalars().all()
    )
    pendentes = [doc for doc in docs if eh_pendencia_vigencia(doc)]
    total = len(pendentes)
    inicio = max(0, (page - 1) * page_size)
    pagina = pendentes[inicio : inicio + page_size]

    data: list[dict[str, Any]] = []
    for doc in pagina:
        extra = dict(doc.extra or {})
        origem = str(extra.get("legal_status_origem") or "").strip()
        if origem.startswith("curadoria:"):
            origem = "curadoria"
        data.append(
            {
                "id": str(doc.id),
                "titulo": doc.titulo,
                "categoria": doc.categoria,
                "chave_origem": doc.chave_origem,
                "versao": doc.versao,
                "situacao_juridica": inferir_situacao_juridica(doc),
                "autoridade": inferir_autoridade_documento(doc),
                "origem_vigencia": origem or None,
                "possui_verificacao": bool(
                    str(extra.get("legal_status_verificado_em") or "").strip()
                ),
                "possui_inferencia": bool(
                    str(extra.get("legal_status_inferido_em") or "").strip()
                ),
                "atualizado_em": _data_iso(doc.atualizado_em or doc.created_at),
            }
        )

    return {
        "data": data,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
