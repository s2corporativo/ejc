"""
documento_ia.py — Importação inteligente de documentos.
POST /api/documentos-ia/analisar  (multipart: file)
  → OCR + extração estruturada + diagnóstico jurídico + honorários + referências.
POST /api/documentos-ia/analisar-url (JSON: url, case_id opcional)
  → importação segura de página pública + dossiê jurídico + análise opcional.
POST /api/documentos-ia/aplicar-acoes (JSON: case_id, intake_result)
  → materializa prazos/tarefas da análise como RASCUNHO (revisão humana
  obrigatória; nunca aplica automaticamente).
Retorna JSON que o frontend usa para pré-preencher um novo caso (sem duplicar a
criação de casos — usa o /cases existente).
"""
import os
import tempfile
import logging
from datetime import date
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.case import Case, CaseMovimento
from app.models.user import User
from app.schemas.document_intake import DocumentoIntakeResult
from app.services import documento_service
from app.services.ai_contextual import classificar_documento
from app.services.document_url_import_service import importar_url_juridica

logger = logging.getLogger("ejc.documento_ia")
router = APIRouter(prefix="/documentos-ia", tags=["Importação Inteligente"])

MAX_BYTES = 25 * 1024 * 1024  # 25 MB
TIPOS_OK = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "image/png", "image/jpeg", "image/jpg", "image/tiff", "image/webp",
}


class AnalisarUrlRequest(BaseModel):
    """Prévia de importação jurídica por URL pública."""

    url: str = Field(..., min_length=8, max_length=2048)
    titulo: Optional[str] = Field(None, max_length=255)
    case_id: Optional[str] = Field(None, description="Caso existente para análise estratégica opcional")
    executar_analise: bool = Field(
        False,
        description="Quando true e case_id informado, roda análise estratégica como rascunho.",
    )


def _aplicar_classificacao_contextual(
    resultado: dict,
    *,
    filename: str | None,
    texto_sanitizado: str,
) -> dict:
    """Acrescenta área, subárea, rito e ações por regras locais auditáveis.

    A classificação contextual só prevalece sobre a classificação genérica do
    LLM quando há área específica e confiança suficiente. A origem anterior é
    preservada para conferência humana.
    """
    classificacao = classificar_documento(filename, texto_sanitizado)
    resultado["classificacao_contextual"] = classificacao
    resultado["acoes_contextuais_sugeridas"] = classificacao.get("skills_sugeridas", [])

    area = classificacao.get("area_sugerida")
    confianca = float(classificacao.get("confianca") or 0)
    if area and confianca >= 0.64:
        atual = dict(resultado.get("classificacao") or {})
        area_anterior = atual.get("area")
        if area_anterior and area_anterior != area:
            atual["area_anterior"] = area_anterior
        atual["area"] = area
        atual["subarea"] = classificacao.get("subarea_sugerida") or atual.get("subarea")
        atual["rito"] = classificacao.get("rito_sugerido") or atual.get("rito")
        atual["tipo_documento_contextual"] = classificacao.get("tipo")
        atual["confianca_contextual"] = confianca
        atual["origem_classificacao"] = classificacao.get("metodo")
        atual["requer_confirmacao_humana"] = True
        resultado["classificacao"] = atual

        intake = resultado.get("intake_result")
        if isinstance(intake, dict):
            caso = intake.get("caso")
            if not isinstance(caso, dict):
                caso = {}
            caso["area"] = area
            caso["ramo_direito"] = area
            if classificacao.get("rito_sugerido"):
                caso["rito"] = classificacao["rito_sugerido"]
            intake["caso"] = caso

    return resultado


