# app/routers/ia_governanca.py
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func as sqlfunc, text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.ai_log import AILog
from app.models.rag import KnowledgeDoc, KnowledgeChunk, FonteIngestao
from app.services.ingestion_service import upsert_documento, registrar_fonte, fetch
from app.models.prompt_juridico import PromptJuridico
from app.models.legal_doc import LegalDoc

router = APIRouter(prefix="/ia-governanca", tags=["IA — Governanca"])

Confianca = Literal["alta", "media", "baixa", "bloqueado"]
RagStatus = Literal["pendente", "aprovado", "recusado", "disponivel"]


def _role(user: User) -> str:
    return getattr(user.role, "value", user.role)


def _require_admin_socio(user: User):
    if _role(user) not in ("superadmin", "admin", "socio"):
        raise HTTPException(403, "Acesso restrito a governanca da IA")


def _v(x):
    return x.value if hasattr(x, "value") else x


def _parse_score(prompt: str | None) -> int | None:
    m = re.search(r"score_confianca\s*[:=]\s*(\d{1,3})", prompt or "", re.I)
    if not m:
        return None
    return max(0, min(100, int(m.group(1))))


def _conf(extra: dict | None) -> str:
    return (extra or {}).get("confidence_level") or (extra or {}).get("confianca") or "media"


def _rag_status(extra: dict | None, status_indexacao: str | None) -> str:
    return (extra or {}).get("rag_status") or ("disponivel" if status_indexacao == "indexado" else "pendente")


class CuradoriaPatch(BaseModel):
    confidence_level: Confianca
    rag_status: RagStatus = "aprovado"
    notas: str | None = Field(None, max_length=2000)


class JurisprudenciaMGIn(BaseModel):
    titulo: str = Field(..., min_length=5, max_length=500)
    ementa: str = Field(..., min_length=50)
    tese_extraida: str | None = Field(None, max_length=4000)
    tribunal: str = Field("TJMG", max_length=30)
    orgao_julgador: str | None = Field(None, max_length=180)
    numero_processo: str | None = Field(None, max_length=80)
    relator: str | None = Field(None, max_length=180)
    data_julgamento: str | None = Field(None, max_length=30)
    data_publicacao: str | None = Field(None, max_length=30)
    area: str | None = Field(None, max_length=80)
    rito: str | None = Field(None, max_length=80)
    classe: str | None = Field(None, max_length=120)
    assunto_cnj: str | None = Field(None, max_length=180)
    resultado: str | None = Field(None, max_length=120)
    favoravel_para: str | None = Field(None, max_length=120)
    fonte_url: str | None = Field(None, max_length=600)
    tipo_fonte: Literal["acordao", "sentenca_jec", "turma_recursal", "fonaje", "stj", "datajud", "outro"] = "acordao"
    aprovar_para_rag: bool = False


class ExtrairJurisprudenciaURLIn(BaseModel):
    url: str = Field(..., min_length=10, max_length=900)
    tipo_fonte: Literal["acordao", "sentenca_jec", "turma_recursal", "fonaje", "stj", "datajud", "outro"] = "acordao"
    area: str | None = Field(None, max_length=80)
    rito: str | None = Field(None, max_length=80)


