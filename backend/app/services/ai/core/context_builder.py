# ── app/services/ai/core/context_builder.py ──────────────────────────────────
# BUILDER DE CONTEXTO do Núcleo Único de IA.
#
# O frontend envia apenas IDs + pergunta; o contexto REAL é montado AQUI, no
# backend, já sob RBAC/ownership (validados antes, no orchestrator):
#   • caso      → case_context.montar_dossie (texto sanitizado + nomes a proteger);
#   • documento → Document.ocr_text (GED) — documentos de cofre (confidencialidade
#     restrito/sigiloso) NUNCA entram em prompt de IA;
#   • processo  → metadados do Process (número CNJ mascarado pela sanitização);
#   • RAG       → ai_service.buscar_contexto_rag (base de conhecimento, com fontes).
# Tudo truncado para caber no orçamento de prompt.
from __future__ import annotations
from dataclasses import dataclass, field

# Orçamentos de caracteres por bloco (prompt enxuto e previsível).
_MAX_DOSSIE = 8000
_MAX_DOC = 6000
_MAX_RAG_CHUNK = 900
_LIMITE_RAG = 6


@dataclass
class ContextoMontado:
    texto: str = ""                                  # blocos prontos p/ prompt
    fontes: list[dict] = field(default_factory=list)  # chunks RAG (p/ citação)
    nomes_proteger: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)   # lacunas (ex.: doc de cofre)


def _trunca(texto: str, limite: int) -> str:
    texto = texto or ""
    if len(texto) <= limite:
        return texto
    return texto[:limite] + "\n[... truncado para caber no contexto ...]"


async def montar_contexto(
    db,
    *,
    mensagem: str,
    case_id: str | None = None,
    document_id: str | None = None,
    process_id: str | None = None,
    usar_rag: bool = True,
    exige_fonte: bool = False,
) -> ContextoMontado:
    ctx = ContextoMontado()
    if db is None:
        return ctx
    blocos: list[str] = []

    # ── Caso (dossiê sanitizado) ─────────────────────────────────────────────
    if case_id:
        from app.services.case_context import montar_dossie
        dossie = await montar_dossie(db, case_id, sanitizar=True)
        if dossie:
            blocos.append(_trunca(dossie.get("texto", ""), _MAX_DOSSIE))
            ctx.nomes_proteger = dossie.get("nomes_proteger") or []
        else:
            ctx.avisos.append("Caso não encontrado — contexto do caso omitido.")

    # ── Documento (GED) ──────────────────────────────────────────────────────
    if document_id:
        from sqlalchemy import select
        from app.models.document import Document, DocConfidencialidade
        doc = (await db.execute(
            select(Document).where(Document.id == document_id,
                                   Document.deleted_at.is_(None))
        )).scalar_one_or_none()
        if doc is None:
            ctx.avisos.append("Documento não encontrado — contexto documental omitido.")
        elif doc.confidencialidade not in (DocConfidencialidade.normal,
                                           DocConfidencialidade.interno):
            # Cofre (>= restrito): documento sigiloso jamais vira prompt de IA.
            ctx.avisos.append(
                "Documento em confidencialidade elevada (cofre) — conteúdo NÃO "
                "enviado à IA por política de sigilo."
            )
        elif not (doc.ocr_text or "").strip():
            ctx.avisos.append("Documento sem texto extraído (OCR pendente).")
        else:
            blocos.append(
                f"[DOCUMENTO] {doc.titulo} (tipo: {doc.tipo or 'não classificado'})\n"
                + _trunca(doc.ocr_text, _MAX_DOC)
            )

    # ── Processo (metadados) ─────────────────────────────────────────────────
    if process_id:
        from sqlalchemy import select
        from app.models.process import Process
        proc = (await db.execute(
            select(Process).where(Process.id == process_id)
        )).scalar_one_or_none()
        if proc is None:
            ctx.avisos.append("Processo não encontrado — contexto processual omitido.")
        else:
            partes = [f"[PROCESSO] status: {getattr(proc, 'status', '?')}"]
            for campo in ("tribunal", "vara", "comarca", "fase", "instancia", "rito"):
                valor = getattr(proc, campo, None)
                if valor:
                    partes.append(f"{campo}: {valor}")
            # numero_cnj propositalmente OMITIDO: é PII estrutural (sanitização
            # o mascararia de toda forma) e não agrega à análise.
            blocos.append(" | ".join(partes))

    # ── RAG (base de conhecimento com fontes) ────────────────────────────────
    if usar_rag or exige_fonte:
        from app.services.ai_service import buscar_contexto_rag
        try:
            ctx.fontes = await buscar_contexto_rag(db, mensagem, limite=_LIMITE_RAG)
        except Exception:
            ctx.fontes = []
            ctx.avisos.append("Busca RAG indisponível — resposta sem base interna.")
        if ctx.fontes:
            linhas = ["[FONTES — BASE DE CONHECIMENTO INTERNA]"]
            for i, f in enumerate(ctx.fontes, 1):
                titulo = f.get("titulo") or "sem título"
                categoria = f.get("categoria") or ""
                trecho = _trunca(f.get("conteudo") or "", _MAX_RAG_CHUNK)
                linhas.append(f"[Fonte {i}] {titulo}"
                              + (f" ({categoria})" if categoria else "") + f"\n{trecho}")
            blocos.append("\n\n".join(linhas))

    ctx.texto = "\n\n---\n\n".join(b for b in blocos if b.strip())
    return ctx
