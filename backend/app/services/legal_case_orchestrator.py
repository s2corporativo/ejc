# ── app/services/legal_case_orchestrator.py ──────────────────────────────────
# FASE 5 do Orquestrador Jurídico — LegalCaseOrchestrator.
#
# Máquina de estados jurídicos que conduz o caso de ponta a ponta SOBRE os
# services já existentes (nunca reimplementa etapa nenhuma):
#   entrada → compreensao → classificacao → validacao_processual → estrategia
#   → contratacao → producao → revisao → protocolo → acompanhamento
#
# REGRAS INVIOLÁVEIS:
#   • O estado é DERIVADO dos ARTEFATOS reais do caso (snapshots, teses,
#     propostas, LegalDocs, Deadlines) — nunca de flag mutável. Fail-safe por
#     construção: erro em um service não corrompe o estado.
#   • O orquestrador NUNCA aprova nada sozinho: atos jurídicos (aprovar
#     snapshot/tese/proposta/peça, confirmar termo isolado) são recusados por
#     `avancar` com instrução do endpoint humano próprio.
#   • NUNCA cria Deadline fora dos gates do motor: a ação "gerar_peca" reusa o
#     handler /motor-peca/gerar (confirmar_e_criar_prazo — checklist bloqueante
#     + termo confirmado pelo advogado no próprio body).
#   • ZERO chamadas novas de LLM — a IA já vive dentro dos services chamados.
#   • Snapshot origem="orquestrador" registra a linha do tempo de transições
#     (payload.estado_orquestrador) via gravar_snapshot_seguro (fail-safe).
#
# ── DERIVAÇÃO DO ESTADO (documentação normativa; mais avançado vence) ─────────
#   acompanhamento       peça de produção protocolada (status=protocolada ou
#                        numero_protocolo preenchido)
#   protocolo            peça aprovada/final E Deadline confirmado (não
#                        cancelado) no caso
#   revisao              peça em em_revisao/corrigida, OU aprovada/final ainda
#                        sem Deadline confirmado
#   producao             peça de produção em rascunho
#   contratacao          proposta de honorários APROVADA vigente E kit gerado
#                        (LegalDoc procuração + contrato)
#   estrategia           matriz de teses montada (existe ThesisCandidate)
#   validacao_processual snapshot origem="motor_peca" (peças cabíveis + prazo
#                        projetado + checklist já analisados)
#   classificacao        algum snapshot de conteúdo CONGELADO (aprovação humana
#                        fixa área/rito — HITL da FASE 1)
#   compreensao          existe snapshot de conteúdo (triagem/intake/raio_x/
#                        matriz_teses/motor_peca/manual) — o caso já foi lido
#   entrada              nenhum artefato de inteligência
#
# "Peça de produção" = LegalDoc que NÃO é do kit documental: exclui tipos
# procuracao/contrato e o checklist do kit (tipo outro com "checklist" no
# título). Determinístico e documentado — sem heurística de IA.
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select

from app.core.ownership import role_str as _role_str
from app.core.rate_limit import consumir
from app.core.security import requer_advogado
from app.services.motor_peca_service import _enum_val
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.case_intelligence import CaseIntelligenceSnapshot
from app.models.deadline import Deadline
from app.models.document import Document
from app.models.fee_proposal import FeeProposal
from app.models.legal_doc import LegalDoc
from app.models.matriz_teses import ThesisCandidate
from app.models.user import User

logger = logging.getLogger("ejc.orquestrador")

ESTADOS: tuple[str, ...] = (
    "entrada", "compreensao", "classificacao", "validacao_processual",
    "estrategia", "contratacao", "producao", "revisao", "protocolo",
    "acompanhamento",
)

ROTULOS_ESTADO: dict[str, str] = {
    "entrada": "Entrada do caso",
    "compreensao": "Compreensão dos fatos",
    "classificacao": "Classificação (área e rito)",
    "validacao_processual": "Validação processual (peças e prazos)",
    "estrategia": "Estratégia (matriz de teses)",
    "contratacao": "Contratação (honorários e kit documental)",
    "producao": "Produção da peça",
    "revisao": "Revisão do advogado",
    "protocolo": "Protocolo",
    "acompanhamento": "Acompanhamento",
}

# Origens de snapshot que contam como "inteligência de conteúdo" (a origem
# "orquestrador" é só linha do tempo — nunca deriva estado sozinha).
_ORIGENS_CONTEUDO = ("triagem", "intake", "raio_x", "motor_peca", "manual",
                     "matriz_teses")

