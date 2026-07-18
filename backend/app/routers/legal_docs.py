# ── app/routers/legal_docs.py ────────────────────────────────────────────────
# Peças jurídicas com HITL ENFORÇADO:
# ai_generated=True NÃO avança para aprovada/final sem human_reviewed=True.
# Bloqueio em nível de código — não apenas UI.
from __future__ import annotations
import logging
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import and_, select, func as sqlfunc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso, is_gestao
from app.models.case import Case
from app.models.user import User
from app.models.legal_doc import LegalDoc, PecaStatus
from app.models.ai_log import AILog
from app.models.rag import KnowledgeDoc
from app.models.audit_log import criar_audit_log
from app.services.case_intel import indexar_peca_rag
from app.services.document_format import padronizar_documento_juridico
from app.services.validador_juridico_service import ValidacaoInput, validar_rascunho_juridico
from app.schemas.legal_doc import (
    LegalDocCreate, LegalDocUpdate, LegalDocRevisao, LegalDocAprovacao,
    LegalDocResponse, LegalDocDetail,
)
from app.schemas.common import MsgResponse

router = APIRouter(prefix="/legal-docs", tags=["Peças Jurídicas"])

STATUS_EXIGE_REVISAO = {"aprovada", "final", "protocolada"}
STATUS_EXIGE_VALIDACAO = {"aprovada", "final", "protocolada"}
VALIDACAO_SCORE_MINIMO = 75

# Status "pronto para protocolar" → dispara checklist pré-protocolo (#CHK gatilho 2).
_STATUS_PRE_PROTOCOLO = {"aprovada", "final"}




def _status_value(status) -> str | None:
    if status is None:
        return None
    return status.value if hasattr(status, "value") else str(status)


def _parse_score(prompt: str | None) -> int | None:
    import re
    m = re.search(r"score_confianca\s*[:=]\s*(\d{1,3})", prompt or "", re.I)
    if not m:
        return None
    return max(0, min(100, int(m.group(1))))


def _parse_veredito(prompt: str | None) -> str | None:
    import re
    m = re.search(r"veredito\s*[:=]\s*([^\n\r]+)", prompt or "", re.I)
    return m.group(1).strip()[:80] if m else None


_VALIDACAO_TIPO_FILTRO = or_(
    AILog.resposta.ilike("%RELATORIO DE VALIDACAO JURIDICA%"),
    AILog.prompt_sanitizado.ilike("%RELATORIO DE VALIDACAO JURIDICA%"),
    AILog.prompt_sanitizado.ilike("%VALIDACAO JURIDICA%"),
)


async def _ultima_validacao_peca(db: AsyncSession, doc: LegalDoc) -> dict:
    marcador = f"LEGAL_DOC_ID:{doc.id}"
    q = select(AILog).where(
        AILog.prompt_sanitizado.ilike(f"%{marcador}%"),
        _VALIDACAO_TIPO_FILTRO,
    ).order_by(AILog.created_at.desc())
    log = (await db.execute(q.limit(1))).scalar_one_or_none()
    return _montar_validacao(log)


async def _validacoes_por_peca(db: AsyncSession, docs: list[LegalDoc]) -> dict[str, dict]:
    """Resolve a última validação de VÁRIAS peças em UMA query (evita N+1).

    Busca todos os AILog de validação que citem qualquer marcador da página e,
    percorrendo do mais recente ao mais antigo, fica com o primeiro (mais novo)
    de cada peça.
    """
    resultado: dict[str, dict] = {d.id: _montar_validacao(None) for d in docs}
    doc_ids = [d.id for d in docs]
    if not doc_ids:
        return resultado
    marcadores = or_(*[
        AILog.prompt_sanitizado.ilike(f"%LEGAL_DOC_ID:{did}%") for did in doc_ids
    ])
    q = select(AILog).where(marcadores, _VALIDACAO_TIPO_FILTRO).order_by(
        AILog.created_at.desc()
    )
    logs = (await db.execute(q)).scalars().all()
    vistos: set[str] = set()
    for log in logs:
        prompt = log.prompt_sanitizado or ""
        for did in doc_ids:
            if did not in vistos and f"LEGAL_DOC_ID:{did}" in prompt:
                resultado[did] = _montar_validacao(log)
                vistos.add(did)
                break
        if len(vistos) == len(doc_ids):
            break
    return resultado


