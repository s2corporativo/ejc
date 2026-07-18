# ── app/routers/motor_peca.py ────────────────────────────────────────────────
# Motor de Peça (P1) — orquestrador único documento→peça.
#
# POST /cases/{case_id}/motor-peca/analisar → rascunho consolidado:
#   1) diagnóstico (área provável + teses do banco — reuso de intake.py)
#   2) peça(s) cabível(is) (rito_engine + mapa determinístico peça→base legal→
#      prazo; IA APENAS para motivação textual, com sanitizar_pii + AILog)
#   3) prazo PROJETADO via deadline_calculator — termo inicial informado ou
#      "pendente de confirmação humana"; termo_inicial_confirmado=false SEMPRE.
#      NUNCA cria Deadline nesta etapa.
#   4) checklist bloqueante da peça proposta (padrão conversao_caso.py).
#
# POST /cases/{case_id}/motor-peca/gerar → confirma e executa:
#   • 422 se checklist não pronto OU termo inicial não confirmado (mesmo padrão
#     422 de conversao_caso.py).
#   • Cria o Deadline (padrão raio_x_service) SÓ após confirmação humana.
#   • Dispara a redação pelo fluxo EXISTENTE: ia_defensiva_service (contestação)
#     ou peca_service.gerar_peca_pipeline (demais) — gate de citações e HITL
#     preservados. Tudo nasce RASCUNHO.
#
# Gates: verificar_acesso_caso em todos os endpoints; advogado+ (mesmo limiar
# de intake.py); rate limit por rota (gerar mais restrito).
from __future__ import annotations

import logging
from datetime import date
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.audit_log import criar_audit_log
from app.models.deadline import (
    Deadline,
    DeadlinePrioridade,
    DeadlineStatus,
    DeadlineTipo,
)
from app.models.user import User
from app.routers import intake as intake_router
from app.services import motor_peca_service as mps
from app.services.ia_defensiva_service import IaDefensivaInput, executar_ia_defensiva
from app.services.sanitizer import sanitizar_pii

logger = logging.getLogger("ejc.motor_peca")

router = APIRouter(prefix="/cases/{case_id}/motor-peca", tags=["Motor de Peça"])


def _pode_usar(cu: User) -> bool:
    """Mesmo limiar de intake.py: advogado+."""
    role = getattr(cu.role, "value", cu.role)
    return ROLE_LEVEL.get(role, 0) >= ROLE_LEVEL["advogado"]


def _enum_val(v) -> str | None:
    return getattr(v, "value", v) if v is not None else None


# ── Schemas ───────────────────────────────────────────────────────────────────

class AnalisarIn(BaseModel):
    """Sinais opcionais além do que o caso já contém."""
    texto: Optional[str] = Field(None, max_length=30000)
    tipo_documento: Optional[str] = Field(None, max_length=200)
    fase: Optional[str] = Field(None, max_length=100)
    # Termo inicial INFORMADO pelo advogado (nunca presumido). Mesmo informado,
    # o prazo permanece PROJETADO até a confirmação explícita no /gerar.
    termo_inicial: Optional[date] = None
    peca_codigo: Optional[str] = Field(None, max_length=64)
    em_dobro: bool = Field(False, description="Prazo em dobro (CPC arts. 180/183/186)")
    incluir_motivacao_ia: bool = True


class GerarIn(BaseModel):
    """Resultado CONFIRMADO pelo advogado (HITL)."""
    peca_codigo: str = Field(..., max_length=64)
    rito_codigo: Optional[str] = Field(None, max_length=64)
    termo_inicial: Optional[date] = None
    termo_inicial_confirmado: bool = False
    # Obrigatória quando o prazo da peça é contagem="verificar".
    data_prazo_manual: Optional[date] = None
    em_dobro: bool = False
    descricao_fatos: Optional[str] = Field(None, max_length=10000)
    pedidos: Optional[str] = Field(None, max_length=3000)
    area_direito: Optional[str] = Field(None, max_length=50)
    nivel_inteligencia: Literal["padrao", "alto", "maximo"] = "alto"


# ── POST /analisar ────────────────────────────────────────────────────────────

