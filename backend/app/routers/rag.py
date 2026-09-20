# ── app/routers/rag.py ───────────────────────────────────────────────────────
# Base de conhecimento RAG: ingestão de docs + consulta.
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select, update, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionLocal
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, require_roles, requer_equipe_juridica
from app.models.user import User
from app.models.audit_log import criar_audit_log
from app.models.rag import KnowledgeDoc, KnowledgeChunk, FonteIngestao
from app.services.ai_service import buscar_contexto_rag, _RESTRICTED_CATS
from app.services.embedding_service import gerar_embeddings, disponivel as emb_disponivel
# Chunker ÚNICO do RAG (heurística de fronteira de frase) — o mesmo usado pela
# ingestão automática (ingestion_service). Evita qualidade de recuperação
# divergente entre ingestão manual e automática.
from app.services.ingestion_service import chunk_texto
# Vocabulário canônico de confiança da governança de IA (alta|media|baixa|bloqueado).
from app.routers.ia_governanca import Confianca
# Dispatcher único de indexação (Fase 3A): Celery quando habilitado/alcançável,
# senão BackgroundTasks (comportamento idêntico ao anterior com CELERY_ENABLED=False).
from app.tasks.dispatcher import agendar_indexacao
from app.schemas.common import MsgResponse

logger = logging.getLogger("ejc.rag")

router = APIRouter(prefix="/rag", tags=["Base de Conhecimento"])


@router.get("/stats")
async def stats_conhecimento(db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    """Contagens da base de conhecimento (dashboard de Conhecimento)."""
    from sqlalchemy import text as _t
    # Dashboard reporta o CORPUS OPERACIONAL: somente versão vigente e não
    # excluída. Histórico continua preservado para auditoria, mas não pode
    # parecer "chunk sem vetor" do RAG atual.
    total_docs = (await db.execute(_t(
        "SELECT count(*) FROM knowledge_docs "
        "WHERE deleted_at IS NULL AND vigente = TRUE"
    ))).scalar() or 0
    total_chunks = (await db.execute(_t(
        "SELECT count(*) FROM knowledge_chunks kc "
        "JOIN knowledge_docs kd ON kd.id = kc.doc_id "
        "WHERE kd.deleted_at IS NULL AND kd.vigente = TRUE"
    ))).scalar() or 0
    com_emb = (await db.execute(_t(
        "SELECT count(*) FROM knowledge_chunks kc "
        "JOIN knowledge_docs kd ON kd.id = kc.doc_id "
        "WHERE kd.deleted_at IS NULL AND kd.vigente = TRUE "
        "AND kc.embedding IS NOT NULL"
    ))).scalar() or 0
    rows = (await db.execute(_t(
        "SELECT categoria, count(*) AS n FROM knowledge_docs "
        "WHERE deleted_at IS NULL AND vigente = TRUE "
        "GROUP BY categoria ORDER BY n DESC"
    ))).all()
    return {
        "total_docs": total_docs, "total_chunks": total_chunks, "chunks_indexados": com_emb,
        "por_categoria": [{"categoria": r[0] or "outros", "total": r[1]} for r in rows],
    }


@router.get("/status")
async def status_indexacao_rag(
    db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)
):
    """BUG-04: estado real da vetorização da base RAG.

    Deriva de `knowledge_docs.status_indexacao` (indexado→vetorizado). Não
    re-embeda nada — apenas reporta. Usado pelo painel de Conhecimento.
    """
    from sqlalchemy import text as _t
    rows = (await db.execute(_t(
        "SELECT status_indexacao AS s, count(*) AS n "
        "FROM knowledge_docs WHERE deleted_at IS NULL AND vigente = TRUE "
        "GROUP BY status_indexacao"
    ))).all()
    vetorizado = sem_vetor = erro = 0
    for s, n in rows:
        if s == "indexado":
            vetorizado += n
        elif s == "erro":
            erro += n
        else:  # pendente | sem_embeddings | NULL
            sem_vetor += n
    return {
        "vetorizado": vetorizado,
        "sem_vetor": sem_vetor,
        "erro": erro,
        "total": vetorizado + sem_vetor + erro,
    }


