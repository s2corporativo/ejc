# ── app/routers/triagem_entrevista.py ────────────────────────────────────────
# Entrevista Inteligente (Jornada do Caso — etapa 2 / Triagem).
# POST /triagem/entrevista: o advogado descreve o ocorrido em texto livre e a
# IA devolve um painel estruturado de triagem preliminar (área, competência,
# possível ação, urgência, tutela, prescrição, valor da causa, pedidos, riscos,
# chance de êxito) — cada item com confiança 0-100.
#
# O pipeline (sanitizar_ou_abortar → ai_gateway.chat(task_type="triagem") →
# registrar_ai_log) vive em services/triagem_entrevista_service.py — núcleo
# COMPARTILHADO com a Entrada Única (routers/entrada.py). Este router mantém
# os gates (RBAC, AI_ENABLED, ownership) e a ponte Entrevista → Ficha.
# Tudo é ESTIMATIVA PRELIMINAR / RASCUNHO (HITL) — nunca parecer definitivo,
# nunca promessa de resultado — revisão humana do advogado responsável é
# obrigatória.
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.services.triagem_entrevista_service import (
    AVISO_ESTIMATIVA,
    TriagemIndisponivelError,
    analisar_relato,
)

settings = get_settings()
logger = logging.getLogger("ejc.triagem.entrevista")

router = APIRouter(prefix="/triagem", tags=["Triagem — Entrevista Inteligente"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class EntrevistaIn(BaseModel):
    relato: str = Field(..., min_length=40, max_length=15000,
                        description="Relato livre do ocorrido ('Conte o ocorrido')")
    case_id: Optional[str] = Field(None, max_length=36)


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/entrevista",
             dependencies=[Depends(rate_limit("triagem-entrevista", 10))])
async def entrevista_inteligente(
    payload: EntrevistaIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Entrevista Inteligente: relato livre → painel de triagem preliminar com
    confiança por item. Toda a resposta é RASCUNHO (HITL obrigatório).
    """
    # Mesmo limiar de intake.py: sugestões de IA restritas a advogado+
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(403, "Sugestões de IA restritas a advogados")
    if not settings.AI_ENABLED:
        raise HTTPException(503, "IA desabilitada na configuração")

    # Gate canônico de ownership quando a entrevista está vinculada a um caso
    case = None
    if payload.case_id:
        case = await verificar_acesso_caso(db, cu, payload.case_id)

    # Com caso conhecido, os nomes das partes ganham pseudonimização REVERSÍVEL
    # no gateway (mesmo padrão de provas.sugerir-faltantes) — sem isso, nomes
    # digitados no relato iam em claro ao provedor externo.
    entidades = None
    if case is not None:
        from app.services.ai.entidades_caso import entidades_do_caso
        entidades = await entidades_do_caso(db, case.id) or None

    try:
        resultado = await analisar_relato(
            db, cu, payload.relato,
            case_id=case.id if case else None,
            entidades=entidades,
        )
    except TriagemIndisponivelError:
        raise HTTPException(503, "IA indisponível no momento. Tente novamente.")

    dados, analise = resultado["dados"], resultado["analise"]

    # Ponte Entrevista → Ficha de Triagem: o painel alimenta a ficha do caso
    # como RASCUNHO (HITL preservado), preenchendo APENAS campos ainda vazios
    # e jamais tocando ficha já CONFIRMADA. Fail-soft: falha aqui não derruba
    # a resposta da entrevista.
    ficha_atualizada = False
    if case is not None and dados is not None:
        try:
            ficha_atualizada = await _alimentar_ficha(db, case.id, analise, cu)
        except Exception as e:
            logger.warning(f"Entrevista→Ficha: falha ao alimentar rascunho: {e}")

    return {
        "status": "rascunho",
        "aviso": AVISO_ESTIMATIVA,
        "case_id": case.id if case else None,
        "analise": analise,
        "parse_ok": resultado["parse_ok"],
        "ficha_atualizada": ficha_atualizada,
        "pii_removida": resultado["pii_removida"],
        "modelo": resultado["modelo"],
        "ai_log_id": resultado["ai_log_id"],
    }


async def _alimentar_ficha(db: AsyncSession, case_id: str,
                           analise: dict, cu: User) -> bool:
    """Grava o painel na ficha do caso (rascunho). Regras:
    • ficha CONFIRMADA nunca é tocada (o gate da peça é do advogado);
    • em ficha existente, só campos VAZIOS são preenchidos (não sobrescreve
      trabalho humano); a confiança nova é MESCLADA à existente."""
    from app.services import ficha_triagem_service as fts

    ficha = await fts.obter(db, case_id)
    if ficha is not None and ficha.status == "confirmada":
        return False

    campos = fts.dados_do_painel_entrevista(analise)
    conf = campos.pop("confianca", {})
    if ficha is not None:
        campos = {
            k: v for k, v in campos.items()
            if getattr(ficha, k, None) in (None, "")
        }
        conf = {k: v for k, v in conf.items() if k in campos}
        conf = {**(ficha.confianca or {}), **conf}
    if not campos:
        return False
    if conf:
        campos["confianca"] = conf
    await fts.salvar(db, case_id, campos, confirmar=False,
                     user_id=cu.id, user_role=cu.role.value,
                     preservar_confirmada=True)
    return True
