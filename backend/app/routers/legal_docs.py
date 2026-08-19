# ── app/routers/legal_docs.py ────────────────────────────────────────────────
# Peças jurídicas com HITL ENFORÇADO:
# ai_generated=True NÃO avança para aprovada/final sem human_reviewed=True.
# Bloqueio em nível de código — não apenas UI.
from __future__ import annotations
import hashlib
import logging
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import and_, select, func as sqlfunc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, requer_advogado, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso, is_gestao
from app.core.status_caso import filtrar_pecas_visiveis
from app.models.case import Case
from app.models.document import Document
from app.models.user import User
from app.models.legal_doc import LegalDoc, PecaStatus
from app.models.ai_log import AILog, AIStatusHITL
from app.models.rag import KnowledgeDoc
from app.models.audit_log import criar_audit_log
from app.services.case_intel import indexar_peca_rag
from app.services.document_format import padronizar_documento_juridico
from app.services.validador_juridico_service import ValidacaoInput, validar_rascunho_juridico
from app.schemas.legal_doc import (
    LegalDocCreate, LegalDocUpdate, LegalDocRevisao, LegalDocAprovacao,
    LegalDocProtocolo, LegalDocResponse, LegalDocDetail,
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

    # Logs novos usam marcador estrutural curto no início do prompt; logs já
    # existentes continuam compatíveis com a chave histórica da rubrica.
    m = re.search(
        r"(?:VALIDATION_SCORE|score_confianca)\s*[:=]\s*(\d{1,3})",
        prompt or "",
        re.I,
    )
    if not m:
        return None
    return max(0, min(100, int(m.group(1))))


def _parse_veredito(prompt: str | None) -> str | None:
    import re

    m = re.search(
        r"(?:VALIDATION_VERDICT|veredito)\s*[:=]\s*([^\n\r]+)",
        prompt or "",
        re.I,
    )
    return m.group(1).strip()[:80] if m else None


def _hash_conteudo_validado(conteudo: str | None) -> str:
    return hashlib.sha256((conteudo or "").encode("utf-8")).hexdigest()


async def _ultima_validacao_peca(db: AsyncSession, doc: LegalDoc) -> dict:
    """Retorna somente validação estrutural da versão corrente da peça.

    Fail-closed: FK, flag de atualidade e SHA-256 precisam coincidir. Nenhum
    marcador textual é usado para correlacionar LegalDoc e AILog.
    """
    content_hash = _hash_conteudo_validado(doc.conteudo)
    q = (
        select(AILog)
        .where(
            AILog.legal_doc_id == doc.id,
            AILog.legal_doc_validation_current.is_(True),
            AILog.legal_doc_content_hash == content_hash,
        )
        .order_by(AILog.created_at.desc())
    )
    log = (await db.execute(q.limit(1))).scalar_one_or_none()
    return _montar_validacao(log)


async def _validacoes_por_peca(db: AsyncSession, docs: list[LegalDoc]) -> dict[str, dict]:
    """Resolve a validação corrente de várias peças em uma única query.

    A associação é feita diretamente por ``ai_logs.legal_doc_id``. O hash é
    conferido por peça para impedir que drift de trigger, restore parcial ou
    dado legado torne uma validação antiga apta para a versão atual.
    """
    resultado: dict[str, dict] = {d.id: _montar_validacao(None) for d in docs}
    if not docs:
        return resultado

    hashes = {d.id: _hash_conteudo_validado(d.conteudo) for d in docs}
    q = (
        select(AILog)
        .where(
            AILog.legal_doc_id.in_(list(hashes)),
            AILog.legal_doc_validation_current.is_(True),
        )
        .order_by(AILog.created_at.desc())
    )
    logs = (await db.execute(q)).scalars().all()
    vistos: set[str] = set()
    for log in logs:
        doc_id = log.legal_doc_id
        if not doc_id or doc_id in vistos or doc_id not in hashes:
            continue
        if log.legal_doc_content_hash != hashes[doc_id]:
            continue
        resultado[doc_id] = _montar_validacao(log)
        vistos.add(doc_id)
        if len(vistos) == len(hashes):
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
    q = filtrar_pecas_visiveis(q)
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
        try:
            q = q.where(LegalDoc.status == PecaStatus(status_f))
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Status de peça inválido: {status_f!r}. Valores aceitos: "
                    f"{', '.join(s.value for s in PecaStatus)}. "
                    "Para não filtrar por status, omita o parâmetro."
                ),
            ) from None
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
    if getattr(payload, "case_id", None):
        from app.services.status_transicao import avancar_status_pos_commit
        await avancar_status_pos_commit(
            db, payload.case_id, "peca_criada", user_id=cu.id
        )
    await db.refresh(d)
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
    try:
        resultado = await validar_rascunho_juridico(payload, db=db, user_id=cu.id, scope_client_id=escopo_cli)
    except RuntimeError as exc:
        from app.core.ai_errors import http_erro_ia
        raise http_erro_ia(exc, 503, contexto="validar_peca_juridica")
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
        ).with_for_update()
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

    novo_status = _status_value(mudancas.get("status"))
    status_atual = _status_value(d.status)
    conteudo_alterado = (
        "conteudo" in mudancas and mudancas["conteudo"] != d.conteudo
    )

    campos_imutaveis_protocolados = {
        "titulo", "conteudo", "tipo_peca", "status", "ai_generated"
    }
    if (
        status_atual == "protocolada"
        and campos_imutaveis_protocolados.intersection(mudancas)
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Peça protocolada é imutável. Crie uma nova peça ou versão para "
                "qualquer alteração posterior ao protocolo."
            ),
        )

    if conteudo_alterado and novo_status in STATUS_EXIGE_VALIDACAO:
        raise HTTPException(
            status_code=422,
            detail=(
                "Conteúdo alterado exige novo ciclo: salve a edição, valide, "
                "revise e somente depois aprove/finalize/protocole."
            ),
        )

    if (novo_status in STATUS_EXIGE_REVISAO
            and d.ai_generated and not d.human_reviewed):
        raise HTTPException(
            status_code=422,
            detail="Peca gerada por IA exige revisao humana registrada antes de aprovar (use POST /legal-docs/{id}/revisar). Provimento OAB 205/2021.",
        )
    if novo_status == "protocolada" and status_atual != "protocolada":
        requer_advogado(
            cu, detail="Marcar peça como protocolada é restrito a advogados"
        )
        if not (d.numero_protocolo or "").strip():
            raise HTTPException(
                status_code=422,
                detail=(
                    "Registre o protocolo antes de mudar o status: "
                    "PATCH /legal-docs/{id}/protocolo (número/tribunal/data). "
                    "A peça ainda não possui numero_protocolo."
                ),
            )
    await _bloquear_sem_validacao(db, d, novo_status)
    await _bloquear_jurisprudencia_nao_validada(db, d, novo_status)

    if conteudo_alterado:
        d.versao += 1
        d.human_reviewed = False
        d.revisor_id = None
        d.revisado_em = None
        d.notas_revisao = None
        if status_atual in STATUS_EXIGE_REVISAO or status_atual == "corrigida":
            mudancas["status"] = PecaStatus.em_revisao

    status_antigo = d.status.value if hasattr(d.status, "value") else d.status
    for k, v in mudancas.items():
        setattr(d, k, v)
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", "legal_docs", doc_id)
    await db.commit()
    await db.refresh(d)
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
    """Registra revisão humana e aplica o gate antialucinação da validação atual."""
    requer_advogado(cu, detail="Registrar revisão de peça é restrito a advogados")
    d = (await db.execute(
        select(LegalDoc).where(
            LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)
        ).with_for_update()
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)

    if payload.aprovado:
        validacao = await _ultima_validacao_peca(db, d)
        ai_log_id = validacao.get("ai_log_id")
        if ai_log_id:
            log = (
                await db.execute(
                    select(AILog).where(AILog.id == ai_log_id).with_for_update()
                )
            ).scalar_one_or_none()
            if log is not None and _status_value(log.status_hitl) not in ("revisado", "aplicado"):
                from app.services.citation_gate import aplicar_gate_hitl

                await aplicar_gate_hitl(db, log, "revisado", False, None, cu)
                log.status_hitl = AIStatusHITL.revisado
                log.revisado_por = cu.id
                log.revisado_em = datetime.now(timezone.utc)
                await db.flush()

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
    requer_advogado(cu, detail="Aprovar peça é restrito a advogados")
    d = (await db.execute(
        select(LegalDoc).where(
            LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)
        ).with_for_update()
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
    background.add_task(indexar_peca_rag, doc_id)
    if status_antigo not in _STATUS_PRE_PROTOCOLO and d.case_id:
        background.add_task(_bg_checklist_protocolo, d.case_id, cu.id)
    return d


@router.post("/{doc_id}/conferir-e-assinar")
async def conferir_e_assinar(
    doc_id: str, payload: LegalDocAprovacao,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """UM ato de conferência e assinatura, no lugar de quatro chamadas.

    Consolida validação, HITL, gates jurídicos e assinatura em uma transação,
    sem dispensar a revisão profissional do advogado.
    """
    requer_advogado(cu, detail="Conferir e assinar peça é restrito a advogados")
    d = (await db.execute(
        select(LegalDoc).where(
            LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)
        ).with_for_update()
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")

    status_atual_peca = _status_value(d.status)
    if status_atual_peca in ("final", "protocolada"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Peça em status '{status_atual_peca}' já passou da assinatura e é "
                "imutável neste fluxo. Crie uma nova peça ou versão para qualquer alteração."
            ),
        )

    escopo_cli = None
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)
        from app.services.ai_service import _escopo_cliente_do_caso
        escopo_cli = await _escopo_cliente_do_caso(db, d.case_id)

    observacoes = (payload.observacoes or "").strip()
    if d.ai_generated and not observacoes:
        raise HTTPException(
            status_code=422,
            detail="Peças geradas por IA exigem observações de revisão humana",
        )

    validacao = await _ultima_validacao_peca(db, d)
    validou_agora = False
    if validacao.get("ai_log_id") is None:
        payload_validacao = ValidacaoInput(
            rascunho=d.conteudo,
            tipo_documento=_status_value(d.tipo_peca) or "peca_juridica",
            area=None,
            rito=None,
            fase="fluxo_peca_pre_finalizacao",
            documentos=[
                f"LEGAL_DOC_ID:{d.id}",
                f"TITULO:{d.titulo}",
                f"STATUS_ATUAL:{_status_value(d.status)}",
            ],
            case_id=d.case_id,
            nivel_inteligencia="alto",
        )
        try:
            resultado = await validar_rascunho_juridico(
                payload_validacao, db=db, user_id=cu.id,
                scope_client_id=escopo_cli, commit=False,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        validou_agora = True
        await criar_audit_log(
            db, cu.id, cu.role.value, "VALIDACAO_JURIDICA", "legal_docs", doc_id,
            detalhes=f"score={resultado.get('score_confianca')} (conferir-e-assinar)",
        )
        validacao = await _ultima_validacao_peca(db, d)

    ai_log_id = validacao.get("ai_log_id")
    if ai_log_id and validacao.get("hitl") not in ("revisado", "aplicado"):
        log = (await db.execute(
            select(AILog).where(AILog.id == ai_log_id).with_for_update()
        )).scalar_one_or_none()
        if log is not None:
            if log.user_id != cu.id and ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
                raise HTTPException(
                    status_code=403,
                    detail="Sem permissão para revisar este log",
                )
            from app.services.citation_gate import aplicar_gate_hitl
            await aplicar_gate_hitl(
                db, log, "revisado", bool(payload.override_citacoes),
                payload.justificativa_override, cu,
            )
            log.status_hitl = AIStatusHITL.revisado
            log.revisado_por = cu.id
            log.revisado_em = datetime.now(timezone.utc)
            await criar_audit_log(
                db, cu.id, cu.role.value, "REVISAO_HITL", "ai_logs", ai_log_id,
                detalhes=f"revisado junto da assinatura da peca {doc_id}",
            )
            await db.flush()
            validacao = await _ultima_validacao_peca(db, d)

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
        detalhes=(
            f"conferir-e-assinar; ai_generated={d.ai_generated}; "
            f"validou_agora={validou_agora}; ai_log_id={ai_log_id}; "
            f"override_citacoes={bool(payload.override_citacoes)}"
        ),
    )
    await db.commit()
    await db.refresh(d)

    background.add_task(indexar_peca_rag, doc_id)
    if status_antigo not in _STATUS_PRE_PROTOCOLO and d.case_id:
        background.add_task(_bg_checklist_protocolo, d.case_id, cu.id)

    return {
        "peca": LegalDocDetail.model_validate(d).model_dump(mode="json"),
        "validacao": validacao,
        "validou_agora": validou_agora,
        "pdf_protocolo": f"/legal-docs/{doc_id}/pdf",
    }


@router.patch("/{doc_id}/protocolo", response_model=LegalDocDetail)
async def registrar_protocolo(
    doc_id: str, payload: LegalDocProtocolo,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    require_status = STATUS_EXIGE_REVISAO
    requer_advogado(cu, detail="Registro de protocolo é restrito a advogados")
    d = (await db.execute(
        select(LegalDoc).where(
            LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)
        ).with_for_update()
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)

    status_atual = _status_value(d.status)
    if status_atual not in require_status:
        raise HTTPException(
            status_code=422,
            detail=(
                "Protocolo só pode ser registrado em peça aprovada. "
                f"Status atual: '{status_atual}'. Aprove a peça "
                "(POST /legal-docs/{id}/aprovar ou PATCH de status) antes de registrar o protocolo."
            ),
        )

    numero = (payload.numero_protocolo or "").strip()
    if not numero:
        raise HTTPException(status_code=422, detail="Número de protocolo é obrigatório")

    d.numero_protocolo = numero[:120]
    tribunal = (payload.protocolo_tribunal or "").strip()
    d.protocolo_tribunal = tribunal[:120] or None
    d.protocolado_em = payload.protocolado_em or datetime.now(timezone.utc)
    comprovante = (payload.protocolo_comprovante_doc_id or "").strip()
    if comprovante:
        if not d.case_id:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Comprovante inválido: a peça precisa estar vinculada a um "
                    "caso para receber comprovante de protocolo"
                ),
            )
        doc = (await db.execute(
            select(Document).where(
                Document.id == comprovante, Document.deleted_at.is_(None)
            )
        )).scalar_one_or_none()
        if doc is None:
            raise HTTPException(
                status_code=422,
                detail="Comprovante inválido: documento não encontrado ou excluído",
            )
        if doc.case_id != d.case_id:
            raise HTTPException(
                status_code=422,
                detail="Comprovante inválido: o documento não pertence ao caso desta peça",
            )
    comprovante_antigo = d.protocolo_comprovante_doc_id
    d.protocolo_comprovante_doc_id = comprovante or None

    await criar_audit_log(
        db, cu.id, cu.role.value, "PROTOCOLO_REGISTRADO", "legal_docs", doc_id,
        detalhes=(
            f"numero={numero} tribunal={d.protocolo_tribunal or '-'} "
            f"protocolado_em={d.protocolado_em.isoformat()} "
            f"comprovante={comprovante_antigo or '-'}→{d.protocolo_comprovante_doc_id or '-'}"
        ),
    )
    case_id_peca = d.case_id
    await db.commit()
    if case_id_peca:
        from app.services.status_transicao import avancar_status_pos_commit
        await avancar_status_pos_commit(
            db, case_id_peca, "peca_protocolada", user_id=cu.id
        )
    await db.refresh(d)
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
    import unicodedata
    base = unicodedata.normalize("NFKD", titulo or "").encode("ascii", "ignore").decode("ascii")
    slug = _re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:60]
    return slug or fallback