def _montar_validacao(log: AILog | None) -> dict:
    if not log:
        return {
            "status": "sem_validacao",
            "apto_fluxo": False,
            "score": None,
            "veredito": None,
            "ai_log_id": None,
            "hitl": None,
            "motivo": "Execute a validacao juridica da peca e marque o log como revisado ou aplicado.",
        }
    score = _parse_score(log.prompt_sanitizado)
    veredito = _parse_veredito(log.prompt_sanitizado)
    hitl = _status_value(log.status_hitl)
    revisada = hitl in ("revisado", "aplicado")
    score_ok = score is not None and score >= VALIDACAO_SCORE_MINIMO
    bloqueada = (veredito or "").upper().startswith("BLOQUEAR")
    apto = revisada and score_ok and not bloqueada
    if apto:
        status = "validada"
        motivo = "Validacao juridica revisada/aplicada e score minimo atendido."
    elif not revisada:
        status = "pendente_revisao"
        motivo = "Validacao gerada, mas ainda nao marcada como revisada ou aplicada no HITL."
    elif not score_ok:
        status = "score_baixo"
        motivo = f"Score inferior ao minimo de {VALIDACAO_SCORE_MINIMO}/100."
    else:
        status = "bloqueada"
        motivo = "Veredito operacional bloqueia o avanco ate correcao."
    return {
        "status": status,
        "apto_fluxo": apto,
        "score": score,
        "score_minimo": VALIDACAO_SCORE_MINIMO,
        "veredito": veredito,
        "ai_log_id": log.id,
        "hitl": hitl,
        "created_at": log.created_at,
        "motivo": motivo,
    }


async def _bloquear_sem_validacao(db: AsyncSession, doc: LegalDoc, novo_status: str | None):
    if novo_status not in STATUS_EXIGE_VALIDACAO:
        return
    validacao = await _ultima_validacao_peca(db, doc)
    if not validacao.get("apto_fluxo"):
        raise HTTPException(
            status_code=422,
            detail=(
                "Peca bloqueada por controle de qualidade: para aprovar/finalizar/protocolar, "
                f"e necessario validacao juridica revisada ou aplicada com score minimo de "
                f"{VALIDACAO_SCORE_MINIMO}/100. Status atual: {validacao.get('status')}. "
                f"{validacao.get('motivo')}"
            ),
        )


_JURIS_CATEGORIAS = {
    "jurisprudencia", "jurisprudencia_tjmg_acordaos", "jurisprudencia_tjmg_juizados",
    "sentencas_jec_tjmg", "fonaje_enunciados", "stj_juizados", "datajud_metadados",
    "sumula_stf", "sumula_stj", "sumula_tst",
}
_CITACAO_CNJ_RE = r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b"
_URL_OFICIAL_RE = r"https?://[^\s)\]]*(?:tjmg\.jus\.br|cnj\.jus\.br|stj\.jus\.br|stf\.jus\.br|fonaje\.amb\.com\.br)[^\s)\]]*"
_LINHA_JURIS_RE = r"\b(jurisprudencia|jurisprudencial|acordao|ementa|relator|turma recursal|camara|tjmg|stj|stf|resp|aresp|agint|sumula)\b"


def _linhas_jurisprudenciais(conteudo: str) -> list[str]:
    import re
    linhas = []
    for linha in (conteudo or "").splitlines():
        limpa = linha.strip()
        if len(limpa) < 12:
            continue
        if re.search(r"\b(sem|nao ha|não há|inexistente)\s+(citacao\s+de\s+)?jurisprud", limpa, flags=re.I):
            continue
        if re.search(_LINHA_JURIS_RE, limpa, flags=re.I):
            linhas.append(limpa[:500])
    return linhas