@router.post("/analisar")
async def analisar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload de PDF/DOCX/imagem → análise jurídica estruturada (HITL)."""
    mimetype = file.content_type or ""
    if mimetype not in TIPOS_OK:
        # alguns navegadores mandam octet-stream; deixamos o OCR decidir pela extensão
        if not (file.filename or "").lower().endswith((".pdf", ".docx", ".png", ".jpg", ".jpeg", ".tiff", ".webp")):
            raise HTTPException(415, "Formato não suportado. Envie PDF, DOCX ou imagem.")

    conteudo = await file.read()
    if len(conteudo) > MAX_BYTES:
        raise HTTPException(413, "Arquivo muito grande (máx. 25 MB).")
    if not conteudo:
        raise HTTPException(400, "Arquivo vazio.")

    # Validação por magic bytes (server-side) — reusa a barreira do GED. Não
    # confiar em content_type/extensão. Extensões sem mapa (.tiff/.webp) passam
    # pelo fallback e ainda assim têm o MIME real detectado; .pdf/.docx/.png/.jpg
    # ganham verificação estrita de conteúdo.
    sufixo = os.path.splitext(file.filename or "doc")[1] or ".bin"
    from app.routers.documents import _validar_conteudo
    mime_real = _validar_conteudo(sufixo.lower(), conteudo)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=sufixo)
    try:
        tmp.write(conteudo)
        tmp.flush()
        tmp.close()
        resultado = await documento_service.extrair_e_analisar(
            tmp.name, mime_real or mimetype or None, db=db, enriquecer_rag=True,
            user_id=current_user.id,
        )
        if not resultado.get("ok"):
            raise HTTPException(422, resultado.get("erro", "Falha ao processar documento."))

        # ── Núcleo Único de IA: o diagnóstico jurídico passa OBRIGATORIAMENTE
        # pelo orchestrator (permissões, policy de provider, validação de
        # citações, HITL e AILog). Os campos antigos do payload (extração
        # estruturada, honorários, referências) são preservados; os campos do
        # núcleo são ACRESCENTADOS — o frontend antigo continua funcionando.
        texto_sanitizado = resultado.pop("_texto_sanitizado", "") or ""
        _aplicar_classificacao_contextual(
            resultado,
            filename=file.filename,
            texto_sanitizado=texto_sanitizado,
        )

        # Retorno degradado (analise_llm_indisponivel=True): TODA a cadeia de
        # IA acabou de falhar no serviço — chamar o orchestrator agora só
        # adiciona latência para falhar de novo. Pula o núcleo e mantém o
        # aviso (aviso_llm) já presente no payload.
        if resultado.get("analise_llm_indisponivel"):
            resultado["diagnostico_nucleo"] = None
        elif texto_sanitizado:
            from app.services.ai.core.orchestrator import orchestrator
            try:
                nucleo = await orchestrator.run(
                    db=db,
                    user=current_user,
                    task_type="document_analysis",
                    domain="documents",
                    mensagem=(
                        "Analise juridicamente o documento abaixo (já sanitizado) e "
                        "aponte natureza, riscos, providências e pontos de atenção "
                        "para o advogado responsável. Considere a classificação local "
                        f"como sugestão revisável: {resultado.get('classificacao_contextual')}.\n\n"
                        "DOCUMENTO:\n"
                        f"{texto_sanitizado}"
                    ),
                    usar_rag=True,
                )
                resultado["diagnostico_nucleo"] = nucleo.get("conteudo")
                resultado["agente"] = nucleo.get("agente")
                resultado["modelo_nucleo"] = nucleo.get("modelo")
                resultado["provider"] = nucleo.get("provider")
                resultado["fontes"] = nucleo.get("fontes", [])
                resultado["citacoes"] = nucleo.get("citacoes", [])
                resultado["log_id"] = nucleo.get("log_id")
                resultado["is_rascunho"] = nucleo.get("is_rascunho", True)
                resultado["aviso_hitl"] = nucleo.get("aviso_hitl")
            except HTTPException as e:
                # Núcleo pode abortar (422 PII residual / policy). A extração
                # estruturada permanece útil — degrada com aviso, sem stack trace.
                logger.warning(f"Núcleo IA indisponível para diagnóstico: {e.detail}")
                resultado["diagnostico_nucleo"] = None
                resultado["nucleo_aviso"] = str(e.detail)[:300]
            except Exception as e:
                logger.warning(f"Núcleo IA falhou no diagnóstico: {type(e).__name__}")
                resultado["diagnostico_nucleo"] = None
                resultado["nucleo_aviso"] = "Diagnóstico pelo núcleo de IA indisponível no momento."
        return resultado
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


@router.post("/analisar-url")
async def analisar_url(
    req: AnalisarUrlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """URL pública → texto jurídico + dossiê + análise opcional.

    Esta rota NÃO grava automaticamente conteúdo externo no GED nem no caso. Ela
    cria uma prévia revisável para evitar reprodução indevida de conteúdo de
    terceiros e para manter revisão humana obrigatória.
    """
    caso = None
    if req.case_id:
        await verificar_acesso_caso(db, current_user, req.case_id)
        caso = (await db.execute(
            select(Case).where(Case.id == req.case_id, Case.deleted_at.is_(None))
        )).scalar_one_or_none()
        if not caso:
            raise HTTPException(status_code=404, detail="Caso não encontrado")

    resultado = await importar_url_juridica(req.url, titulo=req.titulo)
    out = resultado.model_dump() if hasattr(resultado, "model_dump") else resultado.dict()
    out["ok"] = not resultado.bloqueado
    out["origem"] = "url_publica"
    out["requer_revisao_humana"] = True
    out["pode_aplicar_ao_caso"] = bool(req.case_id and not resultado.bloqueado and resultado.dossie)
    out["diretriz_autoral"] = (
        "Use como referência jurídica revisável. Preferir resumo próprio, metadados, "
        "trechos curtos e link de origem; para jurisprudência, validar em fonte oficial."
    )

    if not req.executar_analise:
        return out

    if not caso:
        raise HTTPException(status_code=422, detail="Informe case_id para executar análise")
    if resultado.bloqueado or not resultado.dossie:
        out["analise"] = None
        out["analise_aviso"] = "Análise não executada porque a URL não gerou texto importável."
        return out

    try:
        from app.services.analise_estrategica import analisar_caso
        analise = await analisar_caso(
            titulo=caso.titulo or req.titulo or resultado.titulo or "Importação por URL",
            area=caso.area or "",
            numero_processo=caso.numero_processo or "",
            texto_documento=resultado.dossie,
            scope_client_id=caso.client_id,
            db=db,
        )
        out["analise"] = analise
        out["analise_aviso"] = "Análise gerada como rascunho. Revise antes de usar no caso."
    except Exception as exc:
        logger.warning("Análise de URL falhou: %s", type(exc).__name__)
        out["analise"] = None
        out["analise_aviso"] = f"Falha ao executar análise estratégica: {str(exc)[:180]}"

    return out


class AplicarAcoesRequest(BaseModel):
    """Materializa prazos/tarefas do `intake_result` (DocumentoIntakeResult,
    ver app/schemas/document_intake.py) de uma análise já feita via /analisar."""

    case_id: str
    intake_result: DocumentoIntakeResult
    criar_prazos: bool = True
    criar_tarefas: bool = True
    criar_alerta: bool = True
    responsavel_id: Optional[str] = None


@router.post("/aplicar-acoes",
             dependencies=[Depends(rate_limit("doc-aplicar-acoes", 15))])
async def aplicar_acoes(
    payload: AplicarAcoesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cria prazos/tarefas a partir de `intake_result`, sempre como rascunho
    pendente de validação humana (nunca aplica automaticamente).

    Consome o contrato tipado `DocumentoIntakeResult` (#83 Gap A): `prazos`
    já vem com `termo_final` em ISO e SÓ contém itens com data fatal
    parseável (documento_service._prazos_extraidos nunca inventa data);
    `pendencias` vira tarefa de revisão (PendenciaRevisao: descricao,
    campo_alvo, severidade).

    Segurança (revisão 2026-07-14):
    - `intake_result` valida contra o Pydantic real (não dict livre) — barra
      tipo/estrutura inválida antes de tocar o banco. Ainda assim o CONTEÚDO
      é fornecido pelo cliente (sem link para um AILog/análise persistida),
      então todo registro criado é rascunho auditável, nunca aplicado
      automaticamente a protocolo.
    - `responsavel_id` só pode ser outro usuário se ele tiver acesso
      legítimo ao MESMO caso (gestão ou responsável/auxiliar do caso) — evita
      atribuir prazo/tarefa/notificação a usuário arbitrário do sistema
      (inclusive cliente_externo).
    """
    caso = await verificar_acesso_caso(db, current_user, payload.case_id)

    from app.core.ownership import is_gestao
    from app.models.deadline import Deadline, DeadlinePrioridade, DeadlineTipo
    from app.models.notification import Notification
    from app.models.task import Task

    responsavel_id = payload.responsavel_id or current_user.id
    if payload.responsavel_id and payload.responsavel_id != current_user.id:
        alvo = await db.get(User, payload.responsavel_id)
        if not alvo or not (
            is_gestao(alvo)
            or alvo.id in (caso.advogado_responsavel_id, caso.advogado_auxiliar_id)
        ):
            raise HTTPException(422, "responsavel_id inválido para este caso")

    intake = payload.intake_result.model_dump(mode="json")
    prazos_criados: list[str] = []
    tarefas_criadas: list[str] = []

    def _sev_para_prioridade(sev: Optional[str]) -> str:
        s = (sev or "").lower()
        if s == "alta":
            return "alta"
        if s == "baixa":
            return "baixa"
        return "media"

    if payload.criar_prazos:
        for prazo in (intake.get("prazos") or [])[:20]:
            if not isinstance(prazo, dict):
                continue
            termo_final = prazo.get("termo_final")  # já ISO (aaaa-mm-dd) ou None
            if not termo_final:
                continue
            try:
                data_prazo = date.fromisoformat(str(termo_final)[:10])
            except ValueError:
                continue
            tipo_desc = prazo.get("tipo") or "Prazo extraído de documento"
            d = Deadline(
                id=str(uuid4()),
                titulo=f"Validar prazo — {str(tipo_desc)[:150]}",
                descricao=(
                    "Prazo identificado automaticamente em análise de documento. "
                    "Confira termo inicial, contagem, feriados, suspensão de "
                    "expediente e prazo em dobro antes de confiar nesta data."
                ),
                tipo=DeadlineTipo.processual,
                prioridade=(
                    DeadlinePrioridade.critica if prazo.get("fatal")
                    else DeadlinePrioridade.alta
                ),
                data_prazo=data_prazo,
                base_legal=str(prazo.get("base_legal") or "")[:255] or None,
                case_id=payload.case_id,
                responsavel_id=responsavel_id,
                observacoes="Criado automaticamente como rascunho. Ciência e revisão humana obrigatórias.",
                origem="ia_documento",
            )
            db.add(d)
            prazos_criados.append(d.id)

    if payload.criar_tarefas:
        for pend in (intake.get("pendencias") or [])[:15]:
            if not isinstance(pend, dict):
                continue
            desc = pend.get("descricao") or "Pendência identificada pela análise documental"
            t = Task(
                id=str(uuid4()),
                titulo=f"Revisar IA — {str(desc)[:180]}",
                descricao=(
                    f"Campo: {str(pend.get('campo_alvo') or '—')[:200]}\n\n"
                    "Tarefa criada a partir de análise automática de documento. "
                    "Revisão humana obrigatória."
                ),
                prioridade=_sev_para_prioridade(pend.get("severidade")),
                case_id=payload.case_id,
                responsavel_id=responsavel_id,
                criado_por=current_user.id,
            )
            db.add(t)
            tarefas_criadas.append(t.id)

    riscos = (intake.get("riscos") or [])[:50]
    risco_alto = any(
        isinstance(r, dict) and (r.get("impacto") or "").lower() == "alta"
        for r in riscos
    )
    if payload.criar_alerta and (prazos_criados or risco_alto):
        db.add(Notification(
            id=str(uuid4()),
            user_id=responsavel_id,
            titulo="Análise documental exige revisão",
            mensagem=(
                "Documento analisado por IA/OCR com prazo ou risco identificado. "
                "Validar manualmente antes de qualquer protocolo."
            ),
            tipo="ia",
            link=f"/casos/{payload.case_id}",
        ))

    db.add(CaseMovimento(
        id=str(uuid4()), case_id=payload.case_id, tipo="ia",
        descricao=(
            f"Análise documental aplicada: {len(prazos_criados)} prazo(s) e "
            f"{len(tarefas_criadas)} tarefa(s) criados como rascunho. Revisão humana obrigatória."
        ),
        created_by=current_user.id,
    ))
    await criar_audit_log(
        db, current_user.id, current_user.role.value,
        "AI_DOCUMENT_ACTIONS", "cases", payload.case_id,
        dados_depois={
            "prazos_criados": prazos_criados,
            "tarefas_criadas": tarefas_criadas,
            "responsavel_id": responsavel_id,
            "revisao_humana": True,
        },
    )
    await db.commit()
    return {
        "ok": True,
        "prazos_criados": prazos_criados,
        "tarefas_criadas": tarefas_criadas,
        "aviso": "Ações criadas como rascunho. Revisão humana obrigatória antes de uso jurídico.",
    }
