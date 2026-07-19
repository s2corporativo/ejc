"""
Router de Diplomacia Digital — EJC v3.0
Estratégia de Acordos e Liquidez Judicial.

P1 (2026-07-05):
- /calcular-acordo agora usa a Selic REAL do BCB (bcb_service.selic_anualizada,
  série 4390 anualizada, com fallback determinístico 10,75% + cache negativo)
  quando o caller não informa `selic_anual` — mesmo padrão de
  routers/visual_law.py::breakeven. Chaves novas são ADITIVAS (selic_fonte).
- POST /dossie-pressao materializa gerar_dossie_pressao (antes string fixa):
  gateway central de IA + AILog (registrar_ai_log) + saída rascunho (HITL).
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.services import bcb_service
from app.services.diplomacia_digital import diplomacia
from app.services.sentimento_magistrado import sentimento_ia

router = APIRouter(prefix="/diplomacia-v3", tags=["Diplomacia"])


async def _resolver_selic(payload: dict) -> tuple[float, str]:
    """Selic anual: informada no payload > BCB (real) > fallback 10,75%.
    O fallback/cache negativo fica encapsulado em bcb_service.selic_anualizada."""
    if payload.get("selic_anual") is not None:
        return float(payload["selic_anual"]), "informada"
    selic = await bcb_service.selic_anualizada()
    return selic["selic_anual"], selic["fonte"]


@router.post("/calcular-acordo")
async def calcular_acordo(payload: dict, cu: User = Depends(get_current_user)):
    valor = payload.get("valor_causa")
    prob = payload.get("prob_exito")
    tempo = payload.get("tempo_anos")

    if valor is None or prob is None or tempo is None:
        raise HTTPException(400, "Dados insuficientes para cálculo.")

    selic_anual, selic_fonte = await _resolver_selic(payload)
    resultado = diplomacia.calcular_ponto_equilibrio(
        valor, prob, tempo, selic_anual=selic_anual,
    )
    resultado["selic_fonte"] = selic_fonte  # aditivo — contrato antigo intacto
    return resultado


@router.post("/dossie-pressao",
             dependencies=[Depends(rate_limit("dossie-pressao", 5))])
async def dossie_pressao(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Dossiê de Pressão (Visual Law): calcula o ponto de equilíbrio e gera,
    via gateway central de IA, a argumentação de negociação para a parte
    contrária. Saída é RASCUNHO — revisão humana obrigatória (HITL/OAB)."""
    from app.services.ai_guard import registrar_ai_log
    from app.models.ai_log import AITipoUso

    valor = payload.get("valor_causa")
    prob = payload.get("prob_exito")
    tempo = payload.get("tempo_anos")
    if valor is None or prob is None or tempo is None:
        raise HTTPException(400, "Dados insuficientes (valor_causa, prob_exito, tempo_anos).")

    case_id = payload.get("case_id")
    if case_id:
        await verificar_acesso_caso(db, cu, case_id)

    selic_anual, selic_fonte = await _resolver_selic(payload)
    dados = diplomacia.calcular_ponto_equilibrio(
        valor, prob, tempo, selic_anual=selic_anual,
    )
    dados["selic_fonte"] = selic_fonte

    dossie = await diplomacia.gerar_dossie_pressao(dados)

    # Auditoria: rastro obrigatório em ai_logs (HITL/LGPD). Prompt contém
    # apenas dados numéricos do cálculo — sem PII (pii_removida=False).
    log_id = await registrar_ai_log(
        db, user_id=cu.id, tipo_uso=AITipoUso.analise_caso, case_id=case_id,
        prompt_sanitizado=dossie["prompt"], pii_removida=False,
        resposta=dossie["argumentacao"],
        modelo=f"{dossie['provedor']}/{dossie['modelo']}",
        tokens_input=dossie.get("input_tokens"),
        tokens_output=dossie.get("output_tokens"),
    )
    return {
        "dados_acordo": dados,
        "argumentacao": dossie["argumentacao"],
        "modelo": dossie["modelo"],
        "provedor": dossie["provedor"],
        "log_id": log_id,
        "is_rascunho": True,
        "aviso_hitl": "Rascunho sujeito à revisão humana (HITL obrigatório — OAB).",
    }


class AnalisarMagistradoRequest(BaseModel):
    """Payload VALIDADO (Pydantic → 422 em entrada malformada, nunca 500).

    Tetos defensivos: 50 decisões × 4.000 chars ≈ 200k chars — acima disso é
    abuso de tokens no gateway de IA, não uso legítimo (o prompt do shim usa
    um recorte das decisões)."""

    decisoes: list[Annotated[str, StringConstraints(max_length=4000)]] = Field(
        default_factory=list, max_length=50,
    )
    case_id: Optional[str] = Field(None, max_length=64)


@router.post("/analisar-magistrado", dependencies=[Depends(rate_limit("analisar-magistrado", 10))])
async def analisar_magistrado(
    req: AnalisarMagistradoRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Análise de tendência do magistrado via shim ai_brain (sentimento_ia).
    Auditoria: rastro obrigatório em ai_logs (HITL/LGPD) — mesmo padrão de
    dossie_pressao acima. Contrato de resposta inalterado (str)."""
    from app.services.ai_guard import registrar_ai_log
    from app.models.ai_log import AITipoUso
    from app.services.sanitizer import sanitizar_pii

    decisoes = req.decisoes

    case_id = req.case_id
    if case_id:
        await verificar_acesso_caso(db, cu, case_id)

    resultado = await sentimento_ia.analisar_tendencia(decisoes)

    # Prompt logado já sanitizado (o shim ai_brain aplica a mesma sanitização
    # antes do envio ao gateway central) — nunca grava PII bruta no AILog.
    prompt_limpo, houve_pii = sanitizar_pii("\n".join(decisoes[:10]))
    await registrar_ai_log(
        db, user_id=cu.id, tipo_uso=AITipoUso.analise_caso, case_id=case_id,
        prompt_sanitizado=prompt_limpo, pii_removida=houve_pii,
        resposta=resultado,
    )
    return resultado
