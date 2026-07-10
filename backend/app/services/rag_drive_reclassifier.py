# ── app/services/rag_drive_reclassifier.py ───────────────────────────────────
# Reclassificação segura de documentos Google Drive já ingeridos no RAG.
#
# Desenho operacional:
# - dry-run por padrão;
# - escopo restrito a knowledge_docs vindos do Google Drive;
# - nenhuma exclusão física;
# - arquivos sinalizados como teste/rascunho/backup são retirados da vigência
#   somente quando apply=True, preservando histórico e rollback;
# - metadados de auditoria ficam em extra.taxonomy e extra.reclassification.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import KnowledgeDoc
from app.services.google_drive_taxonomy import DriveTaxonomyDecision, classificar_drive_file


@dataclass(frozen=True, slots=True)
class ReclassificacaoResultado:
    doc_id: str
    titulo: str
    chave_origem: str | None
    categoria_atual: str
    categoria_sugerida: str
    categoria_final: str
    vigente_atual: bool
    vigente_final: bool
    alteraria: bool
    aplicado: bool
    motivo: str
    prioridade: int
    tipo_fonte: str
    area_juridica: str | None
    sinais: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "titulo": self.titulo,
            "chave_origem": self.chave_origem,
            "categoria_atual": self.categoria_atual,
            "categoria_sugerida": self.categoria_sugerida,
            "categoria_final": self.categoria_final,
            "vigente_atual": self.vigente_atual,
            "vigente_final": self.vigente_final,
            "alteraria": self.alteraria,
            "aplicado": self.aplicado,
            "motivo": self.motivo,
            "prioridade": self.prioridade,
            "tipo_fonte": self.tipo_fonte,
            "area_juridica": self.area_juridica,
            "sinais": self.sinais,
        }


def _extra_dict(doc: KnowledgeDoc) -> dict[str, Any]:
    return dict(doc.extra or {})


def _drive_meta(doc: KnowledgeDoc) -> dict[str, Any]:
    extra = _extra_dict(doc)
    drive = extra.get("drive")
    return dict(drive or {}) if isinstance(drive, dict) else {}


def is_google_drive_doc(doc: KnowledgeDoc) -> bool:
    extra = _extra_dict(doc)
    if extra.get("source") == "google_drive":
        return True
    if (doc.chave_origem or "").startswith("gdrive:"):
        return True
    return False


def classificar_doc_rag_drive(doc: KnowledgeDoc) -> DriveTaxonomyDecision:
    drive = _drive_meta(doc)
    nome = str(drive.get("name") or doc.titulo or doc.id)
    caminho = str(drive.get("full_path") or drive.get("path") or "")
    mime_type = str(drive.get("mime_type_original") or "")
    return classificar_drive_file(nome, caminho, mime_type)


def _merge_extra_reclassificacao(
    doc: KnowledgeDoc,
    decisao: DriveTaxonomyDecision,
    *,
    categoria_anterior: str,
    vigente_anterior: bool,
    categoria_final: str,
    vigente_final: bool,
    applied_at: str,
) -> dict[str, Any]:
    extra = _extra_dict(doc)
    extra["taxonomy"] = decisao.as_extra()
    extra["confidence_level"] = decisao.confianca
    historico = extra.get("reclassification_history")
    if not isinstance(historico, list):
        historico = []
    historico.append({
        "source": "rag_drive_reclassifier",
        "applied_at": applied_at,
        "categoria_anterior": categoria_anterior,
        "categoria_final": categoria_final,
        "vigente_anterior": vigente_anterior,
        "vigente_final": vigente_final,
        "motivo": decisao.motivo,
        "sinais": decisao.sinais,
    })
    # Limita crescimento do JSONB sem apagar a última trilha relevante.
    extra["reclassification_history"] = historico[-10:]
    extra["reclassification"] = {
        "source": "rag_drive_reclassifier",
        "last_applied_at": applied_at,
        "categoria_anterior": categoria_anterior,
        "categoria_final": categoria_final,
        "vigente_anterior": vigente_anterior,
        "vigente_final": vigente_final,
    }
    return extra


