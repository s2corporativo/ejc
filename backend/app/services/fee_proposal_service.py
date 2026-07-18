# ── app/services/fee_proposal_service.py ─────────────────────────────────────
# FASE 4 — Proposta de Honorários DETERMINÍSTICA + aprovação HITL imutável.
#
# Motor de sugestão (sugerir_proposta): parte do item VIGENTE da tabela OAB/MG
# estruturada (reusa geracao_documental._itens_oab_vigentes / _item_dict):
#   • minimo_etico  = valor mínimo do item, VERBATIM. Sem item aplicável (ou
#     item só-percentual, sem base monetária) → None + aviso explícito
#     "sem base OAB — não preencher automaticamente". NUNCA inventado.
#   • recomendado / estrategico = APENAS quando há mínimo, por multiplicadores
#     FIXOS documentados abaixo × fator de complexidade do caso (campo
#     `complexidade` do Case quando existir; senão 1.0), com memória de
#     cálculo explícita. NADA de LLM definindo valor.
#
# Ciclo de vida (models/fee_proposal.py — STATUS_PROPOSTA):
#   rascunho → aprovada | rejeitada;  aprovada → substituida (só via aprovação
#   de NOVA versão do mesmo caso). Proposta APROVADA é IMUTÁVEL: qualquer
#   mudança = criar_proposta (versao = max+1). Aprovar/rejeitar são atos
#   humanos de advogado+ com AuditLog obrigatório; o commit é feito aqui.
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.security import ROLE_LEVEL
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.fee_proposal import FeeProposal
from app.models.user import User
from app.services.geracao_documental import _item_dict, _itens_oab_vigentes

# ── Multiplicadores FIXOS e documentados (determinísticos — nunca LLM) ────────
# recomendado  = mínimo OAB × 1.5 × fator de complexidade
# estrategico  = mínimo OAB × 2.0 × fator de complexidade
_FATOR_RECOMENDADO = 1.5
_FATOR_ESTRATEGICO = 2.0
# Fator por complexidade do caso (Case.complexidade, quando o campo existir e
# tiver valor reconhecido; caso contrário 1.0 — nunca presumir complexidade).
_FATOR_COMPLEXIDADE = {"baixa": 1.0, "media": 1.25, "alta": 1.5}

AVISO_SEM_BASE_OAB = (
    "sem base OAB — não preencher automaticamente: nenhum item aplicável da "
    "Tabela OAB/MG vigente para a área do caso. Nunca inventamos valores — "
    "consulte a tabela oficial OAB/MG ou cadastre o item (fonte obrigatória)."
)

AVISO_ITEM_SEM_VALOR = (
    "sem base OAB — não preencher automaticamente: o item vigente da Tabela "
    "OAB/MG não traz valor monetário mínimo (item só-percentual/URH). O "
    "advogado define o valor manualmente."
)

AVISO_SUGESTAO = (
    "Sugestão DETERMINÍSTICA de referência (tabela OAB/MG + multiplicadores "
    "fixos) — não vinculante; o advogado define e aprova o valor final."
)


def _fator_complexidade(case: Case) -> tuple[float, str | None]:
    """Fator fixo pela complexidade do caso; campo ausente/desconhecido → 1.0."""
    c = getattr(case, "complexidade", None)
    c = getattr(c, "value", c)
    c = str(c).strip().lower() if c else ""
    if c in _FATOR_COMPLEXIDADE:
        return _FATOR_COMPLEXIDADE[c], c
    return 1.0, None


def _faixa(valor: float | None, memoria: str) -> dict:
    return {"valor": round(valor, 2) if valor is not None else None,
            "memoria_calculo": memoria}


