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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, ROLE_LEVEL
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
    # Evento processual (Fase 2): quando informado com data_evento, o termo
    # inicial é DERIVADO deterministicamente (evento_processual.resolver_termo_
    # inicial, base legal citada). A IA nunca calcula; eventos incertos saem
    # como "verificar". termo_inicial explícito tem precedência sobre o evento.
    evento: Optional[str] = Field(None, max_length=64)
    data_evento: Optional[date] = None
    meio: Optional[str] = Field(None, max_length=32)
    peca_codigo: Optional[str] = Field(None, max_length=64)
    em_dobro: bool = Field(False, description="Prazo em dobro (CPC arts. 180/183/186)")
    incluir_motivacao_ia: bool = True


class GerarIn(BaseModel):
    """Resultado CONFIRMADO pelo advogado (HITL)."""
    peca_codigo: str = Field(..., max_length=64)
    rito_codigo: Optional[str] = Field(None, max_length=64)
    termo_inicial: Optional[date] = None
    # Evento processual (Fase 2) — alternativa determinística ao termo_inicial
    # explícito. O gate termo_inicial_confirmado NÃO muda: mesmo derivado do
    # evento, o termo só vira Deadline com confirmação humana explícita.
    evento: Optional[str] = Field(None, max_length=64)
    data_evento: Optional[date] = None
    meio: Optional[str] = Field(None, max_length=32)
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
    #    Evento processual (Fase 2): deriva o termo DETERMINISTICAMENTE (base
    #    legal citada); eventos incertos saem "verificar" e nada é presumido.
    evento_info = None
    termo_inicial = payload.termo_inicial
    termo_origem = "informado_pelo_advogado" if termo_inicial else None
    if payload.evento and payload.data_evento:
        from app.services.evento_processual import resolver_termo_inicial
        evento_info = resolver_termo_inicial(
            payload.evento, payload.data_evento, payload.meio)
        if termo_inicial is None and evento_info["contagem_confirmavel"]:
            termo_inicial = evento_info["termo_inicial"]
            termo_origem = "derivado_de_evento"

    prazo_projetado = None
    if peca_principal:
        prazo_projetado = mps.calcular_prazo_projetado(
            peca_principal, rito["codigo"], termo_inicial,
            tribunal=case.tribunal, em_dobro=payload.em_dobro,
        )
        prazo_projetado["termo_inicial_origem"] = termo_origem
        if evento_info:
            prazo_projetado["evento_base_legal"] = evento_info["base_legal"]

    # 4) Checklist bloqueante da peça proposta
    checklist_itens: list[dict] = []
    checklist_pronto = False
    if peca_principal:
        checklist_itens, checklist_pronto = await mps.montar_checklist(
            db, case, peca_principal, texto_limpo
        )

    ai_logs = [x for x in (area_info.get("ai_log_id"),
                           (motivacao_ia or {}).get("ai_log_id")) if x]

    resposta = {
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
        "evento_processual": evento_info,
        "prazo_projetado": prazo_projetado,
        "checklist": {"itens": checklist_itens, "pronto": checklist_pronto},
        "motivacao_ia": motivacao_ia,
        "pii_removida": houve_pii,
        "ai_log_ids": ai_logs,
    }

    # ── FASE 1 (Orquestrador Jurídico) — snapshot versionado do diagnóstico.
    # ADITIVO e FAIL-SAFE: payload = resposta consolidada SEM textos gigantes
    # (compactar_payload garante ~50KB, descartando motivacao_ia/checklist se
    # preciso); falha do snapshot vira warning e NUNCA quebra a resposta.
    try:
        from app.services import case_intelligence_service as cis
        await cis.gravar_snapshot_seguro(
            db,
            case_id=case.id,
            origem="motor_peca",
            payload=cis.compactar_payload({
                "area": area,
                "teses": teses,
                "rito": rito,
                "peca_sugerida": peca_principal,
                "pecas_cabiveis": pecas,
                "prazos_projetados": prazo_projetado,
                "checklist": {"itens": checklist_itens, "pronto": checklist_pronto},
                "motivacao_ia": motivacao_ia,
                "fontes": ["motor_peca_analisar"],
            }, descartaveis=("motivacao_ia", "checklist", "pecas_cabiveis")),
            resumo=f"Motor de Peça — diagnóstico (área: {area or '—'}, "
                   f"peça sugerida: {peca_principal or '—'})",
            ai_log_ids=ai_logs,
            criado_por=cu.id,
        )
    except Exception as e:
        logger.warning(
            f"[motor_peca] Snapshot não gravado ({case.id}): {str(e)[:200]}")

    return resposta


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

    # Núcleo extraído para motor_peca_service.confirmar_e_criar_prazo (fonte
    # única, reusada pela tool `criar_prazo_confirmado` do agente): evento→termo,
    # gates INVIOLÁVEIS (checklist; termo confirmado por humano), cálculo da data
    # fatal e criação do Deadline (auditoria + commit). Comportamento idêntico —
    # GateBloqueado carrega o MESMO detail dos antigos HTTPException(422).
    try:
        confirmado = await mps.confirmar_e_criar_prazo(
            db, cu, case,
            peca_codigo=req.peca_codigo,
            termo_inicial=req.termo_inicial,
            evento=req.evento,
            data_evento=req.data_evento,
            meio=req.meio,
            termo_inicial_confirmado=req.termo_inicial_confirmado,
            data_prazo_manual=req.data_prazo_manual,
            em_dobro=req.em_dobro,
            rito_codigo=req.rito_codigo,
            area_direito=req.area_direito,
            texto=req.descricao_fatos,
        )
    except mps.GateBloqueado as e:
        raise HTTPException(status_code=422, detail=e.detail)

    deadline = confirmado["deadline"]
    data_prazo = confirmado["data_prazo"]
    evento_info = confirmado["evento_info"]
    termo_inicial = confirmado["termo_inicial"]
    prazo_info = confirmado["prazo_info"]
    rito_codigo = confirmado["rito_codigo"]
    texto_limpo = confirmado["texto_limpo"]
    fatos = confirmado["fatos"]

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
            "termo_inicial": termo_inicial.isoformat() if termo_inicial else None,
        },
        "evento_processual": evento_info,
        "termo_inicial_confirmado": True,
        "fluxo_geracao": info["fluxo_geracao"],
        "redacao": redacao,
        "redacao_erro": redacao_erro,
    }