_TIPOS_KIT = ("procuracao", "contrato")


def _req_advogado(cu: User) -> None:
    """Defesa em profundidade: avançar o caso é ato de advogado+."""
    requer_advogado(cu, detail="Orquestrador restrito a advogados")


def _eh_peca_producao(doc: LegalDoc) -> bool:
    """Peça redigida (produção) ≠ documento do kit (procuração/contrato/checklist)."""
    tipo = _enum_val(getattr(doc, "tipo_peca", None)) or ""
    if tipo in _TIPOS_KIT:
        return False
    if tipo == "outro" and "checklist" in (doc.titulo or "").lower():
        return False
    return True


# ── Coleta de artefatos (ordem FIXA de consultas — contrato com os testes) ───

async def coletar_artefatos(db, case_id: str, case: Case | None = None) -> dict:
    """Fotografa os ARTEFATOS reais do caso em flags determinísticas.

    Ordem fixa das consultas (os testes _FakeDB dependem dela):
      (0) Case — apenas quando `case` não é passado pelo chamador;
      (1) snapshots (versão desc);  (2) teses candidatas;  (3) propostas;
      (4) LegalDocs vivos;          (5) Deadlines;         (6) nº docs com OCR;
      (7) nº de AILogs de validação jurídica das peças de produção — SÓ roda
          quando existe peça de produção (sem peça não há o que validar).
    """
    if case is None:
        case = (await db.execute(
            select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
        )).scalar_one_or_none()

    snaps = list((await db.execute(
        select(CaseIntelligenceSnapshot)
        .where(CaseIntelligenceSnapshot.case_id == case_id)
        .order_by(CaseIntelligenceSnapshot.versao.desc())
    )).scalars().all())
    teses = list((await db.execute(
        select(ThesisCandidate).where(ThesisCandidate.case_id == case_id)
    )).scalars().all())
    propostas = list((await db.execute(
        select(FeeProposal).where(FeeProposal.case_id == case_id)
    )).scalars().all())
    docs = list((await db.execute(
        select(LegalDoc).where(LegalDoc.case_id == case_id,
                               LegalDoc.deleted_at.is_(None))
    )).scalars().all())
    deadlines = list((await db.execute(
        select(Deadline).where(Deadline.case_id == case_id,
                               Deadline.deleted_at.is_(None))
    )).scalars().all())
    n_docs_ocr = (await db.execute(
        select(func.count()).select_from(Document).where(
            Document.case_id == case_id,
            Document.deleted_at.is_(None),
            Document.ocr_text.isnot(None),
        )
    )).scalar() or 0

    pecas = [d for d in docs if _eh_peca_producao(d)]

    # (7) "Citações verificadas" usa o mesmo contrato estrutural do
    # fluxo de peças: FK LegalDoc↔AILog, flag corrente e SHA-256 exato.
    n_validacoes = 0
    if pecas:
        import hashlib

        from app.models.ai_log import AILog

        hashes_por_peca = {
            d.id: hashlib.sha256((d.conteudo or "").encode("utf-8")).hexdigest()
            for d in pecas
        }
        pares_correntes = or_(*[
            and_(
                AILog.legal_doc_id == doc_id,
                AILog.legal_doc_content_hash == content_hash,
            )
            for doc_id, content_hash in hashes_por_peca.items()
        ])
        n_validacoes = (await db.execute(
            select(func.count()).select_from(AILog).where(
                AILog.legal_doc_id.in_(list(hashes_por_peca)),
                AILog.legal_doc_validation_current.is_(True),
                pares_correntes,
            )
        )).scalar() or 0

    snaps_conteudo = [s for s in snaps if s.origem in _ORIGENS_CONTEUDO]
    snaps_motor = [s for s in snaps_conteudo if s.origem == "motor_peca"]
    area_sugerida = next(
        (((s.payload or {}).get("area")) for s in snaps_conteudo
         if (s.payload or {}).get("area")), None)
    checklist_motor = next(
        (((s.payload or {}).get("checklist")) for s in snaps_motor
         if isinstance((s.payload or {}).get("checklist"), dict)), None)

    status_pecas = {_enum_val(d.status) for d in pecas}
    tipos_docs = {_enum_val(d.tipo_peca) for d in docs}

    return {
        "case": case,
        "snapshots": snaps,
        # snapshots ---------------------------------------------------------
        "tem_snapshot": bool(snaps_conteudo),
        "tem_snapshot_congelado": any(s.congelado for s in snaps_conteudo),
        "tem_snapshot_motor": bool(snaps_motor),
        "snapshot_atual_id": (snaps_conteudo[0].id if snaps_conteudo else None),
        "snapshot_atual_congelado": (bool(snaps_conteudo[0].congelado)
                                     if snaps_conteudo else False),
        "area_sugerida": area_sugerida,
        "checklist_motor": checklist_motor,
        # matriz de teses ---------------------------------------------------
        "matriz_montada": bool(teses),
        "tese_aprovada": any(t.status == "aprovada" for t in teses),
        # honorários --------------------------------------------------------
        "proposta_existe": bool(propostas),
        "proposta_aprovada": any(p.status == "aprovada" for p in propostas),
        # kit documental ----------------------------------------------------
        "tem_procuracao": "procuracao" in tipos_docs,
        "tem_contrato": "contrato" in tipos_docs,
        "kit_gerado": {"procuracao", "contrato"} <= tipos_docs,
        "tem_checklist_doc": any(
            _enum_val(d.tipo_peca) == "outro"
            and "checklist" in (d.titulo or "").lower() for d in docs),
        # peças de produção -------------------------------------------------
        "peca_rascunho": "rascunho" in status_pecas,
        "peca_em_revisao": bool({"em_revisao", "corrigida"} & status_pecas),
        "peca_aprovada": bool({"aprovada", "final"} & status_pecas),
        "peca_protocolada": ("protocolada" in status_pecas
                             or any(getattr(d, "numero_protocolo", None)
                                    for d in pecas)),
        "peca_ia": any(getattr(d, "ai_generated", False) for d in pecas),
        # CR-15: houve validação jurídica REGISTRADA de alguma peça de produção
        # (gate de citações executado) — sinal de _ultima_validacao_peca, não
        # o mero fato de a peça ser ai_generated.
        "peca_validada": bool(n_validacoes),
        # prazos ------------------------------------------------------------
        # Só Deadline nascido dos gates do próprio fluxo (motor_peca /
        # agente_juridico) conta como "prazo confirmado" para a máquina de
        # estados — prazo antigo/manual sem relação com a peça NÃO pode
        # empurrar o caso a "protocolo". Cancelado/soft-deletado nunca conta
        # (defesa em profundidade além do filtro SQL de deleted_at).
        "deadline_confirmado": any(
            bool(d.confirmado) and _enum_val(d.status) != "cancelado"
            and getattr(d, "deleted_at", None) is None
            and getattr(d, "origem", None) in ("motor_peca", "agente_juridico")
            for d in deadlines),
        # base fática -------------------------------------------------------
        "tem_base_fatica": bool(
            n_docs_ocr or (case is not None
                           and (case.descricao_fatos or "").strip())),
    }