async def sugerir_proposta(db, case: Case, area: str) -> dict:
    """Sugestão determinística de faixas de honorários (NÃO persiste nada).

    Sem item OAB vigente → mínimo None + aviso "sem base OAB — não preencher
    automaticamente"; recomendado/estratégico só existem quando há mínimo.
    """
    itens = await _itens_oab_vigentes(db, area, date.today())
    item = itens[0] if itens else None

    if item is None:
        return {
            "origem_tabela": None,
            "faixas": {
                "minimo_etico": _faixa(None, AVISO_SEM_BASE_OAB),
                "recomendado": _faixa(None, AVISO_SEM_BASE_OAB),
                "estrategico": _faixa(None, AVISO_SEM_BASE_OAB),
            },
            "aviso": AVISO_SEM_BASE_OAB,
        }

    origem = _item_dict(item)
    if item.valor_minimo is None:
        # Item existe, mas sem base monetária: NADA é calculado automaticamente.
        return {
            "origem_tabela": origem,
            "faixas": {
                "minimo_etico": _faixa(None, AVISO_ITEM_SEM_VALOR),
                "recomendado": _faixa(None, AVISO_ITEM_SEM_VALOR),
                "estrategico": _faixa(None, AVISO_ITEM_SEM_VALOR),
            },
            "aviso": AVISO_ITEM_SEM_VALOR,
        }

    minimo = float(item.valor_minimo)
    fator, rotulo = _fator_complexidade(case)
    complex_txt = (f"complexidade '{rotulo}'" if rotulo
                   else "complexidade nao informada (fator 1.0)")
    mem_min = (f"Valor minimo VERBATIM do item {item.item_codigo} da Tabela "
               f"OAB/MG ({item.descricao}); fonte: {item.fonte}")
    mem_rec = (f"minimo OAB R$ {minimo:,.2f} x fator recomendado "
               f"{_FATOR_RECOMENDADO:g} x fator {fator:g} ({complex_txt}) "
               f"= R$ {minimo * _FATOR_RECOMENDADO * fator:,.2f}")
    mem_est = (f"minimo OAB R$ {minimo:,.2f} x fator estrategico "
               f"{_FATOR_ESTRATEGICO:g} x fator {fator:g} ({complex_txt}) "
               f"= R$ {minimo * _FATOR_ESTRATEGICO * fator:,.2f}")
    return {
        "origem_tabela": origem,
        "faixas": {
            "minimo_etico": _faixa(minimo, mem_min),
            "recomendado": _faixa(minimo * _FATOR_RECOMENDADO * fator, mem_rec),
            "estrategico": _faixa(minimo * _FATOR_ESTRATEGICO * fator, mem_est),
        },
        "aviso": AVISO_SUGESTAO,
    }


# ── CRUD/ciclo de vida ───────────────────────────────────────────────────────

def _role_str(cu: User) -> str:
    r = getattr(cu, "role", None)
    return r.value if hasattr(r, "value") else str(r)