class IngestRequest(BaseModel):
    titulo: str
    categoria: str   # legislacao_geral|legislacao_ambiental|legislacao_administrativa|legislacao_trabalhista|legislacao_tributaria|legislacao_bancaria|sumula_tjmg|sumula_stf|sumula_stj|sumula_tst|jurisprudencia_tjmg|jurisprudencia_stj|jurisprudencia_tst|jurisprudencia_carf|jurisprudencia_tcu|precedente_interno|doutrina|tese_vitoriosa|modelo_documento_juridico
    conteudo: str
    fonte: Optional[str] = None
    tribunal: Optional[str] = None
    # Gate de confiança na entrada (mesmo vocabulário da curadoria de governança;
    # persiste em extra["confidence_level"], lido por ia_governanca._conf).
    confianca: Confianca = "media"


import re as _re
import hashlib as _hashlib


def _chave_ingestao_manual(*, actor_id: str, titulo: str, categoria: str,
                           fonte: str | None, tribunal: str | None) -> str:
    """Identidade estável por origem lógica, sem incluir o conteúdo."""
    identidade = "\x1f".join(
        (actor_id, categoria.strip().lower(), (tribunal or "").strip().lower(),
         titulo.strip().lower(), (fonte or "manual").strip())
    )
    return f"manual:{actor_id}:{_hashlib.sha256(identidade.encode()).hexdigest()[:40]}"


async def _ingerir_texto(db, background_tasks, titulo, categoria, conteudo,
                         fonte=None, tribunal=None, confianca: str = "media",
                         extra_doc: Optional[dict] = None,
                         paginas: Optional[list[dict]] = None,
                         actor_id: str = ""):
    """Núcleo de ingestão reutilizado por /ingest, /ingest-pdf e /ingest-url.

    `extra_doc`: chaves adicionais mescladas no JSONB `extra` do documento
    (ex.: extração estruturada do OCR em extra["extracao"])."""
    if len(conteudo.strip()) < 50:
        raise HTTPException(status_code=422, detail="Conteúdo extraído muito curto (< 50 caracteres)")
    if categoria in _RESTRICTED_CATS:
        raise HTTPException(
            status_code=422,
            detail=("Conteúdo de cliente/caso exige o fluxo dedicado com escopo e "
                    "autorização; a ingestão manual geral aceita apenas fontes públicas."),
        )
    extra = {}
    if extra_doc:
        extra.update(extra_doc)
    extra.update({
        "confidence_level": confianca,
        "rag_status": "pendente",
        "ingestao_manual": True,
        "ingerido_por": actor_id,
    })
    chave = _chave_ingestao_manual(
        actor_id=actor_id, titulo=titulo, categoria=categoria,
        fonte=fonte, tribunal=tribunal,
    )
    from app.services.ingestion_service import upsert_documento
    from app.services.legal_chunker import chunks_para_ingestao
    # C5: categoria jurídica (legislacao*/sumula*/jurisprudencia*/doutrina) →
    # chunker por artigo/heading com teto = janela do modelo. PDF com páginas
    # mantém o chunking por página (origem da citação); demais → corte por
    # tamanho dentro do upsert. hash_conteudo não muda (é do documento inteiro).
    chunks_juridicos = None if paginas else chunks_para_ingestao(conteudo, categoria)
    resultado = await upsert_documento(
        db, titulo=titulo, categoria=categoria, conteudo=conteudo,
        chave_origem=chave, fonte=fonte, tribunal=tribunal, extra=extra,
        confianca=confianca, embutir_vetores=False, paginas=paginas,
        chunks=chunks_juridicos,
    )
    doc = (await db.execute(select(KnowledgeDoc).where(
        KnowledgeDoc.chave_origem == chave,
        KnowledgeDoc.deleted_at.is_(None),
        KnowledgeDoc.vigente.is_(True),
    ).order_by(KnowledgeDoc.created_at.desc()).limit(1))).scalars().first()
    if doc is None:
        raise HTTPException(status_code=500,
            detail="Documento ingerido não localizado após o upsert")
    await db.commit()
    if emb_disponivel() and doc.status_indexacao != "indexado":
        await agendar_indexacao(doc.id, background_tasks)
    chunks = chunk_texto(conteudo)
    rag_status = (doc.extra or {}).get("rag_status", "pendente")
    detalhe = (f"Documento ingerido ({len(chunks)} trechos). " +
               ("A aprovação anterior foi preservada."
                if rag_status == "aprovado" else
                "Colocado em revisão; ainda não fundamenta respostas da IA."))
    return {"id": doc.id, "chunks": len(chunks), "status_indexacao": doc.status_indexacao,
            "resultado_upsert": resultado, "rag_status": rag_status,
            "confianca": confianca,
            "embeddings_pendentes": emb_disponivel(),
            "detail": detalhe}


