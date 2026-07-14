# ── app/routers/indices.py ───────────────────────────────────────────────────
# Índices oficiais do BCB (SGS + Olinda) para cálculos judiciais.
# Auth: qualquer usuário logado (nível padrão) · rate limit 30/min por usuário.
# Gate: INDICES_BCB_ENABLED (default True — API pública gratuita, sem chave).
# Saídas são MINUTAS de cálculo (HITL) — o profissional revisa.
from __future__ import annotations

import logging
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.services import indices_service
from app.services.indices_service import SERIES, BCBIndisponivel

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/indices", tags=["Índices oficiais (BCB)"],
    dependencies=[Depends(rate_limit("indices", 30))],
)


def _gate() -> None:
    if not get_settings().INDICES_BCB_ENABLED:
        raise HTTPException(503, "Integração de índices BCB desabilitada "
                                 "(INDICES_BCB_ENABLED=false)")


# ── Schemas ───────────────────────────────────────────────────────────────────

Regra = Literal["correcao", "correcao_mais_taxa_legal", "selic_ec113"]


class AtualizarValorIn(BaseModel):
    valor: float = Field(..., gt=0)
    indice: str = Field("ipca", description=f"Um de: {list(SERIES)}")
    data_inicial: date
    data_final: date
    regra: Regra = Field(
        "correcao",
        description=("correcao = só correção monetária pelo índice · "
                     "correcao_mais_taxa_legal = correção + juros da Taxa Legal "
                     "(Lei 14.905/2024, série 29543) sobre o valor corrigido · "
                     "selic_ec113 = Selic exclusiva (EC 113/2021 — Fazenda Pública)"),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────
# Atenção à ordem: rotas fixas (/series, /taxa-juros, /ptax, /atualizar-valor)
# ANTES da paramétrica /{indice}.

@router.get("/series")
async def series(cu: User = Depends(get_current_user)):
    """Séries SGS suportadas, com o último valor divulgado de cada uma."""
    _gate()
    return {"series": await indices_service.listar_series()}


@router.get("/taxa-juros")
async def taxa_juros(
    modalidade: Optional[str] = Query(None, max_length=200),
    instituicao: Optional[str] = Query(None, max_length=200),
    cu: User = Depends(get_current_user),
):
    """Taxas de juros por modalidade/instituição (Olinda — revisional bancária)."""
    _gate()
    try:
        return await indices_service.taxa_juros_modalidade(
            modalidade=modalidade, instituicao=instituicao)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except Exception:
        logger.exception("Falha ao consultar o BCB/Olinda (taxa-juros)")
        raise HTTPException(502, "Falha ao consultar o serviço do BCB (Olinda)")


@router.get("/ptax")
async def ptax(
    data_inicial: date = Query(...),
    data_final: date = Query(...),
    cu: User = Depends(get_current_user),
):
    """Cotações PTAX (USD) do período — câmbio oficial do BCB."""
    _gate()
    try:
        cotacoes = await indices_service.ptax(data_inicial, data_final)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:
        logger.exception("Falha ao consultar o BCB/Olinda (PTAX)")
        raise HTTPException(502, "Falha ao consultar o serviço do BCB (PTAX)")
    return {"periodo": f"{data_inicial.isoformat()} → {data_final.isoformat()}",
            "total": len(cotacoes), "cotacoes": cotacoes,
            "fonte": "Banco Central — PTAX (Olinda)"}


@router.post("/atualizar-valor")
async def atualizar_valor(req: AtualizarValorIn, cu: User = Depends(get_current_user)):
    """Atualiza um valor por índice oficial com memória de cálculo passo a
    passo (fatores mensais). MINUTA — HITL."""
    _gate()
    try:
        if req.regra == "selic_ec113":
            sel = await indices_service.selic_acumulada(req.data_inicial, req.data_final)
            valor_final = round(req.valor * sel["fator"], 2)
            return {"regra": req.regra, "valor_original": req.valor,
                    "valor_final": valor_final, "etapas": [sel]}

        correcao = await indices_service.atualizar_valor(
            req.valor, req.indice, req.data_inicial, req.data_final)
        if req.regra == "correcao":
            return {"regra": req.regra, "valor_original": req.valor,
                    "valor_final": correcao["valor_final"], "etapas": [correcao]}

        # correcao_mais_taxa_legal: juros legais sobre o valor CORRIGIDO
        juros = await indices_service.juros_taxa_legal(
            correcao["valor_corrigido"], req.data_inicial, req.data_final)
        return {"regra": req.regra, "valor_original": req.valor,
                "valor_final": juros["valor_com_juros"],
                "etapas": [correcao, juros]}
    except ValueError as e:
        raise HTTPException(422, str(e))
    except BCBIndisponivel as e:
        raise HTTPException(502, str(e))
    except Exception:
        logger.exception("Falha ao atualizar valor (índices BCB)")
        raise HTTPException(502, "Falha ao consultar o serviço do BCB")


@router.get("/{indice}")
async def serie_periodo(
    indice: str,
    data_inicial: date = Query(...),
    data_final: date = Query(...),
    cu: User = Depends(get_current_user),
):
    """Valores de uma série SGS no período (cache-first; pagina janelas de
    10 anos automaticamente)."""
    _gate()
    if indice not in SERIES:
        raise HTTPException(404, f"Índice desconhecido. Use: {list(SERIES)}")
    try:
        serie = await indices_service.obter_serie(indice, data_inicial, data_final)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except BCBIndisponivel as e:
        raise HTTPException(502, str(e))
    cfg = SERIES[indice]
    return {
        "indice": indice, "nome": cfg["nome"], "codigo_sgs": cfg["codigo"],
        "tipo": cfg["tipo"],
        "periodo": f"{data_inicial.isoformat()} → {data_final.isoformat()}",
        "total": len(serie),
        "valores": [{"data": d.isoformat(), "valor": float(v)} for d, v in serie],
        "fonte": f"Banco Central — SGS série {cfg['codigo']}",
    }