def _req_advogado_service(cu: User) -> None:
    # Defesa em profundidade: aprovação/rejeição é ato jurídico de advogado+
    # mesmo se algum chamador futuro esquecer o gate do router.
    if ROLE_LEVEL.get(_role_str(cu), 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(status_code=403, detail="Acesso restrito a advogados")


def proposta_out(p: FeeProposal) -> dict:
    return {
        "id": p.id,
        "case_id": p.case_id,
        "versao": p.versao,
        "status": p.status,
        "origem_tabela": p.origem_tabela,
        "faixas": p.faixas or {},
        "exito_percentual": float(p.exito_percentual) if p.exito_percentual is not None else None,
        "parcelamento": p.parcelamento,
        "despesas_criterio": p.despesas_criterio,
        "justificativa": p.justificativa,
        "criado_por": p.criado_por,
        "criado_em": p.criado_em.isoformat() if p.criado_em else None,
        "aprovado_por": p.aprovado_por,
        "aprovado_em": p.aprovado_em.isoformat() if p.aprovado_em else None,
    }


async def obter_proposta(db, proposta_id: str) -> FeeProposal:
    p = (await db.execute(
        select(FeeProposal).where(FeeProposal.id == proposta_id)
    )).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Proposta não encontrada")
    return p


async def criar_proposta(db, case_id: str, user: User, dados: dict) -> FeeProposal:
    """Cria RASCUNHO com versao = max+1 do caso (versionamento estrito).

    `dados` já validado no router (faixas/origem_tabela/exito/parcelamento/
    despesas/justificativa). Auditoria + commit aqui.
    """
    _req_advogado_service(user)
    ultima = (await db.execute(
        select(func.max(FeeProposal.versao)).where(FeeProposal.case_id == case_id)
    )).scalar()
    p = FeeProposal(
        id=str(uuid4()),
        case_id=case_id,
        versao=int(ultima or 0) + 1,
        status="rascunho",
        origem_tabela=dados.get("origem_tabela"),
        faixas=dados.get("faixas") or {},
        exito_percentual=dados.get("exito_percentual"),
        parcelamento=dados.get("parcelamento"),
        despesas_criterio=dados.get("despesas_criterio"),
        justificativa=dados.get("justificativa"),
        criado_por=user.id,
        criado_em=datetime.now(timezone.utc),
    )
    db.add(p)
    await criar_audit_log(
        db, user.id, _role_str(user), "CREATE", "fee_proposals", p.id,
        detalhes=f"Proposta de honorarios v{p.versao} (rascunho) do caso {case_id}",
        dados_depois=proposta_out(p),
    )
    await db.commit()
    return p


async def aprovar(db, proposta_id: str, user: User) -> FeeProposal:
    """Aprova (HITL, advogado+) e CONGELA a proposta.

    Só rascunho pode ser aprovado — aprovada/rejeitada/substituida são
    imutáveis (mudança = nova versão). Aprovadas anteriores do MESMO caso
    viram "substituida" (no máximo uma aprovada vigente por caso).
    """
    _req_advogado_service(user)
    p = await obter_proposta(db, proposta_id)
    if p.status != "rascunho":
        raise HTTPException(
            status_code=409,
            detail=(f"Proposta com status '{p.status}' é imutável — "
                    "crie uma nova versão (rascunho) para alterar."),
        )
    antes = proposta_out(p)

    anteriores = (await db.execute(
        select(FeeProposal).where(
            FeeProposal.case_id == p.case_id,
            FeeProposal.status == "aprovada",
            FeeProposal.id != p.id,
        )
    )).scalars().all()
    for a in anteriores:
        a.status = "substituida"

    p.status = "aprovada"
    p.aprovado_por = user.id
    p.aprovado_em = datetime.now(timezone.utc)
    await criar_audit_log(
        db, user.id, _role_str(user), "APROVAR", "fee_proposals", p.id,
        detalhes=(f"Proposta v{p.versao} do caso {p.case_id} aprovada (congelada)"
                  + (f"; substituidas: {', '.join(a.id for a in anteriores)}"
                     if anteriores else "")),
        dados_antes=antes, dados_depois=proposta_out(p),
    )
    await db.commit()
    return p


async def rejeitar(db, proposta_id: str, user: User, motivo: str | None = None) -> FeeProposal:
    """Rejeita um RASCUNHO (HITL, advogado+). Demais status são imutáveis."""
    _req_advogado_service(user)
    p = await obter_proposta(db, proposta_id)
    if p.status != "rascunho":
        raise HTTPException(
            status_code=409,
            detail=(f"Proposta com status '{p.status}' é imutável — "
                    "apenas rascunhos podem ser rejeitados."),
        )
    antes = proposta_out(p)
    p.status = "rejeitada"
    await criar_audit_log(
        db, user.id, _role_str(user), "REJEITAR", "fee_proposals", p.id,
        detalhes=(f"Proposta v{p.versao} do caso {p.case_id} rejeitada"
                  + (f" — motivo: {motivo}" if motivo else "")),
        dados_antes=antes, dados_depois=proposta_out(p),
    )
    await db.commit()
    return p


async def proposta_aprovada_vigente(db, case_id: str) -> FeeProposal | None:
    """Proposta APROVADA vigente do caso (a de maior versão) — ou None."""
    return (await db.execute(
        select(FeeProposal)
        .where(FeeProposal.case_id == case_id, FeeProposal.status == "aprovada")
        .order_by(FeeProposal.versao.desc())
        .limit(1)
    )).scalar_one_or_none()


# ── Ponte proposta → contrato (documental._contrato_honorarios) ──────────────

def _forma_pagamento(parcelamento: dict | None) -> str:
    """Descrição determinística da forma de pagamento a partir do parcelamento
    estruturado da proposta. Sem parcelamento → padrão do escritório (à vista)."""
    if not parcelamento:
        return "a vista, na assinatura deste contrato"
    if parcelamento.get("descricao"):
        return str(parcelamento["descricao"])
    partes = []
    if parcelamento.get("entrada") is not None:
        partes.append(f"entrada de R$ {float(parcelamento['entrada']):,.2f}")
    n = parcelamento.get("num_parcelas")
    vp = parcelamento.get("valor_parcela")
    if n and vp is not None:
        partes.append(f"{int(n)} parcelas mensais de R$ {float(vp):,.2f}")
    elif n:
        partes.append(f"{int(n)} parcelas mensais")
    return " + ".join(partes) if partes else "a vista, na assinatura deste contrato"


def proposta_para_contrato(p: FeeProposal) -> dict:
    """Parâmetros do contrato a partir de proposta APROVADA (só template).

    Valor contratado = faixa "recomendado" da proposta aprovada (fallback:
    "minimo_etico"). Sem valor em nenhuma faixa → None (o contrato mantém o
    placeholder R$ [____] — nunca inventar valor).
    """
    if p.status != "aprovada":
        raise HTTPException(
            status_code=409,
            detail="Contrato só recebe valores de proposta APROVADA.",
        )
    faixas = p.faixas or {}

    def _valor(k: str):
        v = (faixas.get(k) or {}).get("valor")
        return float(v) if v is not None else None

    valor = _valor("recomendado")
    if valor is None:
        valor = _valor("minimo_etico")
    return {
        "versao": p.versao,
        "valor": valor,
        "forma_pagamento": _forma_pagamento(p.parcelamento),
        "exito_percentual": float(p.exito_percentual) if p.exito_percentual is not None else None,
        "despesas_criterio": (p.despesas_criterio or "").strip() or None,
    }