def derivar_estado(art: dict) -> str:
    """Estado da máquina a partir dos artefatos (função PURA — ver docstring
    do módulo para a tabela normativa). Mais avançado vence."""
    if art["peca_protocolada"]:
        return "acompanhamento"
    if art["peca_aprovada"] and art["deadline_confirmado"]:
        return "protocolo"
    if art["peca_em_revisao"] or art["peca_aprovada"]:
        return "revisao"
    if art["peca_rascunho"]:
        return "producao"
    if art["proposta_aprovada"] and art["kit_gerado"]:
        return "contratacao"
    if art["matriz_montada"]:
        return "estrategia"
    if art["tem_snapshot_motor"]:
        return "validacao_processual"
    if art["tem_snapshot_congelado"]:
        return "classificacao"
    if art["tem_snapshot"]:
        return "compreensao"
    return "entrada"


async def estado_atual(db, case_id: str, case: Case | None = None) -> str:
    """Estado atual do caso, derivado só de ARTEFATOS (nunca de flag mutável)."""
    return derivar_estado(await coletar_artefatos(db, case_id, case=case))


# ── Ações — whitelist (executáveis) e atos jurídicos (sempre humanos) ────────

def _acao(nome: str, endpoint: str, payload: dict | None = None,
          metodo: str = "POST", via_orquestrador: bool = True) -> dict:
    return {"acao": nome, "metodo": metodo, "endpoint": endpoint,
            "payload_esperado": payload or {},
            "executavel_via_orquestrador": via_orquestrador}