def _validar_pdf_upload(raw: bytes, max_mb: int) -> None:
    """Guarda pura do ingest-pdf (testável sem banco, padrão _validar_avatar):
    teto de tamanho no app + assinatura %PDF antes do parse/OCR CPU-bound."""
    if len(raw) > max_mb * 1024 * 1024:
        raise HTTPException(413, f"PDF excede o limite de {max_mb}MB")
    if not raw.startswith(b"%PDF-"):
        raise HTTPException(422, "Arquivo não é um PDF válido (assinatura ausente)")


@router.post("/ingest-pdf", status_code=201)
async def ingerir_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    titulo: str = Form(...),
    categoria: str = Form(...),
    tribunal: Optional[str] = Form(None),
    confianca: Confianca = Form("media"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio", "advogado"])),
):
    """Extrai texto de um PDF e ingere na base RAG.

    Fase 3A: usa ocr_service (texto nativo PyMuPDF + OCR Tesseract nas páginas
    escaneadas — antes, PDF escaneado virava texto vazio) e grava a extração
    estruturada determinística (CNJ/CPF/CNPJ/datas/valores/e-mails/telefones)
    em `extra["extracao"]`.
    """
    from app.services.ocr_service import extrair_texto_pdf
    from app.services.extracao_estruturada import extrair_estruturas
    import asyncio as _asyncio
    # Pente fino 2026-07-25: teto de leitura no app (não confiar só no nginx) e
    # magic bytes ANTES de entregar o buffer ao parser/OCR (CPU-bound).
    from app.core.config import get_settings
    max_mb = get_settings().MAX_UPLOAD_MB
    raw = await file.read(max_mb * 1024 * 1024 + 1)
    _validar_pdf_upload(raw, max_mb)
    try:
        # OCR é CPU-bound (renderização + tesseract) → thread para não travar o loop
        res = await _asyncio.to_thread(extrair_texto_pdf, raw)
    except ValueError as e:
        raise HTTPException(422, str(e))
    texto = res["texto"]
    extracao = extrair_estruturas(texto)
    return await _ingerir_texto(
        db, background_tasks, titulo, categoria, texto,
        fonte=file.filename, tribunal=tribunal, confianca=confianca,
        extra_doc={
            "extracao": extracao,
            "ocr": {"paginas": res["paginas"], "paginas_ocr": res["paginas_ocr"],
                    "ocr_disponivel": res["ocr_disponivel"]},
        },
        paginas=res.get("por_pagina"),
        actor_id=str(cu.id),
    )


