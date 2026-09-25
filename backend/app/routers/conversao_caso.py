"""Conversão para judicial — POST /cases/{case_id}/converter-judicial

MIGRADO (E2): cria um PROCESSO no PRÓPRIO caso (entidade `processes`, 1 Caso : N),
em vez de clonar o caso num segundo registro. Marca o caso como judicial e mantém
todos os satélites (deadlines, documents, fees, movimentos) no mesmo case_id —
elimina a duplicação Caso×Processo. linked_judicial_case_id deixa de ser usado
(preservado só p/ casos legados já vinculados). Agora com RBAC (lacuna do audit).

#CHK: ao judicializar, dispara em background a geração do checklist por legislação
(gatilho=pre_processo) — rascunho HITL, fail-safe (não bloqueia nem quebra a conversão).

#R8 (auditoria pré-redesign): CHECKLIST BLOQUEANTE de conversão.
- GET  /cases/{case_id}/converter-judicial/checklist → 8 verificações {key, titulo, ok, detalhe}.
- POST /cases/{case_id}/converter-judicial só executa se pronto=true; senão 422
  {detail: {mensagem, pendentes}}. Ownership via verificar_acesso_caso em ambos.
"""
import logging
from datetime import date
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func, or_
from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import require_roles
from app.models.ai_log import AILog, AIStatusHITL, AITipoUso
from app.models.audit_log import AuditLog, criar_audit_log
from app.models.case import Case
from app.models.caso_area import CasoArea
from app.models.checklist import CaseChecklist, CaseChecklistItem, ChecklistStatus
from app.models.client import Client
from app.models.deadline import Deadline, DeadlineStatus
from app.models.fee import Fee, FeeStatus
from app.models.procuracao import Procuracao
from app.models.tese import TeseCasoLink
from app.models.user import User
from app.schemas.redesign import ConversaoChecklistResponse
from app.schemas.process import ProcessCreate
from app.services.conflito_service import detectar_conflito
from app.services.processo_service import ProcessConflict, criar_processo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases/{case_id}/converter-judicial", tags=["Conversão de Caso"])

_ESCRITA = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar"]


async def _bg_gerar_checklist(case_id: str, user_id: str):
    """Background: gera checklist por legislação (rascunho) ao judicializar. Fail-safe."""
    from app.core.database import AsyncSessionLocal
    from app.services.checklist_ia import gerar_checklist_ia
    try:
        async with AsyncSessionLocal() as bgdb:
            await gerar_checklist_ia(bgdb, case_id, "pre_processo", user_id)
    except Exception as e:
        logger.warning(f"[conversao] checklist IA automático falhou p/ caso {case_id}: {e}")