# Atos jurídicos: `avancar` NUNCA executa — devolve a instrução do endpoint
# de aprovação humana próprio (HITL, OAB Prov. 205/2021).
ACOES_APROVACAO_HUMANA: dict[str, dict] = {
    "aprovar_snapshot": {
        "endpoint": "POST /cases/{case_id}/inteligencia/{snapshot_id}/aprovar",
        "instrucao": ("Aprovação do snapshot de inteligência é ato humano do "
                      "advogado — use o endpoint próprio."),
    },
    "aprovar_tese": {
        "endpoint": "POST /cases/{case_id}/matriz-teses/teses/{tese_id}/aprovar",
        "instrucao": ("Aprovação de tese (estratégia) é ato humano do advogado "
                      "— use o endpoint próprio."),
    },
    "aprovar_estrategia": {
        "endpoint": "POST /cases/{case_id}/matriz-teses/teses/{tese_id}/aprovar",
        "instrucao": ("Aprovação da estratégia é ato humano do advogado — "
                      "aprove as teses da matriz no endpoint próprio."),
    },
    "aprovar_proposta": {
        "endpoint": "POST /honorarios-oab/propostas/{proposta_id}/aprovar",
        "instrucao": ("Aprovação de proposta de honorários é ato humano do "
                      "advogado — use o endpoint próprio."),
    },
    "aprovar_peca": {
        "endpoint": "PATCH /legal-docs/{doc_id}/aprovar",
        "instrucao": ("Aprovação de peça é ato humano do advogado (HITL) — "
                      "use o endpoint próprio após revisar o conteúdo."),
    },
    "confirmar_termo_inicial": {
        "endpoint": ("POST /cases/{case_id}/motor-peca/gerar "
                     "(termo_inicial_confirmado=true no corpo)"),
        "instrucao": ("Confirmar o termo inicial é ato humano do advogado — "
                      "envie-o explicitamente no fluxo do Motor de Peça "
                      "(ou na ação 'gerar_peca', que preserva TODOS os gates)."),
    },
}


# Executores: cada um REUSA o handler/service existente (gates de role,
# ownership, LGPD, HITL e citações intactos). Assinatura: (db, case, user,
# params) → resultado do fluxo original.

async def _exec_analisar_caso(db, case, user, params: dict):
    from app.routers.intake import AnaliseCompletaIn, analise_completa
    return await analise_completa(case.id, AnaliseCompletaIn(**params), db, user)


async def _exec_analisar_peca(db, case, user, params: dict):
    from app.routers.motor_peca import AnalisarIn, analisar
    return await analisar(case.id, AnalisarIn(**params), db, user)


async def _exec_montar_matriz(db, case, user, params: dict):
    from app.routers.matriz_teses import MontarMatrizIn, montar
    return await montar(case.id, MontarMatrizIn(**params) if params else None,
                        db, user)


async def _exec_sugerir_proposta(db, case, user, params: dict):
    from app.services.fee_proposal_service import sugerir_proposta
    area = params.get("area") or _enum_val(case.area) or ""
    return await sugerir_proposta(db, case, area,
                                  item_codigo=params.get("item_codigo"))


async def _exec_criar_proposta(db, case, user, params: dict):
    from app.routers.honorarios_oab import PropostaIn, criar_proposta_honorarios
    return await criar_proposta_honorarios(case.id, PropostaIn(**params), db, user)


async def _exec_gerar_kit(db, case, user, params: dict):
    from app.routers.kit_documental import KitDocumentalIn, gerar_kit_documental
    return await gerar_kit_documental(case.id, KitDocumentalIn(**params), db, user)


async def _exec_gerar_peca(db, case, user, params: dict):
    # Reusa o handler /motor-peca/gerar INTEIRO: confirmar_e_criar_prazo (gates
    # invioláveis — checklist bloqueante; termo confirmado PELO ADVOGADO no
    # próprio body) + redação pela esteira existente (HITL + gate de citações).
    from app.routers.motor_peca import GerarIn, gerar
    return await gerar(case.id, GerarIn(**params), db, user)


ACOES_EXECUTAVEIS: dict[str, Callable[..., Awaitable[Any]]] = {
    "analisar_caso": _exec_analisar_caso,       # intake análise-completa
    "analisar_peca": _exec_analisar_peca,       # motor-peca /analisar
    "montar_matriz": _exec_montar_matriz,       # matriz de teses (rascunho)
    "sugerir_proposta": _exec_sugerir_proposta, # sugestão determinística (não persiste)
    "criar_proposta": _exec_criar_proposta,     # rascunho de proposta (não aprova)
    "gerar_kit": _exec_gerar_kit,               # kit documental (rascunhos)
    "gerar_peca": _exec_gerar_peca,             # motor-peca /gerar (gates intactos)
}