@router.post("/ingest-url", status_code=201)
async def ingerir_url(
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    titulo: str = Form(...),
    categoria: str = Form(...),
    tribunal: Optional[str] = Form(None),
    confianca: Confianca = Form("media"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio", "advogado"])),
):
    """Busca uma URL pública, extrai o texto (remove HTML) e ingere na base RAG."""
    import httpx
    # SSRF: reutiliza o mesmo validador anti-SSRF do callback público (rag_public):
    # bloqueia IP privado/loopback/link-local/reservado. follow_redirects é
    # DESABILITADO e cada salto é revalidado manualmente para impedir que um
    # redirect leve a um destino interno.
    from app.routers.rag_public import validar_callback_url
    if not url.startswith(("http://", "https://")):
        raise HTTPException(422, "URL inválida")
    try:
        validar_callback_url(url, exigir_https=False)
    except ValueError as e:
        raise HTTPException(422, f"URL rejeitada: {e}")
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as cli:
            resp = await cli.get(url, headers={"User-Agent": "Mozilla/5.0 EJC-RAG"})
            saltos = 0
            while resp.is_redirect and saltos < 5:
                destino = (str(resp.next_request.url)
                           if resp.next_request else resp.headers.get("location", ""))
                if not destino.startswith(("http://", "https://")):
                    raise HTTPException(422, "Redirect para destino inválido")
                validar_callback_url(destino, exigir_https=False)  # revalida cada salto
                resp = await cli.get(destino, headers={"User-Agent": "Mozilla/5.0 EJC-RAG"})
                saltos += 1
            resp.raise_for_status()
            html = resp.text
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(422, f"Redirect rejeitado: {e}")
    except Exception as e:
        raise HTTPException(422, f"Falha ao buscar a URL: {str(e)[:120]}")
    # remove scripts/styles e tags
    html = _re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=_re.S | _re.I)
    texto = _re.sub(r"<[^>]+>", " ", html)
    texto = _re.sub(r"&[a-zA-Z#0-9]+;", " ", texto)
    texto = _re.sub(r"\s+", " ", texto).strip()
    return await _ingerir_texto(db, background_tasks, titulo, categoria, texto,
                                fonte=url, tribunal=tribunal, confianca=confianca,
                                actor_id=str(cu.id))


async def _indexar_doc_bg(doc_id: str) -> None:
    """Gera embeddings dos chunks de um doc em segundo plano (nova sessão DB).

    A sessão da request já foi fechada quando esta task roda, por isso abrimos
    uma sessão própria. Idempotente: só preenche chunks com embedding ainda nulo.
    """
    if not emb_disponivel():
        return
    async with AsyncSessionLocal() as db:
        chunks = (await db.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.doc_id == doc_id,
                   KnowledgeChunk.embedding.is_(None))
            .order_by(KnowledgeChunk.chunk_index)
        )).scalars().all()
        if not chunks:
            await db.execute(
                update(KnowledgeDoc)
                .where(KnowledgeDoc.id == doc_id)
                .values(status_indexacao="indexado")
            )
            await db.commit()
            return
        vetores = await gerar_embeddings([c.conteudo for c in chunks])
        # gerar_embeddings já garante len(vetores) == len(chunks) quando não é
        # None (auditoria RAG: contagem divergente vinha sendo aceita aqui via
        # zip(), que trunca silenciosamente e deixava chunks finais sem
        # embedding com o doc já marcado "indexado"). Ainda assim, checagem
        # defensiva aqui: só aplica e marca "indexado" se bater 1:1.
        if vetores and len(vetores) == len(chunks):
            for ch, v in zip(chunks, vetores):
                ch.embedding = v
            novo_status = "indexado"
        else:
            if vetores:
                logger.warning(
                    "_indexar_doc_bg %s: %d vetores para %d chunks — "
                    "descartado, doc permanece sem embeddings", doc_id,
                    len(vetores), len(chunks),
                )
            novo_status = "sem_embeddings"
        await db.execute(
            update(KnowledgeDoc)
            .where(KnowledgeDoc.id == doc_id)
            .values(status_indexacao=novo_status)
        )
        await db.commit()