def _build_resultado(
    doc: KnowledgeDoc,
    decisao: DriveTaxonomyDecision,
    *,
    apply: bool,
) -> ReclassificacaoResultado:
    categoria_final = decisao.categoria
    vigente_atual = bool(doc.vigente)
    # Documento marcado como teste/rascunho não é removido; sai da vigência para
    # não alimentar busca RAG padrão. Rollback é simples: restaurar vigente=True
    # e/ou categoria anterior via histórico em extra.reclassification_history.
    vigente_final = False if decisao.excluir else vigente_atual
    alteraria = (doc.categoria != categoria_final) or (vigente_atual != vigente_final)
    return ReclassificacaoResultado(
        doc_id=doc.id,
        titulo=doc.titulo,
        chave_origem=doc.chave_origem,
        categoria_atual=doc.categoria,
        categoria_sugerida=decisao.categoria,
        categoria_final=categoria_final,
        vigente_atual=vigente_atual,
        vigente_final=vigente_final,
        alteraria=alteraria,
        aplicado=apply and alteraria,
        motivo=decisao.motivo,
        prioridade=decisao.prioridade,
        tipo_fonte=decisao.tipo_fonte,
        area_juridica=decisao.area_juridica,
        sinais=decisao.sinais,
    )


async def listar_docs_drive(db: AsyncSession, *, limit: int | None = None) -> list[KnowledgeDoc]:
    stmt = (
        select(KnowledgeDoc)
        .where(KnowledgeDoc.deleted_at.is_(None))
        .where(
            (KnowledgeDoc.chave_origem.like("gdrive:%"))
            | (KnowledgeDoc.extra["source"].astext == "google_drive")
        )
        .order_by(KnowledgeDoc.created_at.desc())
    )
    if limit:
        stmt = stmt.limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def reclassificar_docs_drive(
    db: AsyncSession,
    *,
    apply: bool = False,
    limit: int | None = None,
    only_changes: bool = False,
) -> dict[str, Any]:
    docs = await listar_docs_drive(db, limit=limit)
    resultados: list[ReclassificacaoResultado] = []
    applied_at = datetime.now(timezone.utc).isoformat()

    for doc in docs:
        if not is_google_drive_doc(doc):
            continue
        decisao = classificar_doc_rag_drive(doc)
        item = _build_resultado(doc, decisao, apply=apply)
        if only_changes and not item.alteraria:
            continue
        resultados.append(item)

        if apply and item.alteraria:
            doc.extra = _merge_extra_reclassificacao(
                doc,
                decisao,
                categoria_anterior=doc.categoria,
                vigente_anterior=bool(doc.vigente),
                categoria_final=item.categoria_final,
                vigente_final=item.vigente_final,
                applied_at=applied_at,
            )
            doc.categoria = item.categoria_final
            doc.vigente = item.vigente_final
            doc.atualizado_em = datetime.now(timezone.utc)

    if apply:
        await db.commit()
    else:
        await db.rollback()

    por_categoria: dict[str, int] = {}
    por_tipo: dict[str, int] = {}
    por_area: dict[str, int] = {}
    alterariam = aplicados = 0
    for item in resultados:
        if item.alteraria:
            alterariam += 1
        if item.aplicado:
            aplicados += 1
        por_categoria[item.categoria_final] = por_categoria.get(item.categoria_final, 0) + 1
        por_tipo[item.tipo_fonte] = por_tipo.get(item.tipo_fonte, 0) + 1
        area = item.area_juridica or "nao_identificada"
        por_area[area] = por_area.get(area, 0) + 1

    return {
        "modo": "apply" if apply else "dry_run",
        "total_docs_drive_lidos": len(docs),
        "total_resultados": len(resultados),
        "total_alterariam": alterariam,
        "total_aplicados": aplicados,
        "por_categoria_final": por_categoria,
        "por_tipo_fonte": por_tipo,
        "por_area_juridica": por_area,
        "resultados": [item.as_dict() for item in resultados],
        "observacao": (
            "Dry-run não altera o banco. Apply atualiza categoria, taxonomy e, "
            "quando a taxonomia indicar exclusão operacional, marca vigente=false "
            "sem excluir fisicamente o documento."
        ),
    }