async def _fonte_juris_validada(db: AsyncSession, *, numero: str | None = None, url: str | None = None) -> bool:
    if not numero and not url:
        return False
    q = select(KnowledgeDoc).where(KnowledgeDoc.deleted_at.is_(None), KnowledgeDoc.categoria.in_(_JURIS_CATEGORIAS))
    if numero:
        q = q.where(or_(KnowledgeDoc.fonte.ilike(f"%{numero}%"), KnowledgeDoc.extra["numero_processo"].astext == numero))
    if url:
        q = q.where(KnowledgeDoc.fonte.ilike(f"%{url[:240]}%"))
    rows = (await db.execute(q.limit(10))).scalars().all()
    for d in rows:
        ex = d.extra or {}
        if ex.get("fonte_validada") is True and ex.get("confidence_level") in ("alta", "media") and ex.get("rag_status") in ("aprovado", "disponivel"):
            return True
    return False


async def _auditar_jurisprudencia_peca(db: AsyncSession, conteudo: str) -> dict:
    import re
    numeros = sorted(set(re.findall(_CITACAO_CNJ_RE, conteudo or "")))
    urls = sorted(set(re.findall(_URL_OFICIAL_RE, conteudo or "", flags=re.I)))
    linhas = _linhas_jurisprudenciais(conteudo or "")
    problemas: list[str] = []
    validadas: list[str] = []

    for numero in numeros:
        if await _fonte_juris_validada(db, numero=numero):
            validadas.append(numero)
        else:
            problemas.append(f"Jurisprudencia com processo {numero} nao localizada na base validada.")
    for url in urls:
        if await _fonte_juris_validada(db, url=url):
            validadas.append(url)
        else:
            problemas.append(f"Fonte oficial citada nao esta cadastrada/validada na base: {url[:160]}")

    # Se a peca fala em jurisprudencia/acordao/sumula sem numero, URL oficial ou sumula identificada, bloquear.
    linhas_sem_id = []
    for linha in linhas:
        tem_numero = re.search(_CITACAO_CNJ_RE, linha)
        tem_url = re.search(_URL_OFICIAL_RE, linha, flags=re.I)
        tem_sumula_id = re.search(r"\b[Ss]umula\s+(?:vinculante\s+)?\d+\b", linha)
        if not (tem_numero or tem_url or tem_sumula_id):
            linhas_sem_id.append(linha)
    if linhas_sem_id:
        problemas.append("Ha citacao jurisprudencial sem numero/link oficial/sumula identificada: " + linhas_sem_id[0][:220])

    return {
        "apto": not problemas,
        "problemas": problemas,
        "citacoes_validadas": validadas,
        "citacoes_detectadas": {"processos": numeros, "urls": urls, "linhas_jurisprudenciais": len(linhas)},
        "regra": "Peca final nao pode citar jurisprudencia como confirmada sem fonte validada na base MG/JEC/RAG.",
    }


async def _bloquear_jurisprudencia_nao_validada(db: AsyncSession, doc: LegalDoc, novo_status: str | None):
    if novo_status not in STATUS_EXIGE_VALIDACAO:
        return
    auditoria = await _auditar_jurisprudencia_peca(db, doc.conteudo or "")
    if not auditoria.get("apto"):
        raise HTTPException(
            status_code=422,
            detail={
                "mensagem": "Peca bloqueada: jurisprudencia citada sem validacao oficial na base.",
                "auditoria_jurisprudencia": auditoria,
            },
        )