ACOES_VALIDAS: tuple[str, ...] = tuple(
    sorted(set(ACOES_EXECUTAVEIS) | set(ACOES_APROVACAO_HUMANA)))

# Rate limit do FLUXO ORIGINAL consumido também quando a ação roda VIA
# orquestrador (auditoria: o /avancar não pode ser bypass do limite da rota
# própria). Nome e limite ESPELHAM as dependencies dos routers de origem.
_RATE_LIMIT_ACAO: dict[str, tuple[str, int]] = {
    "analisar_caso": ("intake-analise-completa", 10),
    "analisar_peca": ("motor-peca-analisar", 10),
    "montar_matriz": ("matriz-teses-montar", 5),
    "sugerir_proposta": ("proposta-honorarios", 15),
    "criar_proposta": ("proposta-honorarios", 15),
    "gerar_kit": ("kit-documental", 5),
    "gerar_peca": ("motor-peca-gerar", 3),
}


# ── Próximo passo (determinístico, sem LLM) ──────────────────────────────────

def _proximo_do_estado(estado: str, art: dict, case_id: str) -> tuple[str, list[dict], list[dict]]:
    """(passo recomendado, ações disponíveis, pendências bloqueantes) por
    estado — 100% determinístico sobre os artefatos."""
    ep = f"/cases/{case_id}"
    acoes: list[dict] = []
    pend: list[dict] = []

    if estado == "entrada":
        passo = "Ler os documentos do caso e produzir a primeira análise (intake)."
        if not art["tem_base_fatica"]:
            pend.append({"tipo": "base_fatica",
                         "detalhe": ("Sem documentos com OCR nem descrição dos "
                                     "fatos — anexe documentos ou preencha a "
                                     "descrição antes da análise.")})
        acoes.append(_acao("analisar_caso",
                           f"/intake/casos/{case_id}/analise-completa",
                           {"texto": "opcional (string)"}))
    elif estado == "compreensao":
        passo = ("Revisar e aprovar o snapshot de inteligência (fixa área/rito) "
                 "— ato humano do advogado.")
        pend.append({"tipo": "aprovacao_humana",
                     "detalhe": "Snapshot de inteligência ainda não aprovado.",
                     "endpoint": f"{ep}/inteligencia/{{snapshot_id}}/aprovar"})
        acoes.append(_acao("aprovar_snapshot",
                           f"{ep}/inteligencia/{{snapshot_id}}/aprovar",
                           via_orquestrador=False))
        acoes.append(_acao("analisar_caso",
                           f"/intake/casos/{case_id}/analise-completa",
                           {"texto": "opcional (string)"}))
    elif estado == "classificacao":
        passo = ("Validar o caminho processual: peças cabíveis, prazo projetado "
                 "e checklist (Motor de Peça).")
        acoes.append(_acao("analisar_peca", f"{ep}/motor-peca/analisar",
                           {"peca_codigo": "opcional", "termo_inicial": "opcional",
                            "evento": "opcional", "data_evento": "opcional"}))
    elif estado == "validacao_processual":
        passo = "Montar a matriz de teses (pesquisa por questões decompostas)."
        acoes.append(_acao("montar_matriz", f"{ep}/matriz-teses/montar",
                           {"area": "opcional", "fatos": "opcional"}))
    elif estado == "estrategia":
        passo = ("Definir a estratégia (aprovar teses da matriz — ato humano) e "
                 "encaminhar a contratação (proposta + kit).")
        if not art["tese_aprovada"]:
            pend.append({"tipo": "aprovacao_humana",
                         "detalhe": "Nenhuma tese da matriz aprovada pelo advogado.",
                         "endpoint": f"{ep}/matriz-teses/teses/{{tese_id}}/aprovar"})
        if not art["proposta_aprovada"]:
            if not art["proposta_existe"]:
                acoes.append(_acao("sugerir_proposta",
                                   f"/honorarios-oab/casos/{case_id}/proposta/sugerir"))
                acoes.append(_acao("criar_proposta",
                                   f"/honorarios-oab/casos/{case_id}/proposta",
                                   {"faixas": "faixas definidas pelo advogado"}))
            pend.append({"tipo": "aprovacao_humana",
                         "detalhe": "Proposta de honorários sem aprovação vigente.",
                         "endpoint": "/honorarios-oab/propostas/{proposta_id}/aprovar"})
        if not art["kit_gerado"]:
            acoes.append(_acao("gerar_kit", f"{ep}/kit-documental",
                               {"tipo_poderes": "ad_judicia (default)"}))
    elif estado == "contratacao":
        passo = ("Produzir a peça: confirmar o termo inicial (ato humano) e "
                 "gerar pelo Motor de Peça — os gates criam o prazo.")
        checklist = art.get("checklist_motor") or {}
        if checklist and not checklist.get("pronto"):
            pendentes = [i for i in (checklist.get("itens") or [])
                         if not i.get("ok")]
            pend.append({"tipo": "checklist",
                         "detalhe": "Checklist bloqueante da peça com itens pendentes.",
                         "itens": pendentes})
        pend.append({"tipo": "aprovacao_humana",
                     "detalhe": ("Termo inicial do prazo exige confirmação "
                                 "explícita do advogado (termo_inicial_confirmado=true)."),
                     "endpoint": f"{ep}/motor-peca/gerar"})
        acoes.append(_acao("analisar_peca", f"{ep}/motor-peca/analisar",
                           {"peca_codigo": "opcional"}))
        acoes.append(_acao("gerar_peca", f"{ep}/motor-peca/gerar",
                           {"peca_codigo": "obrigatório",
                            "termo_inicial": "data (ou evento+data_evento)",
                            "termo_inicial_confirmado": "true (confirmação humana)"}))
    elif estado == "producao":
        passo = "Revisar a peça em rascunho (HITL — revisão humana obrigatória)."
        pend.append({"tipo": "aprovacao_humana",
                     "detalhe": "Peça em rascunho aguardando revisão do advogado.",
                     "endpoint": "/legal-docs/{doc_id}/revisar"})
        acoes.append(_acao("aprovar_peca", "/legal-docs/{doc_id}/aprovar",
                           metodo="PATCH", via_orquestrador=False))
    elif estado == "revisao":
        passo = ("Concluir a revisão: aprovar a peça (ato humano) e garantir o "
                 "prazo confirmado antes do protocolo.")
        if not art["peca_aprovada"]:
            pend.append({"tipo": "aprovacao_humana",
                         "detalhe": "Peça ainda não aprovada pelo advogado.",
                         "endpoint": "/legal-docs/{doc_id}/aprovar"})
        if not art["deadline_confirmado"]:
            pend.append({"tipo": "prazo",
                         "detalhe": ("Nenhum prazo confirmado no caso — confirme "
                                     "o termo inicial pelo Motor de Peça."),
                         "endpoint": f"{ep}/motor-peca/gerar"})
        acoes.append(_acao("aprovar_peca", "/legal-docs/{doc_id}/aprovar",
                           metodo="PATCH", via_orquestrador=False))
    elif estado == "protocolo":
        passo = ("Protocolar a peça no tribunal (ato externo) e registrar o "
                 "comprovante na peça.")
        pend.append({"tipo": "ato_externo",
                     "detalhe": ("Peticionamento é manual (PJe/eproc); registre "
                                 "número/data/tribunal do protocolo na peça."),
                     "endpoint": "/legal-docs/{doc_id}/protocolo"})
        acoes.append(_acao("registrar_protocolo", "/legal-docs/{doc_id}/protocolo",
                           metodo="PATCH", via_orquestrador=False))
    else:  # acompanhamento
        passo = ("Acompanhar andamentos/intimações; novos eventos reabrem o "
                 "ciclo pelo Motor de Peça.")
        acoes.append(_acao("analisar_peca", f"{ep}/motor-peca/analisar",
                           {"evento": "opcional", "data_evento": "opcional"}))
    return passo, acoes, pend


