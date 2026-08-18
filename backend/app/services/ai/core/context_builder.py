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

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("ejc.ai.core.context")

# Orçamentos de caracteres por bloco (prompt enxuto e previsível).
_MAX_DOSSIE = 24000
_MAX_DOC = 18000
_MAX_RAG_CHUNK = 2000
_LIMITE_RAG = 10


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


async def _acesso_caso_ok(db, user, alvo_case_id: str) -> bool:
    """Prova (fail-closed) que `user` pode acessar `alvo_case_id`.

    Reusa o gate canônico `verificar_acesso_caso` (mesma regra RBAC/ABAC e a
    mesma exceção do projeto), convertendo o 403/404 em False para o chamador
    apenas OMITIR o trecho — sem vazar existência do recurso cross-tenant.
    Sem `user` autenticado não há como provar o vínculo → nega.
    """
    if user is None or not alvo_case_id:
        return False
    from fastapi import HTTPException
    from app.core.ownership import verificar_acesso_caso
    try:
        await verificar_acesso_caso(db, user, alvo_case_id)
        return True
    except HTTPException:
        return False


async def _documento_autorizado(db, user, doc, case_id: str | None) -> bool:
    """Ownership de DOCUMENTO antes de injetar seu conteúdo no prompt (IDOR guard).

    - Vínculo por caso é a fonte primária: se o contexto trouxe `case_id`, o
      documento TEM de ser daquele caso (bloqueia doc de outro caso/cliente);
      além disso, prova o acesso do usuário ao caso do próprio documento.
    - Documento sem caso: só gestão ou o próprio uploader (fail-closed p/ o
      resto — validação por cliente sem caso fica em routers.documents._verificar_
      acesso_documento; não importável aqui sem acoplar service→router).
    """
    doc_case = getattr(doc, "case_id", None)
    if doc_case:
        if case_id and doc_case != case_id:
            return False
        return await _acesso_caso_ok(db, user, doc_case)
    if user is None:
        return False
    from app.core.ownership import is_gestao
    if is_gestao(user):
        return True
    uploader = getattr(doc, "uploaded_by", None)
    return bool(uploader) and uploader == getattr(user, "id", None)


async def _processo_autorizado(db, user, proc, case_id: str | None) -> bool:
    """Ownership de PROCESSO (Process.case_id é NOT NULL) antes do prompt."""
    proc_case = getattr(proc, "case_id", None)
    if not proc_case:
        return False
    if case_id and proc_case != case_id:
        return False
    return await _acesso_caso_ok(db, user, proc_case)


async def montar_contexto(
    db,
    *,
    mensagem: str,
    case_id: str | None = None,
    document_id: str | None = None,
    process_id: str | None = None,
    user=None,
    usar_rag: bool = True,
    exige_fonte: bool = False,
) -> ContextoMontado:
    ctx = ContextoMontado()
    if db is None:
        return ctx
    blocos: list[str] = []
    scope_client_id: str | None = None

    # ── Caso (dossiê sanitizado) ─────────────────────────────────────────────
    if case_id:
        from app.services.case_context import montar_dossie
        dossie = await montar_dossie(db, case_id, sanitizar=True)
        if dossie:
            blocos.append(_trunca(dossie.get("texto", ""), _MAX_DOSSIE))
            ctx.nomes_proteger = dossie.get("nomes_proteger") or []
            # O RAG restrito é client-scoped. Sem este escopo, o filtro
            # fail-closed exclui justamente precedentes internos, peças e
            # comunicações do próprio cliente, deixando o Núcleo Único sem a
            # memória institucional que deveria utilizar. Acesso ao caso já foi
            # provado pelo orchestrator; ainda assim, a resolução consulta apenas
            # caso ativo e nunca aceita client_id vindo do frontend.
            from app.services.ai_service import _escopo_cliente_do_caso
            scope_client_id = await _escopo_cliente_do_caso(db, case_id)
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
        elif not await _documento_autorizado(db, user, doc, case_id):
            # IDOR guard: doc de outro caso/cliente (ou vínculo não provável)
            # é tratado como INEXISTENTE — mesma mensagem, sem vazar existência.
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
        elif not await _processo_autorizado(db, user, proc, case_id):
            # IDOR guard: processo de outro caso/cliente → tratado como inexistente.
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
            ctx.fontes = await buscar_contexto_rag(
                db,
                mensagem,
                limite=_LIMITE_RAG,
                scope_client_id=scope_client_id,
            )
        except Exception as exc:
            ctx.fontes = []
            ctx.avisos.append("Busca RAG indisponível — resposta sem base interna.")
            # Observabilidade segura: registra apenas a classe, nunca consulta,
            # contexto ou detalhe de banco que possa conter PII.
            logger.warning("Busca RAG do context builder falhou: %s", type(exc).__name__)
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