async def _bg_checklist_protocolo(case_id: str, user_id: str):
    """Antes do protocolo: gera checklist por legislação (rascunho HITL). Fail-safe."""
    from app.core.database import AsyncSessionLocal
    from app.services.checklist_ia import gerar_checklist_ia
    try:
        async with AsyncSessionLocal() as bgdb:
            await gerar_checklist_ia(bgdb, case_id, "pre_protocolo", user_id)
    except Exception as e:
        logging.getLogger("ejc.legal_docs").warning(f"checklist pre_protocolo falhou: {e}")


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    case_id: Optional[str] = None,
    status_f: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(LegalDoc).where(LegalDoc.deleted_at.is_(None))
    # Ownership por caso (IDOR): não-gestão só vê peças dos seus casos
    # (responsável/auxiliar/sem-dono) ou sem caso vinculado.
    if not is_gestao(cu):
        casos_visiveis = select(Case.id).where(
            Case.deleted_at.is_(None),
            (
                (Case.advogado_responsavel_id == cu.id)
                | (Case.advogado_auxiliar_id == cu.id)
                | (Case.advogado_responsavel_id.is_(None) & Case.advogado_auxiliar_id.is_(None))
            ),
        )
        q = q.where(LegalDoc.case_id.is_(None) | LegalDoc.case_id.in_(casos_visiveis))
    if case_id:
        q = q.where(LegalDoc.case_id == case_id)
    if status_f:
        q = q.where(LegalDoc.status == status_f)
    q = q.order_by(LegalDoc.created_at.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    validacoes = await _validacoes_por_peca(db, rows)
    data = []
    for d in rows:
        item = LegalDocResponse.model_validate(d).model_dump(mode="json")
        item["validacao_juridica"] = validacoes[d.id]
        data.append(item)
    return {"data": data, "total": total, "page": page, "page_size": page_size}


@router.post("/", response_model=LegalDocDetail, status_code=201)
async def criar(
    payload: LegalDocCreate,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if getattr(payload, "case_id", None):
        await verificar_acesso_caso(db, cu, payload.case_id)
    dados = payload.model_dump()
    dados["titulo"] = padronizar_documento_juridico(dados.get("titulo", ""))[:255]
    dados["conteudo"] = padronizar_documento_juridico(dados.get("conteudo", ""))
    d = LegalDoc(
        id=str(uuid4()), created_by=cu.id,
        **dados,
    )
    db.add(d)
    await criar_audit_log(
        db, cu.id, cu.role.value, "CREATE", "legal_docs", d.id,
        detalhes=f"IA={payload.ai_generated}",
    )
    await db.commit()
    await db.refresh(d)
    # ETAPA 2 — produção interna alimenta a RAG (sanitizada, classificada).
    background.add_task(indexar_peca_rag, d.id)
    return d


@router.get("/{doc_id}")
async def detalhe(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(
        select(LegalDoc).where(
            LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    # Ownership (IDOR): peça vinculada a caso só é visível a quem tem o caso.
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)
    item = LegalDocDetail.model_validate(d).model_dump(mode="json")
    item["validacao_juridica"] = await _ultima_validacao_peca(db, d)
    return item


@router.get("/{doc_id}/validacao")
async def status_validacao_juridica(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(select(LegalDoc).where(LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)))).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)
    return await _ultima_validacao_peca(db, d)


@router.post("/{doc_id}/validar")
async def validar_peca_juridica(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(select(LegalDoc).where(LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)))).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    escopo_cli = None
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)
        from app.services.ai_service import _escopo_cliente_do_caso
        escopo_cli = await _escopo_cliente_do_caso(db, d.case_id)
    payload = ValidacaoInput(
        rascunho=d.conteudo,
        tipo_documento=_status_value(d.tipo_peca) or "peca_juridica",
        area=None,
        rito=None,
        fase="fluxo_peca_pre_finalizacao",
        documentos=[f"LEGAL_DOC_ID:{d.id}", f"TITULO:{d.titulo}", f"STATUS_ATUAL:{_status_value(d.status)}"],
        case_id=d.case_id,
        nivel_inteligencia="alto",
    )
    resultado = await validar_rascunho_juridico(payload, db=db, user_id=cu.id, scope_client_id=escopo_cli)
    await criar_audit_log(db, cu.id, cu.role.value, "VALIDACAO_JURIDICA", "legal_docs", doc_id, detalhes=f"score={resultado.get('score_confianca')}")
    await db.commit()
    return resultado