async def _gates_exportacao_protocolo(db: AsyncSession, d: LegalDoc) -> dict:
    status_atual = _status_value(d.status)
    if d.ai_generated and not d.human_reviewed:
        raise HTTPException(
            status_code=422,
            detail=(
                "PDF de protocolo bloqueado: peça gerada por IA exige "
                "revisão humana registrada antes da exportação final."
            ),
        )
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

    return {
        "validacao": validacao,
        "auditoria_jurisprudencia": auditoria_juris,
    }


@router.get("/{doc_id}/pdf-minuta")
async def exportar_pdf_minuta(
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

    titulo = padronizar_documento_juridico(d.titulo)
    conteudo = padronizar_documento_juridico(d.conteudo)

    try:
        pdf_bytes = await peca_para_pdf_async(
            titulo, conteudo, pronto_protocolo=False,
            codigo_peca=d.codigo_peca, versao=d.versao,
            status=d.status, revisado_em=d.revisado_em,
            minuta_ia=bool(d.ai_generated and not d.human_reviewed),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    await criar_audit_log(db, cu.id, cu.role.value, "DOWNLOAD", "legal_docs",
                          doc_id, detalhes="Exportacao PDF minuta (leitura)")
    await db.commit()

    safe_name = _slug_arquivo(titulo, fallback="minuta")
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-minuta.pdf"'},
    )


@router.get("/{doc_id}/pdf")
async def exportar_pdf(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(
        select(LegalDoc).where(LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)).with_for_update()
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

    safe_name = _slug_arquivo(titulo, fallback="peca")
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
    )


@router.get(
    "/{doc_id}/documento-unico-impressao",
    dependencies=[Depends(rate_limit("legal-docs-doc-unico-impressao", 5))],
)
async def documento_unico_impressao(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    import asyncio

    from app.models.document import Document
    from app.models.prova import Prova
    from app.routers.documents import _pode_acessar_confidencial
    from app.services import anexos_service

    if ROLE_LEVEL.get(getattr(cu.role, "value", str(cu.role)), 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(403, "Acesso restrito a advogado ou superior.")

    d = (await db.execute(
        select(LegalDoc).where(LegalDoc.id == doc_id, LegalDoc.deleted_at.is_(None)).with_for_update()
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Peça não encontrada")

    case = None
    if d.case_id:
        case = await verificar_acesso_caso(db, cu, d.case_id)

    gate_result = await _gates_exportacao_protocolo(db, d)
    auditoria_juris = gate_result["auditoria_jurisprudencia"]

    titulo = padronizar_documento_juridico(d.titulo)
    conteudo = padronizar_documento_juridico(d.conteudo)
    try:
        pdf_final = await peca_para_pdf_async(
            titulo, conteudo, pronto_protocolo=True,
            codigo_peca=d.codigo_peca, versao=d.versao,
            status=d.status, revisado_em=d.revisado_em,
            minuta_ia=bool(d.ai_generated and not d.human_reviewed),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    total_anexos = 0
    if case is not None:
        rows = (await db.execute(
            select(Prova, Document)
            .outerjoin(Document, and_(
                Document.id == Prova.document_id,
                Document.deleted_at.is_(None),
                Document.case_id == d.case_id,
            ))
            .where(Prova.case_id == d.case_id, Prova.deleted_at.is_(None))
            .order_by(Prova.ordem, Prova.created_at)
        )).all()
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


@router.get("/{doc_id}/exportar-docx")
async def exportar_docx(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
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

    from app.services.peca_numeracao import linha_controle, status_label
    meta["codigo_peca"] = d.codigo_peca
    meta["versao"] = d.versao
    meta["status"] = status_label(d.status)
    meta["linha_controle"] = linha_controle(
        codigo_peca=d.codigo_peca, titulo=d.titulo, versao=d.versao,
        status=d.status, revisado_em=d.revisado_em,
    )
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