# ── #R8: cômputo das 8 verificações bloqueantes ──────────────────────────────
async def _computar_checklist(db: AsyncSession, case: Case) -> tuple[list[dict], bool]:
    """
    Computa as 8 verificações do checklist de conversão extrajudicial→judicial.
    Retorna (itens, pronto). Cada item: {key, titulo, ok, detalhe}.
    LGPD: os detalhes NUNCA incluem CPF/CNPJ/e-mail — apenas nomes de campos.
    """
    itens: list[dict] = []
    hoje = date.today()

    client = (await db.execute(
        select(Client).where(Client.id == case.client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()

    # 1. qualificacao_completa — nome + CPF/CNPJ + endereço do cliente
    faltas: list[str] = []
    if client is None:
        faltas.append("cliente do caso não encontrado (ou excluído)")
    else:
        if not (client.nome or client.razao_social):
            faltas.append("nome/razão social")
        if not (client.cpf_enc or client.cnpj_enc):
            faltas.append("CPF/CNPJ")
        end_faltas = [rotulo for rotulo, valor in (
            ("logradouro", client.logradouro), ("número", client.numero),
            ("cidade", client.cidade), ("UF", client.estado),
        ) if not valor]
        if end_faltas:
            faltas.append("endereço: " + ", ".join(end_faltas))
    itens.append({
        "key": "qualificacao_completa",
        "titulo": "Qualificação completa do cliente",
        "ok": not faltas,
        "detalhe": ("Nome, CPF/CNPJ e endereço preenchidos."
                    if not faltas else "Pendente — " + "; ".join(faltas)),
    })

    # 2. documentos_obrigatorios — itens obrigatórios do checklist do caso concluídos
    n_checklists = (await db.execute(
        select(func.count()).select_from(CaseChecklist).where(
            CaseChecklist.case_id == case.id,
            CaseChecklist.status != ChecklistStatus.cancelado,
        )
    )).scalar_one()
    if n_checklists == 0:
        docs_ok, docs_det = False, "Caso sem checklist — instancie o checklist da área."
    else:
        pend_obrig = (await db.execute(
            select(func.count()).select_from(CaseChecklistItem)
            .join(CaseChecklist, CaseChecklist.id == CaseChecklistItem.case_checklist_id)
            .where(
                CaseChecklist.case_id == case.id,
                CaseChecklist.status != ChecklistStatus.cancelado,
                CaseChecklistItem.obrigatorio.is_(True),
                CaseChecklistItem.concluido.is_(False),
            )
        )).scalar_one()
        docs_ok = pend_obrig == 0
        docs_det = ("Todos os itens obrigatórios do checklist estão concluídos."
                    if docs_ok else f"{pend_obrig} item(ns) obrigatório(s) pendente(s) no checklist do caso.")
    itens.append({
        "key": "documentos_obrigatorios",
        "titulo": "Documentos/itens obrigatórios do checklist da área",
        "ok": docs_ok, "detalhe": docs_det,
    })

    # 3. procuracao_valida — ativa (não revogada) e vigente (validade nula = indeterminada)
    n_proc = (await db.execute(
        select(func.count()).select_from(Procuracao).where(
            Procuracao.client_id == case.client_id,
            Procuracao.deleted_at.is_(None),
            or_(Procuracao.revogada.is_(False), Procuracao.revogada.is_(None)),
            or_(Procuracao.data_validade.is_(None), Procuracao.data_validade >= hoje),
        )
    )).scalar_one()
    itens.append({
        "key": "procuracao_valida",
        "titulo": "Procuração ativa e vigente",
        "ok": n_proc > 0,
        "detalhe": (f"{n_proc} procuração(ões) vigente(s) do cliente." if n_proc > 0
                    else "Nenhuma procuração vigente (não revogada e dentro da validade) para o cliente."),
    })

    # 4. area_confirmada — campo area do Case OU registro em caso_areas
    n_areas = (await db.execute(
        select(func.count()).select_from(CasoArea).where(CasoArea.case_id == case.id)
    )).scalar_one()
    area_val = case.area.value if hasattr(case.area, "value") else case.area
    area_ok = bool(area_val) or n_areas > 0
    itens.append({
        "key": "area_confirmada",
        "titulo": "Área do direito confirmada",
        "ok": area_ok,
        "detalhe": (f"Área: {area_val or '(multi-área)'}"
                    + (f" + {n_areas} registro(s) em caso_areas." if n_areas else ".")
                    if area_ok else "Caso sem área definida — defina a área principal."),
    })

    # 5. tese_aprovada — tese vinculada E nenhum AILog de tese (analise_caso) pendente de revisão
    n_teses = (await db.execute(
        select(func.count()).select_from(TeseCasoLink).where(TeseCasoLink.case_id == case.id)
    )).scalar_one()
    n_ia_pend = (await db.execute(
        select(func.count()).select_from(AILog).where(
            AILog.case_id == case.id,
            AILog.tipo_uso == AITipoUso.analise_caso,
            AILog.status_hitl == AIStatusHITL.gerado,
        )
    )).scalar_one()
    tese_ok = n_teses > 0 and n_ia_pend == 0
    if n_teses == 0:
        tese_det = "Nenhuma tese vinculada ao caso — vincule a tese aplicável."
    elif n_ia_pend > 0:
        tese_det = f"{n_teses} tese(s) vinculada(s), mas {n_ia_pend} sugestão(ões) de IA pendente(s) de revisão (HITL)."
    else:
        tese_det = f"{n_teses} tese(s) vinculada(s); sem sugestões de IA pendentes de revisão."
    itens.append({
        "key": "tese_aprovada",
        "titulo": "Tese vinculada e revisada (HITL)",
        "ok": tese_ok, "detalhe": tese_det,
    })

    # 6. valor_definido — valor_causa OU honorário cadastrado
    n_fees = (await db.execute(
        select(func.count()).select_from(Fee).where(
            Fee.case_id == case.id,
            Fee.deleted_at.is_(None),
            Fee.status != FeeStatus.cancelado,
        )
    )).scalar_one()
    valor_ok = case.valor_causa is not None or n_fees > 0
    itens.append({
        "key": "valor_definido",
        "titulo": "Valor da causa ou honorário definido",
        "ok": valor_ok,
        "detalhe": ("Valor da causa preenchido." if case.valor_causa is not None
                    else (f"{n_fees} honorário(s) cadastrado(s)." if n_fees > 0
                          else "Sem valor da causa e sem honorário cadastrado.")),
    })

    # 7. conflito_verificado — reusa registro CONFLICT_CHECK (conflito_interesses grava
    #    no audit log); se ausente/não conclusivo, executa detectar_conflito on-the-fly.
    ultimo_check = (await db.execute(
        select(AuditLog).where(
            AuditLog.acao == "CONFLICT_CHECK",
            AuditLog.registro_id == case.id,
        ).order_by(AuditLog.created_at.desc()).limit(1)
    )).scalars().first()
    if ultimo_check is not None and "sem_conflito" in (ultimo_check.detalhes or "").lower():
        conf_ok, conf_det = True, "Verificação registrada no audit log: sem_conflito."
    else:
        resultado = await detectar_conflito(
            db,
            nome=(client.nome or client.razao_social) if client else None,
            cpf=client.cpf_plain if client else None,
            cnpj=client.cnpj_plain if client else None,
            parte_contraria=case.parte_contraria,
            ignorar_client_id=case.client_id,
        )
        conf_ok = resultado["classificacao"] == "SEM_CONFLITO"
        conf_det = (f"Verificação on-the-fly: {resultado['classificacao']} "
                    f"({len(resultado['achados'])} achado(s)).")
    itens.append({
        "key": "conflito_verificado",
        "titulo": "Conflito de interesses verificado (EOAB arts. 34-35)",
        "ok": conf_ok, "detalhe": conf_det,
    })

    # 8. prazos_vinculados — >=1 prazo ativo (pendente) com responsável
    n_prazos = (await db.execute(
        select(func.count()).select_from(Deadline).where(
            Deadline.case_id == case.id,
            Deadline.deleted_at.is_(None),
            Deadline.status == DeadlineStatus.pendente,
            Deadline.responsavel_id.is_not(None),
        )
    )).scalar_one()
    itens.append({
        "key": "prazos_vinculados",
        "titulo": "Prazo ativo com responsável definido",
        "ok": n_prazos > 0,
        "detalhe": (f"{n_prazos} prazo(s) pendente(s) com responsável." if n_prazos > 0
                    else "Nenhum prazo ativo com responsável vinculado ao caso."),
    })

    pronto = all(i["ok"] for i in itens)
    return itens, pronto


@router.get("/checklist", response_model=ConversaoChecklistResponse)
async def checklist_conversao(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    """#R8: checklist bloqueante de conversão — 8 verificações {key, titulo, ok, detalhe}."""
    case = await verificar_acesso_caso(db, cu, case_id)
    itens, pronto = await _computar_checklist(db, case)
    return {"itens": itens, "pronto": pronto}


@router.post("", status_code=201)
async def converter_judicial(
    case_id: str,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    # Achado de forma independente por duas frentes: só existência era checada,
    # não ownership — qualquer usuário com papel _ESCRITA podia converter/
    # escrever em processo de QUALQUER caso, não só os seus (mesmo padrão já
    # corrigido em processes.py). Ownership (RBAC + ABAC): 404 se não existe,
    # 403 se sem permissão. Retorna o Case ORM completo (necessário p/
    # _computar_checklist mais abaixo, que acessa client_id/area/etc.).
    orig = await verificar_acesso_caso(db, cu, case_id)

    # Evita duplicar: se já há processo judicial neste caso, recusa.
    ja = (await db.execute(text("""
        SELECT 1 FROM processes
        WHERE case_id = :cid AND tipo = 'judicial' AND deleted_at IS NULL LIMIT 1
    """), {"cid": case_id})).first()
    if ja:
        raise HTTPException(409, "Este caso já possui um processo judicial")

    # #R8: gate bloqueante — só converte com o checklist 100% ok.
    itens, pronto = await _computar_checklist(db, orig)
    if not pronto:
        pendentes = [i for i in itens if not i["ok"]]
        # Audit da tentativa bloqueada (sem writes pendentes até aqui — commit seguro).
        await criar_audit_log(
            db, cu.id, cu.role.value, "CONVERTER_JUDICIAL_BLOQUEADO", "cases", case_id,
            detalhes="Conversão bloqueada — pendentes: " + ", ".join(i["key"] for i in pendentes),
        )
        await db.commit()
        raise HTTPException(status_code=422, detail={
            "mensagem": "Conversão bloqueada — itens pendentes",
            "pendentes": pendentes,
        })

    # Cria o Processo pelo serviço canônico: preserva lock Caso -> CNJ,
    # valida DV e impede que o mesmo CNJ seja associado a outro Caso.
    try:
        processo = await criar_processo(
            case_id,
            ProcessCreate(
                numero_cnj=orig.numero_processo or None,
                tribunal=orig.tribunal,
                comarca=orig.comarca,
                vara=orig.vara,
                tipo="judicial",
                valor_causa=orig.valor_causa,
                status="ativo",
                is_principal=True,
            ),
            db,
        )
    except ProcessConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    pid = processo["id"]

    # Marca o caso como judicial (mantém continuidade e satélites no mesmo case_id).
    await db.execute(text("""
        UPDATE cases SET case_type = 'judicial', has_judicial_process = true, updated_at = now()
        WHERE id = :cid
    """), {"cid": case_id})

    await db.execute(text("""
        INSERT INTO case_movimentos (id, case_id, tipo, descricao, created_by, created_at)
        VALUES (:id, :cid, 'nota', :desc, :uid, now())
    """), {"id": str(uuid4()), "cid": case_id,
           "desc": "Caso judicializado — processo judicial criado no próprio caso.",
           "uid": cu.id})

    await criar_audit_log(
        db, cu.id, cu.role.value, "CONVERTER_JUDICIAL", "processes", pid,
        detalhes="Checklist de conversão (R8) aprovado: 8/8 verificações ok.",
    )
    await db.commit()

    # #CHK: gera o checklist por legislação em background (não bloqueia a resposta).
    background.add_task(_bg_gerar_checklist, case_id, cu.id)

    return {"ok": True, "case_id": case_id, "process_id": pid, "checklist": "gerando"}