@router.post("/ingest", status_code=201)
async def ingerir(
    req: IngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio", "advogado"])),
):
    """
    Ingere documento na base de conhecimento.
    O texto entra como `rag_status=pendente` e só fica disponível à IA depois
    de aprovação no fluxo de governança.
    Os embeddings (busca semântica) são gerados em segundo plano via
    BackgroundTasks — sem Celery/Redis (tudo local). O campo
    `status_indexacao` reflete o progresso (pendente → indexado).
    """
    # Núcleo único de ingestão (mesmo chunker/fluxo do PDF/URL); vetorização
    # continua em BackgroundTasks (não bloqueia a resposta).
    return await _ingerir_texto(
        db, background_tasks, req.titulo, req.categoria, req.conteudo,
        fonte=req.fonte, tribunal=req.tribunal, confianca=req.confianca,
        actor_id=str(cu.id),
    )


@router.get("/buscar")
async def buscar(
    q: str = Query(..., min_length=3),
    limite: int = Query(6, ge=1, le=20),
    categorias: Optional[List[str]] = Query(None),
    incluir_historico: bool = Query(
        False, description="Inclui versões não-vigentes (migration 068) — auditoria de citações antigas."
    ),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Consulta a base pelo único pipeline governado de recuperação.

    ``buscar_contexto_rag`` aplica escopo, vigência, aprovação, quarentena de
    súmulas e exclusão do corpus fictício tanto no caminho vetorial quanto nos
    fallbacks lexicais. Manter SQL próprio nesta rota criou um bypass desses
    controles; por isso a rota não executa mais retrieval paralelo.
    """
    requer_equipe_juridica(
        cu, "Pesquisa jurídica restrita à equipe jurídica"
    )
    cats = categorias if categorias else None
    resultados = await buscar_contexto_rag(
        db, q, limite=limite, categorias=cats, incluir_historico=incluir_historico
    )
    # Preserva o contrato legado consumido pelo frontend e expõe o pipeline
    # governado separadamente para observabilidade.
    modo = "semantica" if emb_disponivel() else "textual"
    return {
        "query": q,
        "modo": modo,
        "pipeline": "hibrida_governada",
        "resultados": resultados,
    }


@router.get("/docs")
async def listar_docs(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    categoria: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # Metadados de documentos de caso também são informação jurídica protegida.
    # A listagem global do acervo é superfície da equipe jurídica, não do portal
    # do cliente nem de papéis financeiro/secretaria.
    requer_equipe_juridica(cu, "Acesso ao acervo RAG restrito à equipe jurídica")
    q = select(KnowledgeDoc).where(KnowledgeDoc.deleted_at.is_(None))
    if categoria:
        q = q.where(KnowledgeDoc.categoria == categoria)
    q = q.order_by(KnowledgeDoc.created_at.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [
            # status_indexacao/tribunal (item 3.1/3.2): sem eles, /conhecimento
            # renderizava "Sem vetor" para TODO doc (campo undefined), divergindo
            # da Curadoria RAG que já expõe o status real do mesmo documento.
            {"id": d.id, "titulo": d.titulo, "categoria": d.categoria,
             "fonte": d.fonte, "tribunal": d.tribunal,
             "status_indexacao": d.status_indexacao, "created_at": d.created_at}
            for d in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.delete("/docs/{doc_id}", response_model=MsgResponse)
async def remover_doc(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    d = (await db.execute(
        select(KnowledgeDoc).where(
            KnowledgeDoc.id == doc_id, KnowledgeDoc.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    d.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return MsgResponse(detail="Documento removido da base")


@router.get("/monitor-legislativo")
async def monitor_legislativo(
    q: Optional[str] = None,
    casa: Optional[str] = Query(None, description="camara | senado"),
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Radar legislativo (Bloco E): proposições recentes (Câmara + Senado) já
    ingeridas no RAG. Filtra por palavra-chave e casa; ordena por recência.
    Inclui o frescor da ingestão (última execução dos jobs)."""
    query = select(KnowledgeDoc).where(
        KnowledgeDoc.deleted_at.is_(None),
        KnowledgeDoc.categoria == "proposicao_legislativa",
    )
    if q:
        query = query.where(KnowledgeDoc.titulo.ilike(f"%{q}%"))
    if casa in ("camara", "senado"):
        # filtro no JSONB extra->>'casa'
        query = query.where(KnowledgeDoc.extra["casa"].astext == casa)
    query = query.order_by(
        sqlfunc.coalesce(KnowledgeDoc.atualizado_em, KnowledgeDoc.created_at).desc()
    )
    rows = (await db.execute(query.limit(limit))).scalars().all()

    proposicoes = []
    for d in rows:
        ex = d.extra or {}
        proposicoes.append({
            "titulo": d.titulo, "fonte": d.fonte,
            "casa": ex.get("casa"), "sigla": ex.get("sigla"),
            "ano": ex.get("ano"), "numero": ex.get("numero"),
            "atualizado_em": d.atualizado_em or d.created_at,
        })

    # frescor da ingestão (jobs camara/senado)
    fontes = (await db.execute(
        select(FonteIngestao).where(FonteIngestao.slug.in_(["camara", "senado"]))
    )).scalars().all()
    ingestao = [{
        "fonte": f.slug, "ultima_execucao": f.ultima_execucao,
        "status": f.ultimo_status, "registros_total": f.registros_total,
    } for f in fontes]

    return {
        "total": len(proposicoes),
        "filtro": {"q": q, "casa": casa},
        "proposicoes": proposicoes,
        "ingestao": ingestao,
        "nota": "Proposições ingeridas automaticamente (jobs diários Câmara/Senado). "
                "Ementa para triagem — texto integral nos portais oficiais.",
    }


# ── Seed da Base de Conhecimento (admin, idempotente) ────────────────────────
@router.post("/seed", summary="Popula a base com o conhecimento inicial do escritório (idempotente)",
             dependencies=[Depends(rate_limit("rag_seed", 3))])
async def seed_base_conhecimento(
    background_tasks: BackgroundTasks,
    incluir_jurisprudencia: bool = Query(
        False,
        description="Agenda também a importação inicial de jurisprudência REAL "
                    "(LexML/STJ) para temas comuns, em background — gracioso se "
                    "as fontes estiverem desabilitadas/indisponíveis.",
    ),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """Seed idempotente: README de uso, checklist de curadoria, padrão-ouro de
    peças, diretrizes internas por área e modelos de estrutura de documento.
    Reexecutar não duplica (dedup por chave_origem `ejc_seed:*`); conteúdo
    alterado gera nova versão preservando o histórico. Jurisprudência real
    entra somente pelo importador oficial (opt-in via query param)."""
    from app.models.audit_log import criar_audit_log
    from app.services.seed_conhecimento import (
        agendar_jurisprudencia_inicial, executar_seed_conhecimento,
    )
    resumo = await executar_seed_conhecimento(db)
    role = getattr(cu.role, "value", str(cu.role))
    await criar_audit_log(
        db, user_id=cu.id, user_role=role, acao="CREATE",
        entidade="rag_seed_conhecimento",
        detalhes=(f"Seed da base de conhecimento: {resumo['novos']} novos, "
                  f"{resumo['atualizados']} atualizados, "
                  f"{resumo['inalterados']} inalterados"
                  f"{'; jurisprudência inicial agendada' if incluir_jurisprudencia else ''}"),
    )
    await db.commit()
    jobs = []
    if incluir_jurisprudencia:
        jobs = agendar_jurisprudencia_inicial(background_tasks, cu.id, role)
    return {
        **resumo,
        "jurisprudencia_agendada": jobs,
        "detail": (
            f"Seed aplicado: {resumo['novos']} novos, {resumo['atualizados']} "
            f"atualizados, {resumo['inalterados']} inalterados de "
            f"{resumo['total']} documentos."
            + (f" {len(jobs)} importações de jurisprudência agendadas." if jobs else "")
        ),
    }


# ── Ingestão de fontes oficiais de conhecimento (Bloco 3) ────────────────────
@router.post(
    "/ingest-fontes-oficiais", status_code=202,
    summary="Dispara a ingestão das fontes oficiais de conhecimento (ANPD + Normas RFB)",
    dependencies=[Depends(rate_limit("rag_fontes", 3))],
)
async def ingest_fontes_oficiais(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """Disparo MANUAL do mesmo pipeline do job semanal (domingo 03h00 UTC):
    ANPD (regulamentações + guias orientativos) e Normas RFB (sijut2consulta).

    Roda em background (202) — o resultado durável fica no painel de fontes
    (tabela fontes_ingestao, slugs `anpd` e `normas_rfb`). Idempotente: o
    dedup/versionamento por chave_origem do upsert garante que reexecutar não
    duplica documentos. Auditado em audit_logs (INGESTAO_FONTES_OFICIAIS).
    """
    from app.models.audit_log import criar_audit_log
    from app.services.conhecimento_ingest import (
        FONTES_SLUGS, executar_ingest_conhecimento,
    )
    role = getattr(cu.role, "value", str(cu.role))
    await criar_audit_log(
        db, user_id=cu.id, user_role=role,
        acao="INGESTAO_FONTES_OFICIAIS", entidade="knowledge_docs",
        detalhes=("Disparo manual da ingestão de fontes oficiais de "
                  f"conhecimento: {', '.join(FONTES_SLUGS)}"),
    )
    await db.commit()
    # executar_ingest_conhecimento nunca levanta (try/except por fonte) e abre
    # as próprias sessões — seguro como BackgroundTask pós-resposta.
    background_tasks.add_task(executar_ingest_conhecimento)

    # Federação LexML (legislação estadual/municipal + jurisprudência de
    # tribunais): opt-in. Só enfileira se o gate estiver LIGADO — mantém o
    # princípio "nada roda por default". executar_ingestao abre a própria sessão
    # e isola falhas (registra a fonte 'lexml' no painel), seguro pós-resposta.
    from app.core.config import get_settings
    fontes = list(FONTES_SLUGS)
    if get_settings().LEXML_INGEST_ENABLED:
        from app.services.ingestion_service import executar_ingestao
        from app.services.ingestors import lexml
        background_tasks.add_task(
            executar_ingestao, "lexml",
            "Federação LexML (legislação + jurisprudência)", "jurisprudencia",
            lexml.ingerir,
        )
        fontes.append("lexml")

    return {
        "detail": "Ingestão de fontes oficiais agendada em background.",
        "fontes": fontes,
        "acompanhamento": ("Painel de fontes de ingestão (fontes_ingestao): "
                           "última execução, status e contagens por fonte."),
    }


# ── Destilação RAG com gate humano (#15) ─────────────────────────────────────
_AILOG_RAG_CATEGORIAS = {
    "conhecimento_ia",
    "tese_juridica",
    "referencia_interna",
    "precedente_interno",
}


class IngerirAILogRequest(BaseModel):
    categoria: str = "conhecimento_ia"
    titulo_override: str | None = None

@router.post("/ingerir-ai-log/{log_id}", summary="Destila output de IA aprovado para o RAG")
async def ingerir_ai_log_aprovado(
    log_id: str,
    req: IngerirAILogRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Gate humano de destilação: advogado aprova um output de IA (ai_log)
    e ele é ingerido no RAG como conhecimento institucional.
    REGRA: só outputs com status HITL 'revisado' ou 'aplicado' podem ser ingeridos.
    """
    from app.models.ai_log import AILog, AIStatusHITL
    from app.services.ingestion_service import upsert_documento
    from app.services.ai_service import _escopo_cliente_do_caso

    requer_equipe_juridica(
        cu, "Destilação de conhecimento RAG restrita à equipe jurídica"
    )
    if req.categoria not in _AILOG_RAG_CATEGORIAS:
        raise HTTPException(
            status_code=422,
            detail=(
                "Categoria não permitida para conhecimento derivado de IA. "
                f"Permitidas: {', '.join(sorted(_AILOG_RAG_CATEGORIAS))}"
            ),
        )

    log = (await db.execute(
        select(AILog).where(AILog.id == log_id, AILog.user_id == cu.id)
    )).scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="AI log não encontrado")
    if log.status_hitl not in (AIStatusHITL.revisado, AIStatusHITL.aplicado):
        raise HTTPException(
            status_code=400,
            detail=f"Somente outputs com status 'revisado' ou 'aplicado' podem ser ingeridos. Status atual: {log.status_hitl}"
        )
    if not log.resposta or len(log.resposta.strip()) < 50:
        raise HTTPException(status_code=400, detail="Output muito curto para ingestão")

    titulo = req.titulo_override or f"IA {log.tipo_uso.value} — {log.created_at.strftime('%d/%m/%Y')}"
    fonte  = f"ejc_ia_{log.tipo_uso.value}"
    chave  = f"ai_log_{log.id}"

    case_id = getattr(log, "case_id", None)
    client_id = await _escopo_cliente_do_caso(db, case_id) if case_id else None
    if case_id and not client_id:
        raise HTTPException(
            status_code=409,
            detail="Não foi possível confirmar o escopo do caso; ingestão RAG bloqueada.",
        )
    if req.categoria == "precedente_interno" and not client_id:
        raise HTTPException(
            status_code=422,
            detail="precedente_interno exige vínculo com caso/cliente.",
        )

    resultado = await upsert_documento(
        db,
        titulo=titulo,
        categoria=req.categoria,
        conteudo=log.resposta,
        chave_origem=chave,
        fonte=fonte,
        extra={
            # HITL do output de IA NÃO substitui a curadoria do conhecimento.
            # O documento nasce pendente e só entra no retrieval após revisão
            # explícita no fluxo de Governança RAG.
            "rag_status": "pendente",
            "requires_human_review": True,
            "human_reviewed": False,
            "origem": "ai_log_hitl",
            "status_hitl": log.status_hitl.value,
            "destilado_por": str(cu.id),
        },
        client_id=client_id,
        case_id=case_id,
        confianca="media",
    )
    doc = (await db.execute(
        select(KnowledgeDoc).where(
            KnowledgeDoc.chave_origem == chave,
            KnowledgeDoc.deleted_at.is_(None),
            KnowledgeDoc.vigente.is_(True),
            KnowledgeDoc.client_id == client_id if client_id else KnowledgeDoc.client_id.is_(None),
        ).limit(1)
    )).scalars().first()
    role = getattr(getattr(cu, "role", None), "value", getattr(cu, "role", None))
    await criar_audit_log(
        db,
        str(cu.id),
        str(role or ""),
        "RAG_DESTILAR_AILOG",
        "knowledge_docs",
        str(doc.id) if doc else None,
        detalhes=(
            f"ai_log={log_id} categoria={req.categoria} "
            f"escopo={'caso' if case_id else 'institucional'}"
        ),
    )
    await db.commit()

    # Estima chunks para retorno informativo
    chunks_estimados = len(chunk_texto(log.resposta))

    return {
        "ok": True,
        "ai_log_id": log_id,
        "resultado_upsert": resultado,   # "novo" | "atualizado" | "inalterado"
        "chunks_estimados": chunks_estimados,
        "categoria": req.categoria,
        "titulo": titulo,
        "aviso": "Output destilado para o RAG em estado pendente; requer curadoria antes de entrar nas consultas.",
    }