@router.patch("/{doc_id}", response_model=LegalDocDetail)
async def atualizar(
    doc_id: str, payload: LegalDocUpdate,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(
        select(LegalDoc).where(
            LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)

    mudancas = payload.model_dump(exclude_unset=True)
    if "titulo" in mudancas and mudancas["titulo"] is not None:
        mudancas["titulo"] = padronizar_documento_juridico(mudancas["titulo"])[:255]
    if "conteudo" in mudancas and mudancas["conteudo"] is not None:
        mudancas["conteudo"] = padronizar_documento_juridico(mudancas["conteudo"])

    # ── BLOQUEIO HITL (em código, não só UI) ───────────────────────────
    novo_status = mudancas.get("status")
    if (novo_status in STATUS_EXIGE_REVISAO
            and d.ai_generated and not d.human_reviewed):
        raise HTTPException(
            status_code=422,
            detail="Peca gerada por IA exige revisao humana registrada antes de aprovar (use POST /legal-docs/{id}/revisar). Provimento OAB 205/2021.",
        )
    await _bloquear_sem_validacao(db, d, novo_status)
    await _bloquear_jurisprudencia_nao_validada(db, d, novo_status)

    # Edição de conteúdo incrementa versão
    if "conteudo" in mudancas and mudancas["conteudo"] != d.conteudo:
        d.versao += 1

    status_antigo = d.status.value if hasattr(d.status, "value") else d.status
    for k, v in mudancas.items():
        setattr(d, k, v)
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", "legal_docs", doc_id)
    await db.commit()
    await db.refresh(d)
    # #CHK gatilho 2 — ao APROVAR/FINALIZAR a peça (pronta p/ protocolo), gera o
    # checklist pré-protocolo (rascunho HITL) em background. Só na transição.
    ns = mudancas.get("status")
    ns = ns.value if hasattr(ns, "value") else ns
    if ns in _STATUS_PRE_PROTOCOLO and status_antigo not in _STATUS_PRE_PROTOCOLO and d.case_id:
        background.add_task(_bg_checklist_protocolo, d.case_id, cu.id)
    return d


@router.get("/{doc_id}/jurisprudencia-check")
async def checar_jurisprudencia_peca(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(select(LegalDoc).where(LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)))).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)
    return await _auditar_jurisprudencia_peca(db, d.conteudo or "")