def _limpar_html(html: str) -> str:
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</(p|div|li|tr|h1|h2|h3|h4)>", "\n", html, flags=re.I)
    texto = re.sub(r"<[^>]+>", " ", html)
    entidades = {"&nbsp;": " ", "&amp;": "&", "&quot;": '"', "&#39;": "'", "&lt;": "<", "&gt;": ">"}
    for k, v in entidades.items():
        texto = texto.replace(k, v)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _meta_content(html: str, prop: str) -> str | None:
    patterns = [
        "<meta[^>]+(?:property|name)=[\"']" + re.escape(prop) + "[\"'][^>]+content=[\"']([^\"']+)[\"']",
        "<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:property|name)=[\"']" + re.escape(prop) + "[\"']",
    ]
    for pat in patterns:
        m = re.search(pat, html, flags=re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return None


def _inferir_campos_jurisprudencia(url: str, html: str, texto: str, tipo_fonte: str, area: str | None, rito: str | None) -> dict:
    titulo = _meta_content(html, "og:title") or _meta_content(html, "title")
    if not titulo:
        mt = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.S | re.I)
        titulo = re.sub(r"\s+", " ", mt.group(1)).strip() if mt else "Jurisprudencia importada"
    cnj = re.search(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b", texto)
    relator = re.search(r"Relator(?:a)?\s*[:\-]\s*([^\n]{3,120})", texto, flags=re.I)
    orgao = re.search(r"(?:Orgao julgador|Camara|Turma Recursal)\s*[:\-]\s*([^\n]{3,160})", texto, flags=re.I)
    data_julg = re.search(r"(?:Data do julgamento|Julgamento)\s*[:\-]\s*(\d{1,2}/\d{1,2}/\d{4})", texto, flags=re.I)
    data_pub = re.search(r"(?:Publicacao|Publicado em|DJe)\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})", texto, flags=re.I)
    # Ementa: tenta capturar a partir do marcador; fallback usa trecho central curto.
    em = re.search(r"EMENTA\s*[:\-]?\s*(.{80,4000})", texto, flags=re.S | re.I)
    ementa = em.group(1).strip() if em else texto[:3500].strip()
    ementa = re.sub(r"\n{2,}.*$", lambda m: m.group(0), ementa).strip()
    tribunal = "TJMG" if "tjmg.jus.br" in url.lower() else "STJ" if "stj.jus.br" in url.lower() else "STF" if "stf.jus.br" in url.lower() else "CNJ" if "cnj.jus.br" in url.lower() else "OUTRO"
    return {
        "titulo": titulo[:500],
        "ementa": ementa[:12000] if len(ementa) >= 50 else (texto[:12000] or titulo),
        "tese_extraida": "",
        "tribunal": tribunal,
        "orgao_julgador": orgao.group(1).strip()[:180] if orgao else None,
        "numero_processo": cnj.group(0) if cnj else None,
        "relator": relator.group(1).strip()[:180] if relator else None,
        "data_julgamento": data_julg.group(1) if data_julg else None,
        "data_publicacao": data_pub.group(1) if data_pub else None,
        "area": area,
        "rito": rito,
        "classe": None,
        "assunto_cnj": None,
        "resultado": None,
        "favoravel_para": None,
        "fonte_url": url,
        "tipo_fonte": tipo_fonte,
        "aprovar_para_rag": False,
        "fonte_validada": _fonte_oficial(url),
    }


_OFICIAL_DOMAINS = (
    "tjmg.jus.br",
    "cnj.jus.br",
    "stj.jus.br",
    "stf.jus.br",
    "fonaje.amb.com.br",
)


def _fonte_oficial(url: str | None) -> bool:
    """True apenas se o HOSTNAME da URL for um dominio oficial (ou subdominio
    legitimo) e o esquema for https. Valida por hostname normalizado, nunca por
    substring solta — evita bypass como https://evil.com/?x=tjmg.jus.br ou
    https://tjmg.jus.br.evil.net/."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in _OFICIAL_DOMAINS)


def _colecao_mg(tipo_fonte: str, rito: str | None) -> str:
    rito_norm = (rito or "").lower()
    if tipo_fonte in ("sentenca_jec", "turma_recursal") or "jec" in rito_norm or "juizado" in rito_norm:
        return "jurisprudencia_tjmg_juizados"
    if tipo_fonte == "fonaje":
        return "fonaje_enunciados"
    if tipo_fonte == "stj":
        return "stj_juizados"
    if tipo_fonte == "datajud":
        return "datajud_metadados"
    return "jurisprudencia_tjmg_acordaos"


def _texto_jurisprudencia_mg(req: JurisprudenciaMGIn) -> str:
    partes = [
        f"TITULO: {req.titulo}",
        f"TRIBUNAL: {req.tribunal}",
        f"ORGAO JULGADOR: {req.orgao_julgador or 'nao informado'}",
        f"NUMERO DO PROCESSO: {req.numero_processo or 'nao informado'}",
        f"RELATOR: {req.relator or 'nao informado'}",
        f"DATA JULGAMENTO: {req.data_julgamento or 'nao informada'}",
        f"AREA: {req.area or 'nao informada'}",
        f"RITO: {req.rito or 'nao informado'}",
        f"CLASSE: {req.classe or 'nao informada'}",
        f"ASSUNTO CNJ: {req.assunto_cnj or 'nao informado'}",
        f"RESULTADO: {req.resultado or 'nao informado'}",
        f"FAVORAVEL PARA: {req.favoravel_para or 'nao informado'}",
        "EMENTA:",
        req.ementa,
    ]
    if req.tese_extraida:
        partes.extend(["TESE EXTRAIDA:", req.tese_extraida])
    if req.fonte_url:
        partes.extend(["FONTE OFICIAL:", req.fonte_url])
    partes.append("REGRA DE USO: citar em peca final somente se a fonte oficial estiver validada e o advogado revisar a aderencia ao caso concreto.")
    return "\n\n".join(partes)


@router.get("/dashboard")
async def dashboard_governanca(
    dias: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_admin_socio(cu)
    desde = datetime.now(timezone.utc) - timedelta(days=dias)

    total_logs = (await db.execute(select(sqlfunc.count()).select_from(AILog).where(AILog.created_at >= desde))).scalar() or 0
    por_status = (await db.execute(select(AILog.status_hitl, sqlfunc.count()).where(AILog.created_at >= desde).group_by(AILog.status_hitl))).all()
    status_map = {_v(s): c for s, c in por_status}
    aplicados = status_map.get("aplicado", 0)
    revisados = status_map.get("revisado", 0)

    logs_validacao = (await db.execute(select(AILog.prompt_sanitizado).where(AILog.created_at >= desde, AILog.prompt_sanitizado.ilike("%score_confianca%")))).scalars().all()
    scores = [s for s in (_parse_score(x) for x in logs_validacao) if s is not None]

    # ── HITL a NÍVEL DE PEÇA (item 1.2) ──────────────────────────────────
    # A taxa_hitl_pct acima é o % de LOGS de IA marcados manualmente como
    # revisado/aplicado — estruturalmente ~0%, pois a revisão humana grava em
    # LegalDoc.human_reviewed (controle realmente imposto por código em
    # legal_docs.py), nunca em AILog.status_hitl. A métrica que reflete o
    # controle HITL efetivo é a cobertura de revisão das PEÇAS geradas por IA.
    pecas_ia_total = (await db.execute(
        select(sqlfunc.count()).select_from(LegalDoc).where(
            LegalDoc.deleted_at.is_(None),
            LegalDoc.ai_generated.is_(True),
            LegalDoc.created_at >= desde,
        )
    )).scalar() or 0
    pecas_ia_revisadas = (await db.execute(
        select(sqlfunc.count()).select_from(LegalDoc).where(
            LegalDoc.deleted_at.is_(None),
            LegalDoc.ai_generated.is_(True),
            LegalDoc.human_reviewed.is_(True),
            LegalDoc.created_at >= desde,
        )
    )).scalar() or 0

    # ── CUSTO DE IA (governança de gasto) ────────────────────────────────
    # O custo já é rastreado por chamada (AILog.custo_estimado, via ai_cost.py);
    # aqui damos VISIBILIDADE no painel — total do período, tokens, por modelo, e
    # um alerta opcional de orçamento (AI_BUDGET_ALERTA_BRL no .env; 0 = desligado).
    custo_total = (await db.execute(
        select(sqlfunc.coalesce(sqlfunc.sum(AILog.custo_estimado), 0)).where(AILog.created_at >= desde)
    )).scalar() or 0
    tokens_in = (await db.execute(
        select(sqlfunc.coalesce(sqlfunc.sum(AILog.tokens_input), 0)).where(AILog.created_at >= desde)
    )).scalar() or 0
    tokens_out = (await db.execute(
        select(sqlfunc.coalesce(sqlfunc.sum(AILog.tokens_output), 0)).where(AILog.created_at >= desde)
    )).scalar() or 0
    custo_por_modelo = [
        {"modelo": m, "chamadas": int(n), "custo_brl": round(float(c), 4)}
        for (m, n, c) in (await db.execute(
            select(
                AILog.modelo, sqlfunc.count(),
                sqlfunc.coalesce(sqlfunc.sum(AILog.custo_estimado), 0),
            )
            .where(AILog.created_at >= desde)
            .group_by(AILog.modelo)
            .order_by(sqlfunc.coalesce(sqlfunc.sum(AILog.custo_estimado), 0).desc())
        )).all()
    ]
    custo_total_brl = round(float(custo_total), 2)
    budget_alerta = float(get_settings().AI_BUDGET_ALERTA_BRL or 0)
    # Projeção mensal simples (ritmo atual) — consciência de consumo sem config.
    projecao_mensal = round(custo_total_brl / dias * 30, 2) if dias else custo_total_brl

    docs = (await db.execute(select(KnowledgeDoc).where(KnowledgeDoc.deleted_at.is_(None)))).scalars().all()
    conf_map = {"alta": 0, "media": 0, "baixa": 0, "bloqueado": 0, "sem_curadoria": 0}
    rag_status_map: dict[str, int] = {}
    for d in docs:
        extra = d.extra or {}
        if not extra.get("confidence_level") and not extra.get("confianca"):
            conf_map["sem_curadoria"] += 1
        else:
            conf_map[_conf(extra)] = conf_map.get(_conf(extra), 0) + 1
        rs = _rag_status(extra, d.status_indexacao)
        rag_status_map[rs] = rag_status_map.get(rs, 0) + 1

    prompts_total = (await db.execute(select(sqlfunc.count()).select_from(PromptJuridico).where(PromptJuridico.deleted_at.is_(None)))).scalar() or 0
    prompts_exec = (await db.execute(select(sqlfunc.coalesce(sqlfunc.sum(PromptJuridico.vezes_executado), 0)).where(PromptJuridico.deleted_at.is_(None)))).scalar() or 0
    pecas_sem_validacao = (await db.execute(sqltext("""
        SELECT count(*) FROM legal_docs ld
        WHERE ld.deleted_at IS NULL
          AND ld.status IN ('aprovada','final','protocolada')
          AND NOT EXISTS (
            SELECT 1 FROM ai_logs al
            WHERE al.prompt_sanitizado ILIKE '%' || 'LEGAL_DOC_ID:' || ld.id || '%'
              AND al.status_hitl IN ('revisado','aplicado')
          )
    """))).scalar() or 0

    fontes = (await db.execute(select(FonteIngestao).order_by(FonteIngestao.slug))).scalars().all()
    fontes_status = {}
    for f in fontes:
        fontes_status[f.ultimo_status or "sem_execucao"] = fontes_status.get(f.ultimo_status or "sem_execucao", 0) + 1

    return {
        "periodo_dias": dias,
        "ia": {
            "total_chamadas": total_logs,
            # Cobertura HITL das PEÇAS de IA — métrica ligada ao controle imposto
            # por código (LegalDoc.human_reviewed). É o indicador principal do painel.
            "hitl_pecas_pct": round(pecas_ia_revisadas / pecas_ia_total * 100, 1) if pecas_ia_total else None,
            "pecas_ia_geradas": pecas_ia_total,
            "pecas_ia_revisadas": pecas_ia_revisadas,
            # Ratio a nível de LOG (marcação manual em AILog.status_hitl) — mantido
            # para diagnóstico, mas NÃO é a cobertura de revisão humana das peças.
            "taxa_hitl_logs_pct": round((aplicados + revisados) / total_logs * 100, 1) if total_logs else None,
            "por_status": status_map,
            "score_medio_validacoes": round(sum(scores) / len(scores), 1) if scores else None,
            "validacoes_com_score": len(scores),
        },
        "custo": {
            "total_brl": custo_total_brl,
            "projecao_mensal_brl": projecao_mensal,
            "tokens_input": int(tokens_in),
            "tokens_output": int(tokens_out),
            "por_modelo": custo_por_modelo,
            "orcamento_alerta_brl": budget_alerta or None,
            "acima_do_alerta": bool(budget_alerta and custo_total_brl > budget_alerta),
            "pct_do_orcamento": round(custo_total_brl / budget_alerta * 100, 1) if budget_alerta else None,
        },
        "rag": {
            "documentos": len(docs),
            "por_confianca": conf_map,
            "por_status": rag_status_map,
        },
        "prompts": {"total": prompts_total, "execucoes": int(prompts_exec or 0)},
        "guardrails": {
            "pecas_finais_sem_validacao_revisada": pecas_sem_validacao,
            "score_minimo_peca": 75,
            "protocolo_sem_human_review": "bloqueado_por_codigo",
        },
        "fontes": {"total": len(fontes), "por_status": fontes_status},
    }


@router.get("/rag-curadoria")
async def listar_curadoria(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    categoria: str | None = None,
    confianca: str | None = None,
    busca: str | None = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_admin_socio(cu)
    q = select(KnowledgeDoc).where(KnowledgeDoc.deleted_at.is_(None))
    if categoria:
        q = q.where(KnowledgeDoc.categoria == categoria)
    if busca:
        q = q.where(KnowledgeDoc.titulo.ilike(f"%{busca}%"))
    if confianca:
        # Filtro no SQL (não em Python pós-paginação): garante total e páginas
        # corretos. Espelha _conf(): confidence_level → confianca (legado) → "media".
        conf_expr = sqlfunc.coalesce(
            sqlfunc.nullif(KnowledgeDoc.extra["confidence_level"].astext, ""),
            sqlfunc.nullif(KnowledgeDoc.extra["confianca"].astext, ""),
            "media",
        )
        q = q.where(conf_expr == confianca)
    q = q.order_by(KnowledgeDoc.created_at.desc())
    total = (await db.execute(select(sqlfunc.count()).select_from(q.subquery()))).scalar() or 0
    rows = (await db.execute(q.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    # Contagem de chunks por doc em UMA query agregada (evita N+1 no loop).
    doc_ids = [d.id for d in rows]
    chunk_counts: dict[str, int] = {}
    if doc_ids:
        cc = await db.execute(
            select(KnowledgeChunk.doc_id, sqlfunc.count())
            .where(KnowledgeChunk.doc_id.in_(doc_ids))
            .group_by(KnowledgeChunk.doc_id)
        )
        chunk_counts = {row[0]: row[1] for row in cc.all()}
    data = []
    for d in rows:
        extra = d.extra or {}
        item_conf = _conf(extra)
        chunks = chunk_counts.get(d.id, 0)
        data.append({
            "id": d.id,
            "titulo": d.titulo,
            "categoria": d.categoria,
            "fonte": d.fonte,
            "tribunal": d.tribunal,
            "status_indexacao": d.status_indexacao,
            "chunks": chunks,
            "confidence_level": item_conf,
            "rag_status": _rag_status(extra, d.status_indexacao),
            "curadoria": extra.get("curadoria") or {},
            "created_at": d.created_at,
        })
    return {"data": data, "total": total, "page": page, "page_size": page_size}


@router.patch("/rag-curadoria/{doc_id}")
async def atualizar_curadoria(
    doc_id: str,
    req: CuradoriaPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_admin_socio(cu)
    d = (await db.execute(select(KnowledgeDoc).where(KnowledgeDoc.id == doc_id, KnowledgeDoc.deleted_at.is_(None)))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Documento RAG nao encontrado")
    extra = dict(d.extra or {})
    extra["confidence_level"] = req.confidence_level
    extra["rag_status"] = req.rag_status
    extra["curadoria"] = {
        "reviewed_by": cu.id,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "notas": req.notas,
    }
    d.extra = extra
    await db.commit()
    return {"detail": "Curadoria atualizada", "id": d.id, "confidence_level": req.confidence_level, "rag_status": req.rag_status}


@router.get("/prompts")
async def governanca_prompts(db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    _require_admin_socio(cu)
    rows = (await db.execute(select(PromptJuridico).where(PromptJuridico.deleted_at.is_(None)).order_by(PromptJuridico.vezes_executado.desc(), PromptJuridico.updated_at.desc()).limit(50))).scalars().all()
    return {"data": [{
        "id": p.id,
        "titulo": p.titulo,
        "categoria": _v(p.categoria),
        "versao": p.versao,
        "vezes_executado": p.vezes_executado,
        "avaliacao_media": p.avaliacao_media,
        "favorito": p.favorito,
        "publico": p.publico,
        "updated_at": p.updated_at,
    } for p in rows]}


@router.get("/fontes")
async def fontes_ingestao(db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    _require_admin_socio(cu)
    rows = (await db.execute(select(FonteIngestao).order_by(FonteIngestao.slug))).scalars().all()
    return {"data": [{
        "slug": f.slug,
        "descricao": f.descricao,
        "categoria_rag": f.categoria_rag,
        "ativo": f.ativo,
        "ultima_execucao": f.ultima_execucao,
        "ultimo_status": f.ultimo_status,
        "registros_novos": f.registros_novos,
        "registros_total": f.registros_total,
        "ultimo_erro": f.ultimo_erro,
    } for f in rows]}


@router.post("/fontes/tjmg/coletar", status_code=202)
async def coletar_tjmg_agora(
    bg: BackgroundTasks,
    cu: User = Depends(get_current_user),
):
    """Dispara uma coleta do TJMG SOB DEMANDA (fora do cron semanal).

    Serve para o escritório VALIDAR o coletor contra o site real do TJMG antes
    de ligar o job agendado (TJMG_INGEST_ENABLED) — por isso NÃO depende desse
    gate: é uma ação explícita de admin/sócio. Roda em segundo plano (a coleta
    faz requisições de rede) e o resultado (novos/total/erro) aparece na fonte
    'tjmg' em GET /ia-governanca/fontes.
    """
    _require_admin_socio(cu)
    from app.services.ingestion_service import executar_ingestao
    from app.services.ingestors import tjmg
    bg.add_task(
        executar_ingestao,
        "tjmg", "Jurisprudência TJMG (crawler — base de acórdãos)",
        "jurisprudencia", tjmg.ingerir,
    )
    return {
        "status": "coleta_iniciada",
        "mensagem": "Coleta do TJMG iniciada em segundo plano. Acompanhe o "
                    "resultado (novos/total/erro) na fonte 'tjmg' em "
                    "/ia-governanca/fontes.",
    }


@router.get("/guardrails")
async def guardrails(db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    _require_admin_socio(cu)
    total_pecas = (await db.execute(select(sqlfunc.count()).select_from(LegalDoc).where(LegalDoc.deleted_at.is_(None)))).scalar() or 0
    ia_sem_revisao = (await db.execute(select(sqlfunc.count()).select_from(LegalDoc).where(LegalDoc.deleted_at.is_(None), LegalDoc.ai_generated.is_(True), LegalDoc.human_reviewed.is_(False)))).scalar() or 0
    logs_pendentes = (await db.execute(select(sqlfunc.count()).select_from(AILog).where(AILog.status_hitl == "gerado"))).scalar() or 0
    return {
        "regras_ativas": [
            "Peca IA nao avanca para aprovada/final/protocolada sem revisao humana.",
            "Peca nao avanca para aprovada/final/protocolada sem validacao juridica revisada/aplicada e score minimo.",
            "AI logs so entram no RAG apos HITL revisado ou aplicado.",
            "Embeddings rodam em servico interno isolado; backend principal permanece leve.",
            "Dados sao sanitizados antes de chamadas externas de IA.",
        ],
        "metricas": {"pecas_total": total_pecas, "pecas_ia_sem_revisao": ia_sem_revisao, "ai_logs_pendentes_hitl": logs_pendentes},
    }


@router.get("/jurisprudencia-mg/geometria")
async def geometria_jurisprudencia_mg(cu: User = Depends(get_current_user)):
    _require_admin_socio(cu)
    return {
        "colecoes": [
            "jurisprudencia_tjmg_acordaos",
            "jurisprudencia_tjmg_juizados",
            "sentencas_jec_tjmg",
            "fonaje_enunciados",
            "stj_juizados",
            "datajud_metadados",
            "teses_internas_escritorio",
            "pecas_aprovadas_escritorio",
        ],
        "metadados_obrigatorios": [
            "tribunal", "orgao_julgador", "numero_processo", "data_julgamento",
            "area", "rito", "assunto_cnj", "resultado", "fonte_url", "fonte_validada",
        ],
        "regra_citacao": "Jurisprudencia sem fonte oficial validada fica pendente e nao deve ser citada como confirmada em peca final.",
        "fontes_oficiais_aceitas": list(_OFICIAL_DOMAINS),
        "estrategia_busca": "hibrida: filtro estruturado por metadados + busca textual/vetorial nos chunks RAG + revisao humana.",
    }


@router.post("/jurisprudencia-mg", status_code=201)
async def importar_jurisprudencia_mg(
    req: JurisprudenciaMGIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_admin_socio(cu)
    fonte_validada = _fonte_oficial(req.fonte_url)
    colecao = _colecao_mg(req.tipo_fonte, req.rito)
    confidence = "alta" if fonte_validada and req.numero_processo else "media" if fonte_validada else "baixa"
    rag_status = "aprovado" if req.aprovar_para_rag and fonte_validada else "pendente"
    chave_base = req.numero_processo or req.fonte_url or f"manual-{uuid4()}"
    chave = f"mg-jec:{colecao}:{chave_base}"[:255]
    extra = {
        "source_family": "mg_jec",
        "collection": colecao,
        "tipo_fonte": req.tipo_fonte,
        "tribunal": req.tribunal,
        "orgao_julgador": req.orgao_julgador,
        "numero_processo": req.numero_processo,
        "relator": req.relator,
        "data_julgamento": req.data_julgamento,
        "data_publicacao": req.data_publicacao,
        "area": req.area,
        "rito": req.rito,
        "classe": req.classe,
        "assunto_cnj": req.assunto_cnj,
        "resultado": req.resultado,
        "favoravel_para": req.favoravel_para,
        "fonte_url": req.fonte_url,
        "fonte_validada": fonte_validada,
        "confidence_level": confidence,
        "rag_status": rag_status,
        "curadoria": {
            "reviewed_by": cu.id,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "notas": "Importacao MG/JEC com validacao automatica de dominio oficial.",
        },
        "uso_em_peca": "permitido_com_revisao" if fonte_validada else "verificar_fonte_oficial",
    }
    resultado = await upsert_documento(
        db,
        titulo=req.titulo,
        categoria=colecao,
        conteudo=_texto_jurisprudencia_mg(req),
        chave_origem=chave,
        fonte=req.fonte_url,
        tribunal=req.tribunal,
        extra=extra,
    )
    await registrar_fonte(db, "tjmg_jec_manual", "Curadoria manual TJMG/Juizados Especiais", "jurisprudencia")
    await db.commit()
    return {
        "ok": True,
        "resultado": resultado,
        "colecao": colecao,
        "fonte_validada": fonte_validada,
        "confidence_level": confidence,
        "rag_status": rag_status,
        "aviso": "Fonte sem dominio oficial permanece pendente de validacao." if not fonte_validada else "Registro pronto para busca RAG, sujeito a revisao humana no caso concreto.",
    }


@router.post("/jurisprudencia-mg/extrair-url")
async def extrair_jurisprudencia_url(
    req: ExtrairJurisprudenciaURLIn,
    cu: User = Depends(get_current_user),
):
    _require_admin_socio(cu)
    if not req.url.startswith(("http://", "https://")):
        raise HTTPException(422, "URL invalida")
    if not _fonte_oficial(req.url):
        raise HTTPException(422, "Use uma URL oficial TJMG/CNJ/STJ/STF/FONAJE para importacao assistida")
    # Anti-SSRF: fetch(validar_ssrf=True) desabilita follow_redirects automatico
    # e revalida a URL inicial + CADA salto de redirect contra IP interno
    # (169.254.169.254/127.0.0.1/10.*/link-local/reservado). Nenhum host que
    # resolva para IP privado/loopback pode ser buscado, nem via redirect.
    try:
        resp = await fetch(
            req.url,
            headers={
                "User-Agent": "Mozilla/5.0 EJC-Jurisprudencia/1.0",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=25,
            validar_ssrf=True,
        )
    except Exception as e:
        raise HTTPException(422, f"Falha ao acessar URL oficial: {str(e)[:160]}")
    html = resp.text or ""
    texto = _limpar_html(html)
    if len(texto) < 80:
        raise HTTPException(422, "Texto extraido muito curto. Cole a ementa manualmente.")
    data = _inferir_campos_jurisprudencia(req.url, html, texto, req.tipo_fonte, req.area, req.rito)
    return {
        "data": data,
        "texto_extraido_preview": texto[:1800],
        "aviso": "Revise os campos extraidos antes de salvar. O sistema nao presume aderencia ao caso concreto.",
    }


@router.get("/jurisprudencia-mg")
async def listar_jurisprudencia_mg(
    q: str | None = Query(None, min_length=2),
    area: str | None = None,
    rito: str | None = None,
    colecao: str | None = None,
    fonte_validada: bool | None = None,
    limite: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _require_admin_socio(cu)
    colecoes = [
        "jurisprudencia_tjmg_acordaos", "jurisprudencia_tjmg_juizados",
        "sentencas_jec_tjmg", "fonaje_enunciados", "stj_juizados", "datajud_metadados",
    ]
    query = select(KnowledgeDoc).where(KnowledgeDoc.deleted_at.is_(None))
    query = query.where(KnowledgeDoc.categoria.in_([colecao] if colecao else colecoes))
    if q:
        query = query.where(KnowledgeDoc.titulo.ilike(f"%{q}%"))
    if area:
        query = query.where(KnowledgeDoc.extra["area"].astext.ilike(f"%{area}%"))
    if rito:
        query = query.where(KnowledgeDoc.extra["rito"].astext.ilike(f"%{rito}%"))
    if fonte_validada is not None:
        query = query.where(KnowledgeDoc.extra["fonte_validada"].as_boolean() == fonte_validada)
    rows = (await db.execute(query.order_by(KnowledgeDoc.created_at.desc()).limit(limite))).scalars().all()
    data = []
    for d in rows:
        ex = d.extra or {}
        data.append({
            "id": d.id,
            "titulo": d.titulo,
            "colecao": d.categoria,
            "tribunal": d.tribunal,
            "fonte": d.fonte,
            "orgao_julgador": ex.get("orgao_julgador"),
            "numero_processo": ex.get("numero_processo"),
            "area": ex.get("area"),
            "rito": ex.get("rito"),
            "resultado": ex.get("resultado"),
            "favoravel_para": ex.get("favoravel_para"),
            "fonte_validada": ex.get("fonte_validada"),
            "confidence_level": _conf(ex),
            "rag_status": _rag_status(ex, d.status_indexacao),
            "created_at": d.created_at,
        })
    return {"data": data, "total": len(data), "filtros": {"q": q, "area": area, "rito": rito, "colecao": colecao, "fonte_validada": fonte_validada}}