async def proximo_passo(db, case_id: str, case: Case | None = None,
                        art: dict | None = None) -> dict:
    """Passo recomendado + ações disponíveis + pendências bloqueantes.
    Determinístico, sem LLM — só artefatos e a tabela de estados."""
    art = art or await coletar_artefatos(db, case_id, case=case)
    estado = derivar_estado(art)
    passo, acoes, pendencias = _proximo_do_estado(estado, art, case_id)
    return {
        "estado": estado,
        "estado_rotulo": ROTULOS_ESTADO[estado],
        "passo_recomendado": passo,
        "acoes_disponiveis": acoes,
        "pendencias_bloqueantes": pendencias,
    }


# ── Jornada resumida p/ UI (§16 do plano) ────────────────────────────────────

def montar_jornada(art: dict) -> list[dict]:
    """Lista ORDENADA de etapas {etapa, rotulo, status} derivada dos artefatos.

    status: concluida | em_andamento | pendente | bloqueada.
    A primeira etapa não concluída vira "bloqueada" quando depende de aprovação
    humana/checklist, senão "em_andamento"; as seguintes ficam "pendente".
    """
    checklist = art.get("checklist_motor") or {}
    etapas: list[tuple[str, str, bool, bool]] = [
        # (chave, rótulo humano, concluída?, bloqueio humano/checklist?)
        ("documentos_lidos", "Documentos lidos", art["tem_base_fatica"], False),
        ("area_sugerida", "Área sugerida", bool(art["area_sugerida"]) or art["tem_snapshot"], False),
        ("area_confirmada", "Área confirmada pelo advogado",
         art["tem_snapshot_congelado"], True),
        ("prazo_calculado", "Prazo calculado", art["tem_snapshot_motor"], False),
        ("checklist_criado", "Checklist criado",
         bool(checklist) or art["tem_checklist_doc"], False),
        ("teses_pesquisadas", "Teses pesquisadas", art["matriz_montada"], False),
        ("estrategia_aprovada", "Estratégia aprovada pelo advogado",
         art["tese_aprovada"], True),
        ("honorarios_sugeridos", "Honorários sugeridos", art["proposta_existe"], False),
        ("honorarios_aprovados", "Honorários aprovados pelo advogado",
         art["proposta_aprovada"], True),
        ("procuracao_gerada", "Procuração gerada", art["tem_procuracao"], False),
        ("contrato_gerado", "Contrato gerado", art["tem_contrato"], False),
        ("prazo_confirmado", "Prazo confirmado pelo advogado",
         art["deadline_confirmado"], True),
        ("peca_redigida", "Peça redigida",
         art["peca_rascunho"] or art["peca_em_revisao"] or art["peca_aprovada"]
         or art["peca_protocolada"], False),
        # CR-15: concluída SÓ com validação jurídica registrada da peça (gate
        # de citações executado) — antes bastava a peça ser ai_generated.
        ("citacoes_verificadas", "Citações verificadas", art["peca_validada"], False),
        ("aprovacao_peca", "Aguardando aprovação do advogado",
         art["peca_aprovada"] or art["peca_protocolada"], True),
        ("peca_protocolada", "Peça protocolada", art["peca_protocolada"], False),
    ]
    jornada: list[dict] = []
    atual_marcada = False
    for chave, rotulo, concluida, exige_humano in etapas:
        if concluida:
            status = "concluida"
        elif not atual_marcada:
            status = "bloqueada" if exige_humano else "em_andamento"
            atual_marcada = True
        else:
            status = "pendente"
        jornada.append({"etapa": chave, "rotulo": rotulo, "status": status})
    return jornada