@router.post("/{doc_id}/revisar", response_model=LegalDocDetail)
async def revisar(
    doc_id: str, payload: LegalDocRevisao,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Registro de revisão humana — desbloqueia aprovação de peça IA."""
    d = (await db.execute(
        select(LegalDoc).where(
            LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)

    d.human_reviewed = payload.aprovado
    d.revisor_id = cu.id
    d.revisado_em = datetime.now(timezone.utc)
    d.notas_revisao = payload.notas
    d.status = PecaStatus.corrigida if payload.aprovado else PecaStatus.em_revisao

    await criar_audit_log(
        db, cu.id, cu.role.value, "REVISAO_HITL", "legal_docs", doc_id,
        detalhes=f"aprovado={payload.aprovado}",
    )
    await db.commit()
    await db.refresh(d)
    # ETAPA 2 — re-indexa a versão revisada (qualidade validada) na RAG.
    if payload.aprovado:
        background.add_task(indexar_peca_rag, doc_id)
    return d


@router.patch("/{doc_id}/aprovar", response_model=LegalDocDetail)
async def aprovar(
    doc_id: str, payload: LegalDocAprovacao,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """BUG-08: aprovação HITL da peça.

    Registra a revisão humana (human_reviewed) e avança o status para 'aprovada'.
    Peça gerada por IA (ai_generated) EXIGE observações de revisão — sem elas,
    a aprovação é recusada (422). Mantém os gates de qualidade existentes
    (validação jurídica + jurisprudência) coerentes com o fluxo do PATCH.
    """
    d = (await db.execute(
        select(LegalDoc).where(
            LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)

    observacoes = (payload.observacoes or "").strip()
    if d.ai_generated and not observacoes:
        raise HTTPException(
            status_code=422,
            detail="Peças geradas por IA exigem observações de revisão humana",
        )

    # Gates de qualidade (mesmos do PATCH) antes de chegar a 'aprovada'.
    novo_status = PecaStatus.aprovada.value
    await _bloquear_sem_validacao(db, d, novo_status)
    await _bloquear_jurisprudencia_nao_validada(db, d, novo_status)

    status_antigo = _status_value(d.status)
    d.human_reviewed = True
    d.revisor_id = cu.id
    d.revisado_em = datetime.now(timezone.utc)
    d.notas_revisao = observacoes or d.notas_revisao
    d.status = PecaStatus.aprovada

    await criar_audit_log(
        db, cu.id, cu.role.value, "APROVAR_HITL", "legal_docs", doc_id,
        detalhes=f"ai_generated={d.ai_generated}",
    )
    await db.commit()
    await db.refresh(d)
    # Re-indexa a versão aprovada na RAG e dispara checklist pré-protocolo.
    background.add_task(indexar_peca_rag, doc_id)
    if status_antigo not in _STATUS_PRE_PROTOCOLO and d.case_id:
        background.add_task(_bg_checklist_protocolo, d.case_id, cu.id)
    return d


@router.delete("/{doc_id}", response_model=MsgResponse)
async def remover(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(
        select(LegalDoc).where(
            LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)
    d.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "legal_docs", doc_id)
    await db.commit()
    return MsgResponse(detail="Peça removida")


# ═══ Exportação em PDF timbrado (logo institucional embutido) ═══
import io
import re as _re

from fastapi.responses import Response, StreamingResponse
from app.services.pdf_service import peca_para_pdf_async
from app.services.docx_service import gerar_docx_async

_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _slug_arquivo(titulo: str, fallback: str = "documento") -> str:
    """Slug ASCII seguro p/ Content-Disposition filename."""
    import unicodedata
    base = unicodedata.normalize("NFKD", titulo or "").encode("ascii", "ignore").decode("ascii")
    slug = _re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:60]
    return slug or fallback


async def _gates_exportacao_protocolo(db: AsyncSession, d: LegalDoc) -> None:
    """Gates compartilhados das exportações FINAIS de PDF (/pdf e
    /documento-unico-impressao): peça aprovada/final/protocolada com validação
    jurídica apta + jurisprudência citada validada na base. Extraído verbatim
    do /pdf — mesmas mensagens e status codes (contrato do frontend/testes)."""
    status_atual = _status_value(d.status)
    validacao = await _ultima_validacao_peca(db, d)
    pronto_protocolo = status_atual in STATUS_EXIGE_VALIDACAO and validacao.get("apto_fluxo")
    if not pronto_protocolo:
        raise HTTPException(
            status_code=422,
            detail=(
                "PDF de protocolo bloqueado: a peca precisa estar aprovada/final/protocolada "
                "e ter validacao juridica revisada ou aplicada com score minimo antes da exportacao final. "
                f"Status da peca: {status_atual}. Validacao: {validacao.get('status')}. "
                f"{validacao.get('motivo')}"
            ),
        )

    auditoria_juris = await _auditar_jurisprudencia_peca(db, d.conteudo or "")
    if not auditoria_juris.get("apto"):
        raise HTTPException(
            status_code=422,
            detail={
                "mensagem": "PDF de protocolo bloqueado: jurisprudencia citada sem validacao oficial na base.",
                "auditoria_jurisprudencia": auditoria_juris,
            },
        )


@router.get("/{doc_id}/pdf")
async def exportar_pdf(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(
        select(LegalDoc).where(LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")

    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)

    await _gates_exportacao_protocolo(db, d)

    titulo = padronizar_documento_juridico(d.titulo)
    conteudo = padronizar_documento_juridico(d.conteudo)

    try:
        pdf_bytes = await peca_para_pdf_async(
            titulo, conteudo, pronto_protocolo=True,
            codigo_peca=d.codigo_peca, versao=d.versao,
            status=d.status, revisado_em=d.revisado_em,
            minuta_ia=bool(d.ai_generated and not d.human_reviewed),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    await criar_audit_log(db, cu.id, cu.role.value, "DOWNLOAD", "legal_docs",
                          doc_id, detalhes="Exportacao PDF protocolo")
    await db.commit()

    # Filename ASCII (Content-Disposition é latin-1): dobra só o NOME DO
    # ARQUIVO — o conteúdo do PDF preserva a acentuação.
    safe_name = _slug_arquivo(titulo, fallback="peca")
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
    )


# ═══ Documento Único de Impressão (Visual Law) ═══
# Peça pronta para protocolo + relação/capas "DOC. NN" + anexos reais mesclados
# num único PDF — o pacote que vai para impressão/protocolo físico, no padrão
# da petição de referência do escritório.

@router.get(
    "/{doc_id}/documento-unico-impressao",
    dependencies=[Depends(rate_limit("legal-docs-doc-unico-impressao", 5))],
)
async def documento_unico_impressao(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Gera o Documento Único de Impressão: PDF da peça (pronto_protocolo=True)
    seguido, quando o caso tem acervo probatório, do bloco de anexos Visual Law
    (capa + índice + separadores "DOC. NN" + arquivos reais mesclados).

    Decisão de produto: diferente do /pdf (exportação de protocolo, bloqueada
    até a validação), este endpoint sai em QUALQUER status — a peça é rascunho
    no fluxo HITL, mas o PDF já tem a forma do documento final protocolável.
    O controle de revisão permanece no status da LegalDoc (o PATCH continua
    exigindo revisão humana para aprovar); a auditoria de jurisprudência roda
    de forma NÃO bloqueante e fica registrada no audit log.
    Sem caso ou sem provas, devolve só o PDF da peça (ainda é o documento de
    impressão).
    """
    import asyncio

    from app.models.document import Document
    from app.models.prova import Prova
    from app.routers.documents import _pode_acessar_confidencial
    from app.services import anexos_service

    # Piso de papel do fluxo de anexos (anexos.py:_pode_gerar): este endpoint
    # exporta BYTES de arquivos do caso — a regra anti-lockout do ownership
    # sozinha liberaria qualquer interno em caso órfão (achado A3 da auditoria).
    if ROLE_LEVEL.get(getattr(cu.role, "value", str(cu.role)), 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(403, "Acesso restrito a advogado ou superior.")

    d = (await db.execute(
        select(LegalDoc).where(LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")

    case = None
    if d.case_id:
        case = await verificar_acesso_caso(db, cu, d.case_id)

    # Auditoria de jurisprudência NÃO bloqueante (vs. /pdf, onde bloqueia):
    # o resultado vai para o audit log — rastro de que o rascunho impresso
    # ainda carregava citação não validada.
    auditoria_juris = await _auditar_jurisprudencia_peca(db, d.conteudo or "")

    titulo = padronizar_documento_juridico(d.titulo)
    conteudo = padronizar_documento_juridico(d.conteudo)
    try:
        pdf_final = await peca_para_pdf_async(
            titulo, conteudo, pronto_protocolo=True,
            codigo_peca=d.codigo_peca, versao=d.versao,
            status=d.status, revisado_em=d.revisado_em,
            # Este endpoint exporta em QUALQUER status (rascunho incluso): a marca
            # de origem-IA precisa viajar com o PDF de impressão do rascunho.
            minuta_ia=bool(d.ai_generated and not d.human_reviewed),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Bloco de anexos: acervo probatório do caso na MESMA ordenação do gerador
    # de provas (ordem, created_at) — o "(doc. NN)" citado na peça (padrão-ouro)
    # casa 1:1 com as capas "DOC. NN" do bloco mesclado.
    total_anexos = 0
    if case is not None:
        # deleted_at do Document no ON (não no WHERE): arquivo eliminado do GED
        # (inclusive por pedido LGPD) não entra no pacote, mas a Prova permanece
        # — a capa "DOC. NN" sai sem o anexo, preservando a numeração da peça.
        rows = (await db.execute(
            select(Prova, Document)
            .outerjoin(Document, and_(
                Document.id == Prova.document_id,
                Document.deleted_at.is_(None),
                # Trava anti-IDOR de leitura (achado A4): o invariante "prova
                # aponta para doc do mesmo caso" é garantido na escrita, mas
                # re-verificar aqui protege contra drift futuro (ex.: mover
                # documento de caso).
                Document.case_id == d.case_id,
            ))
            .where(Prova.case_id == d.case_id, Prova.deleted_at.is_(None))
            .order_by(Prova.ordem, Prova.created_at)
        )).all()
        # Cofre de confidencialidade (achado A1): mesmo gate do download direto
        # do GED — doc restrito/confidencial/segredo_justica exige socio+. 403
        # explícito em vez de excluir silenciosamente: pacote incompleto seria
        # protocolado sem o advogado perceber.
        bloqueados = [
            doc.titulo for _, doc in rows
            if doc is not None and not _pode_acessar_confidencial(cu, doc.confidencialidade.value)
        ]
        if bloqueados:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Documento(s) sob confidencialidade no acervo do caso exigem "
                    f"perfil sócio ou superior para exportação: {', '.join(bloqueados[:5])}"
                ),
            )
        if rows:
            ctx = await anexos_service.montar_contexto(db, case, None)
            itens = anexos_service.itens_de_provas(rows)
            try:
                pdf_anexos = await anexos_service.montar_documento_unico(ctx, itens)
                pdf_final = await asyncio.get_event_loop().run_in_executor(
                    None, anexos_service.mesclar_pdfs, [pdf_final, pdf_anexos]
                )
            except (RuntimeError, ImportError) as e:
                # Falha aqui NÃO degrada silenciosamente para peça-sem-anexos:
                # o advogado protocolaria um pacote incompleto sem perceber.
                raise HTTPException(status_code=503, detail=f"Geração do bloco de anexos indisponível: {e}")
            total_anexos = len(itens)

    await criar_audit_log(
        db, cu.id, cu.role.value, "DOWNLOAD", "legal_docs", doc_id,
        detalhes=(
            f"Documento unico de impressao ({total_anexos} anexo(s); "
            f"status={_status_value(d.status)}; "
            f"jurisprudencia_apta={bool(auditoria_juris.get('apto'))})"
        ),
    )
    await db.commit()

    filename = f"{_slug_arquivo(titulo, fallback='peca')}-documento-unico.pdf"
    return Response(
        content=pdf_final, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ═══ Exportação em DOCX editável (Times 12pt, ABNT — R7 auditoria) ═══
@router.get("/{doc_id}/exportar-docx")
async def exportar_docx(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Exporta a peça em DOCX editável (versão de trabalho — não substitui o
    PDF de protocolo). Gate idêntico ao GET do detalhe: 404 se inexistente,
    ownership do caso (IDOR) quando a peça está vinculada a um caso.
    """
    d = (await db.execute(
        select(LegalDoc).where(LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")

    meta: dict = {}
    if d.case_id:
        case = await verificar_acesso_caso(db, cu, d.case_id)
        if case.numero_processo:
            meta["numero_processo"] = case.numero_processo

    # Controle/versionamento (Fase D): meta é render-only, nunca toca o conteúdo.
    from app.services.peca_numeracao import linha_controle, status_label
    meta["codigo_peca"] = d.codigo_peca
    meta["versao"] = d.versao
    meta["status"] = status_label(d.status)
    meta["linha_controle"] = linha_controle(
        codigo_peca=d.codigo_peca, titulo=d.titulo, versao=d.versao,
        status=d.status, revisado_em=d.revisado_em,
    )
    # Marca de origem-IA embutida na 1ª página SÓ para rascunho não-revisado
    # (ai_generated e não human_reviewed). O advogado precisa baixar o DOCX para
    # editar — nada de gate de bloqueio; a marca d'água na minuta é a salvaguarda.
    meta["minuta_ia"] = bool(d.ai_generated and not d.human_reviewed)

    titulo = padronizar_documento_juridico(d.titulo)
    conteudo = padronizar_documento_juridico(d.conteudo)

    try:
        docx_bytes = await gerar_docx_async(titulo, conteudo, meta)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    await criar_audit_log(db, cu.id, cu.role.value, "DOWNLOAD", "legal_docs",
                          doc_id, detalhes="Exportacao DOCX editavel")
    await db.commit()

    filename = f"{_slug_arquivo(titulo, fallback='peca')}.docx"
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type=_DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