@router.post(
    "/analisar",
    dependencies=[Depends(rate_limit("motor-peca-analisar", 10))],
)
async def analisar(
    case_id: str,
    payload: AnalisarIn | None = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Diagnóstico consolidado documento→peça. TUDO rascunho; nenhum Deadline
    é criado aqui — o termo inicial segue não confirmado até o /gerar."""
    if not _pode_usar(cu):
        raise HTTPException(403, "Motor de Peça restrito a advogados")

    case = await verificar_acesso_caso(db, cu, case_id)
    payload = payload or AnalisarIn()

    # Texto-base + LGPD (sanitizar_pii ANTES de qualquer IA/log)
    texto_bruto = await mps.texto_base_do_caso(db, case, payload.texto)
    texto_limpo, houve_pii = sanitizar_pii(texto_bruto[:18000], [])

    # 1) Diagnóstico — reuso do intake (área provável + teses do banco)
    area_info = await intake_router._identificar_area(
        db, cu, case, intake_router.AnaliseCompletaIn(), texto_limpo
    )
    area = area_info["valor"]
    teses = await intake_router._buscar_teses(db, area)

    # 2) Peça cabível — rito_engine (determinístico) + mapa código→peça→base
    #    legal→prazo. IA entra só na motivação textual (fail-safe).
    from app.services.rito_engine import identificar_rito
    rito = identificar_rito({
        "area": area,
        "texto": texto_limpo[:8000],
        "tipo_documento": payload.tipo_documento,
        "fase": payload.fase or _enum_val(getattr(case, "fase", None)),
        "tribunal": case.tribunal,
    })
    codigos = mps.pecas_cabiveis(rito["codigo"], rito["etapa_atual"])
    pecas = [mps.descrever_peca(c, rito["codigo"]) for c in codigos]

    peca_principal = None
    if payload.peca_codigo and payload.peca_codigo in mps.CATALOGO_PECAS:
        peca_principal = payload.peca_codigo
    elif codigos:
        peca_principal = codigos[0]

    motivacao_ia = None
    if payload.incluir_motivacao_ia and pecas:
        motivacao_ia = await mps.motivacao_pecas_ia(
            db, cu.id, case.id, area, pecas, texto_limpo
        )

    # 3) Prazo PROJETADO — nunca presumir termo inicial; nunca criar Deadline.
    prazo_projetado = None
    if peca_principal:
        prazo_projetado = mps.calcular_prazo_projetado(
            peca_principal, rito["codigo"], payload.termo_inicial,
            tribunal=case.tribunal, em_dobro=payload.em_dobro,
        )

    # 4) Checklist bloqueante da peça proposta
    checklist_itens: list[dict] = []
    checklist_pronto = False
    if peca_principal:
        checklist_itens, checklist_pronto = await mps.montar_checklist(
            db, case, peca_principal, texto_limpo
        )

    ai_logs = [x for x in (area_info.get("ai_log_id"),
                           (motivacao_ia or {}).get("ai_log_id")) if x]

    return {
        "status": "rascunho",
        "aviso": mps.AVISO_HITL,
        "case_id": case.id,
        "termo_inicial_confirmado": False,
        "diagnostico": {
            "area": {"valor": area, "origem": area_info["origem"]},
            "teses": teses,
            "teses_aviso": (None if teses else
                            "Nenhuma tese cadastrada no banco para esta área — "
                            "nada foi inventado (cadastre em /teses)"),
        },
        "rito": rito,
        "pecas_cabiveis": pecas,
        "pecas_aviso": (None if pecas else
                        "Nenhuma peça mapeada deterministicamente para este "
                        "rito/etapa — selecione a peça manualmente."),
        "peca_principal": peca_principal,
        "prazo_projetado": prazo_projetado,
        "checklist": {"itens": checklist_itens, "pronto": checklist_pronto},
        "motivacao_ia": motivacao_ia,
        "pii_removida": houve_pii,
        "ai_log_ids": ai_logs,
    }


# ── POST /gerar ───────────────────────────────────────────────────────────────

@router.post(
    "/gerar",
    status_code=201,
    dependencies=[Depends(rate_limit("motor-peca-gerar", 3))],
)
async def gerar(
    case_id: str,
    req: GerarIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Confirmação humana → cria o Deadline e dispara a redação (fluxo
    existente). 422 se checklist não pronto OU termo inicial não confirmado."""
    if not _pode_usar(cu):
        raise HTTPException(403, "Motor de Peça restrito a advogados")

    if req.peca_codigo not in mps.CATALOGO_PECAS:
        raise HTTPException(422, detail={
            "mensagem": "Peça desconhecida pelo mapa determinístico do Motor de Peça",
            "pecas_validas": sorted(mps.CATALOGO_PECAS.keys()),
        })

    case = await verificar_acesso_caso(db, cu, case_id)
    info = mps.CATALOGO_PECAS[req.peca_codigo]

    # Texto-base + LGPD (sanitizar_pii ANTES de qualquer LLM)
    texto_bruto = await mps.texto_base_do_caso(db, case, req.descricao_fatos)
    texto_limpo, _ = sanitizar_pii(texto_bruto[:18000], [])

    # Rito: NUNCA confiar só no eco do cliente. Sem rito_codigo no request, o
    # servidor recomputa com os mesmos sinais do /analisar — senão overrides de
    # prazo por rito (ex.: JEC/trabalhista, defesa em audiência) se perdem e o
    # Deadline fatal sai errado.
    rito_codigo = req.rito_codigo
    if not rito_codigo:
        from app.services.rito_engine import identificar_rito
        rito_codigo = identificar_rito({
            "area": req.area_direito or _enum_val(getattr(case, "area", None)),
            "texto": texto_limpo[:8000],
            "fase": _enum_val(getattr(case, "fase", None)),
            "tribunal": case.tribunal,
        })["codigo"]
    prazo_info = mps.prazo_da_peca(req.peca_codigo, rito_codigo)

    # Gate 1 — checklist bloqueante (mesmo padrão 422 de conversao_caso.py)
    itens, pronto = await mps.montar_checklist(db, case, req.peca_codigo, texto_limpo)
    if not pronto:
        pendentes = [i for i in itens if not i["ok"]]
        raise HTTPException(status_code=422, detail={
            "mensagem": "Geração bloqueada — checklist da peça com itens pendentes",
            "pendentes": pendentes,
        })

    # Gate 2 — prazo fatal NUNCA sem confirmação humana do termo inicial
    if not req.termo_inicial_confirmado:
        raise HTTPException(status_code=422, detail={
            "mensagem": ("Termo inicial não confirmado pelo advogado — o Motor "
                         "de Peça nunca cria prazo fatal sem confirmação humana."),
            "termo_inicial_confirmado": False,
        })

    # Data fatal: determinística (uteis/corridos) ou manual (contagem=verificar)
    if prazo_info["contagem"] == "uteis" and prazo_info["prazo_dias"]:
        if req.termo_inicial is None:
            raise HTTPException(422, detail={
                "mensagem": "Informe o termo inicial confirmado para calcular o prazo."})
        data_prazo = mps.prazo_dias_uteis(
            req.termo_inicial, prazo_info["prazo_dias"],
            tribunal=case.tribunal, em_dobro=req.em_dobro,
        )
    elif prazo_info["contagem"] == "corridos" and prazo_info["prazo_dias"]:
        if req.termo_inicial is None:
            raise HTTPException(422, detail={
                "mensagem": "Informe o termo inicial confirmado para calcular o prazo."})
        data_prazo = mps.prazo_dias_corridos(
            req.termo_inicial, prazo_info["prazo_dias"], tribunal=case.tribunal,
            # Decadencial (ex.: MS, Lei 12.016 art. 23): vencimento não prorroga.
            prorrogar_fim=not prazo_info.get("decadencial"),
        )
    else:
        if req.data_prazo_manual is None:
            raise HTTPException(422, detail={
                "mensagem": ("Prazo desta peça/rito não é determinável automaticamente "
                             f"({prazo_info['base_legal']}) — informe data_prazo_manual "
                             "após verificar a norma aplicável."),
                "contagem": prazo_info["contagem"],
            })
        data_prazo = req.data_prazo_manual

    # Validação prévia da base fática p/ redação (antes de persistir o Deadline)
    fatos = (req.descricao_fatos or texto_limpo).strip()
    if len(fatos) < 50:
        raise HTTPException(422, detail={
            "mensagem": ("Base fática insuficiente para a redação (mín. 50 "
                         "caracteres) — anexe documentos ou descreva os fatos."),
        })

    # ── Deadline (padrão raio_x_service.converter_em_caso) — SÓ após confirmação
    deadline = Deadline(
        id=str(uuid4()),
        titulo=f"Prazo — {info['nome']}"[:255],
        descricao=("Criado pelo Motor de Peça após confirmação humana do termo "
                   "inicial. Conferir intimação/citação nos autos."),
        tipo=(DeadlineTipo.administrativo if info["tipo_deadline"] == "administrativo"
              else DeadlineTipo.processual),
        prioridade=DeadlinePrioridade.alta,
        status=DeadlineStatus.pendente,
        data_prazo=data_prazo,
        data_intimacao=req.termo_inicial,
        base_legal=(prazo_info["base_legal"] or "")[:255] or None,
        case_id=case.id,
        responsavel_id=cu.id,
        origem="motor_peca",
        confirmado=True,  # termo inicial confirmado explicitamente pelo advogado
    )
    db.add(deadline)
    await criar_audit_log(
        db, cu.id, getattr(cu.role, "value", cu.role), "MOTOR_PECA_GERAR",
        "deadlines", deadline.id,
        detalhes=(f"Motor de Peça: peça={req.peca_codigo} caso={case.id} "
                  f"termo_inicial_confirmado=True base_legal={prazo_info['base_legal']}"),
    )
    # Commit ANTES da redação: o prazo fatal confirmado nunca pode se perder
    # por indisponibilidade de IA.
    await db.commit()

    # ── Redação via fluxo EXISTENTE (HITL + gate de citações preservados) ────
    area = req.area_direito or _enum_val(case.area) or "civil"
    redacao = None
    redacao_erro = None
    try:
        if info["fluxo_geracao"] == "ia_defensiva":
            redacao = await executar_ia_defensiva(
                IaDefensivaInput(
                    etapa="redigir_contestacao",
                    peticao_inicial=texto_limpo,
                    rito=rito_codigo,
                    area=area,
                    dados_formais={"peca": info["nome"],
                                   "base_legal_prazo": prazo_info["base_legal"]},
                    case_id=case.id,
                    momento="motor_peca",
                    nivel_inteligencia=req.nivel_inteligencia,
                ),
                db=db,
                user_id=cu.id,
            )
        else:
            scope_client_id = None
            try:
                from app.services.ai_service import _escopo_cliente_do_caso
                scope_client_id = await _escopo_cliente_do_caso(db, case.id)
            except Exception:
                pass
            from app.services.peca_service import AREAS_DIREITO
            area_pipeline = area if area in AREAS_DIREITO else "civil"
            redacao = await mps.executar_pipeline_peca(
                db=db,
                user_id=cu.id,
                case_id=case.id,
                codigo_peca=req.peca_codigo,
                area_direito=area_pipeline,
                descricao_fatos=fatos[:10000],
                pedidos=(req.pedidos or
                         "Pedidos a definir pelo advogado responsável — [VERIFICAR]"),
                scope_client_id=scope_client_id,
            )
    except Exception as e:
        # Deadline já persistido — a falha de IA não pode apagar o prazo fatal.
        logger.error("[MotorPeca] redação falhou (deadline %s preservado): %s",
                     deadline.id, e)
        redacao_erro = ("Redação indisponível no momento — o prazo foi criado; "
                        "gere a peça manualmente ou tente novamente.")

    return {
        "status": "rascunho",
        "aviso": mps.AVISO_HITL,
        "case_id": case.id,
        "peca_codigo": req.peca_codigo,
        "deadline": {
            "id": deadline.id,
            "titulo": deadline.titulo,
            "data_prazo": data_prazo.isoformat(),
            "base_legal": deadline.base_legal,
            "tipo": _enum_val(deadline.tipo),
            "confirmado": True,
            "termo_inicial": req.termo_inicial.isoformat() if req.termo_inicial else None,
        },
        "termo_inicial_confirmado": True,
        "fluxo_geracao": info["fluxo_geracao"],
        "redacao": redacao,
        "redacao_erro": redacao_erro,
    }