# ── Linha do tempo de estados (a partir dos snapshots) ───────────────────────

_ORIGEM_ESTADO = {
    "triagem": "compreensao",
    "intake": "compreensao",
    "raio_x": "compreensao",
    "manual": "compreensao",
    "motor_peca": "validacao_processual",
    "matriz_teses": "estrategia",
}


def linha_do_tempo(snapshots: list) -> list[dict]:
    """Linha do tempo (mais antigo primeiro) derivada dos snapshots do caso.
    Snapshots origem="orquestrador" carregam o estado registrado na transição;
    os demais são mapeados pela origem (tabela _ORIGEM_ESTADO)."""
    eventos = []
    for s in sorted(snapshots, key=lambda x: x.versao):
        payload = s.payload or {}
        estado = (payload.get("estado_orquestrador")
                  if s.origem == "orquestrador"
                  else _ORIGEM_ESTADO.get(s.origem))
        eventos.append({
            "versao": s.versao,
            "origem": s.origem,
            "estado": estado,
            "resumo": s.resumo,
            "congelado": bool(s.congelado),
            "criado_em": s.criado_em.isoformat() if s.criado_em else None,
        })
    return eventos


# ── avancar — executa UMA transição sobre os services existentes ─────────────

async def avancar(db, case_id: str, user: User, acao: str,
                  params: dict | None = None, case: Case | None = None) -> dict:
    """Executa UMA transição chamando o service/handler já existente.

    • Ação fora da whitelist → HTTPException 422 (o router propaga).
    • Ato jurídico (ACOES_APROVACAO_HUMANA) → NUNCA executa; devolve a
      instrução do endpoint de aprovação humana próprio.
    • Ação executável → roda o fluxo original (todos os gates intactos),
      audita a transição (criar_audit_log) e registra snapshot
      origem="orquestrador" (fail-safe — falha não corrompe nada, pois o
      estado é derivado de artefatos).
    """
    _req_advogado(user)
    params = dict(params or {})

    if acao not in ACOES_VALIDAS:
        raise HTTPException(status_code=422, detail={
            "mensagem": f"Ação desconhecida pelo orquestrador: {acao!r}",
            "acoes_validas": list(ACOES_VALIDAS),
        })

    if acao in ACOES_APROVACAO_HUMANA:
        info = ACOES_APROVACAO_HUMANA[acao]
        return {
            "executado": False,
            "requer_aprovacao_humana": True,
            "acao": acao,
            "instrucao": info["instrucao"],
            "endpoint_humano": info["endpoint"],
        }

    # Anti-bypass do rate limit: consome a cota do FLUXO ORIGINAL (mesma chave
    # user:{id} das dependencies dos routers) — 429 propaga ao chamador.
    rl = _RATE_LIMIT_ACAO.get(acao)
    if rl is not None:
        await consumir(rl[0], f"user:{user.id}", rl[1])

    if case is None:
        case = (await db.execute(
            select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
        )).scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    # Estado ANTES (best-effort — falha de derivação nunca impede a ação).
    estado_antes = None
    try:
        estado_antes = await estado_atual(db, case_id, case=case)
    except Exception as e:  # noqa: BLE001 — fail-safe por contrato
        logger.warning("[orquestrador] estado_antes indisponível (%s): %s",
                       case_id, str(e)[:150])

    try:
        resultado = await ACOES_EXECUTAVEIS[acao](db, case, user, params)
    except ValidationError as e:
        # Params fora do schema do fluxo original NUNCA viram 500 — devolve
        # 422 estruturado com campo/erro (contrato do endpoint /avancar).
        raise HTTPException(status_code=422, detail={
            "mensagem": f"Parâmetros inválidos para a ação '{acao}'",
            "erros": [{"campo": ".".join(str(p) for p in err.get("loc", ())),
                       "erro": err.get("msg", "inválido")}
                      for err in e.errors()],
        })

    # Estado DEPOIS (best-effort) + auditoria + linha do tempo (fail-safe).
    estado_depois = None
    try:
        estado_depois = await estado_atual(db, case_id, case=case)
    except Exception as e:  # noqa: BLE001
        logger.warning("[orquestrador] estado_depois indisponível (%s): %s",
                       case_id, str(e)[:150])

    await criar_audit_log(
        db, user.id, _role_str(user), "ORQUESTRADOR_AVANCAR", "cases", case_id,
        detalhes=(f"Orquestrador: acao={acao} "
                  f"estado_antes={estado_antes or '?'} "
                  f"estado_depois={estado_depois or '?'}"),
    )
    await db.commit()

    try:
        from app.services.case_intelligence_service import gravar_snapshot_seguro
        await gravar_snapshot_seguro(
            db, case_id=case_id, origem="orquestrador",
            payload={
                "estado_orquestrador": estado_depois or estado_antes or "desconhecido",
                "estado_anterior": estado_antes,
                "acao": acao,
            },
            resumo=(f"Orquestrador — transição '{acao}' "
                    f"({estado_antes or '?'} → {estado_depois or '?'})"),
            criado_por=user.id,
        )
    except Exception as e:  # noqa: BLE001 — linha do tempo nunca quebra o fluxo
        logger.warning("[orquestrador] snapshot de transição não gravado "
                       "(%s): %s", case_id, str(e)[:150])

    return {
        "executado": True,
        "acao": acao,
        "estado_anterior": estado_antes,
        "estado": estado_depois,
        "resultado": resultado,
    }


# ── Visão consolidada p/ o GET do router ─────────────────────────────────────

async def visao_orquestrador(db, case_id: str, case: Case | None = None) -> dict:
    """Estado + próximo passo + pendências + jornada + linha do tempo — tudo
    derivado dos artefatos reais numa única coleta."""
    art = await coletar_artefatos(db, case_id, case=case)
    prox = await proximo_passo(db, case_id, case=case, art=art)
    return {
        "case_id": case_id,
        "estado": prox["estado"],
        "estado_rotulo": prox["estado_rotulo"],
        "estados": list(ESTADOS),
        "proximo_passo": prox,
        "jornada": montar_jornada(art),
        "linha_do_tempo": linha_do_tempo(art["snapshots"]),
    }
