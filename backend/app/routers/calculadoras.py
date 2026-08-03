# ── app/routers/calculadoras.py ──────────────────────────────────────────────
# Calculadoras jurídicas (Bloco C). Ferramentas stateless de apoio ao advogado.
# Todas as saídas são MINUTAS de cálculo (HITL) — o profissional revisa.
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import require_roles
from app.models.user import User
from app.services.calc.trabalhista import calcular, EntradaRescisao, TIPOS
from app.services.calc.tax_tables import inss as calc_inss, irrf as calc_irrf
from app.services.calc.prescricao import (
    calcular as calc_prescricao, EntradaPrescricao, PRAZOS,
)
from app.services.calc import custas_tjmg
from app.services import bcb_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calculadoras", tags=["calculadoras"])

# Equipe interna (cliente externo não acessa ferramentas internas)
_EQUIPE = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"]


# ── Schemas ───────────────────────────────────────────────────────────────────
class RescisaoIn(BaseModel):
    salario: float = Field(..., gt=0, description="Salário mensal bruto")
    admissao: date
    demissao: date
    tipo: str = Field("sem_justa_causa", description=f"Um de: {list(TIPOS)}")
    aviso_indenizado: bool = True
    dias_trabalhados_mes: int | None = Field(None, ge=0, le=31)
    ferias_vencidas: bool = False
    saldo_fgts: float = Field(0.0, ge=0)
    dependentes: int = Field(0, ge=0, le=20)


class CorrecaoIn(BaseModel):
    valor: float = Field(..., gt=0)
    data_inicial: date
    data_final: date
    indice: str = Field("ipca", description=(
        "Legados: ipca | ipca_e | inpc | selic | tr. Com INDICES_BCB_ENABLED "
        "aceita também as séries oficiais do indices_service (igpm, ipca15, "
        "cdi_mensal, selic_mensal, poupanca, taxa_legal…)"))
    juros_mora_pct_mes: float = Field(0.0, ge=0, le=100)


class PrescricaoIn(BaseModel):
    chave: str = Field(..., description="Chave do prazo (ver /prescricao/tipos)")
    termo_inicial: date = Field(..., description="Data do fato/violação/ciência")


# ── Endpoints ──────────────────────────────────────────────────────────────────
@router.get("/tipos-rescisao")
async def tipos_rescisao(cu: User = Depends(require_roles(_EQUIPE))):
    """Lista os tipos de rescisão suportados e suas regras."""
    return {k: v["rotulo"] for k, v in TIPOS.items()}


@router.post("/trabalhista/rescisao")
async def rescisao(req: RescisaoIn, cu: User = Depends(require_roles(_EQUIPE))):
    """Calcula verbas rescisórias (CLT) com memória auditável. MINUTA — HITL."""
    try:
        return calcular(EntradaRescisao(
            salario=req.salario, admissao=req.admissao, demissao=req.demissao,
            tipo=req.tipo, aviso_indenizado=req.aviso_indenizado,
            dias_trabalhados_mes=req.dias_trabalhados_mes,
            ferias_vencidas=req.ferias_vencidas, saldo_fgts=req.saldo_fgts,
            dependentes=req.dependentes,
        ))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/inss")
async def inss_endpoint(
    salario: float = Query(..., gt=0),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Contribuição INSS 2026 (progressiva, faixa a faixa)."""
    return calc_inss(salario)


@router.get("/irrf")
async def irrf_endpoint(
    rendimento: float = Query(..., gt=0),
    inss: float = Query(0.0, ge=0),
    dependentes: int = Query(0, ge=0, le=20),
    pensao: float = Query(0.0, ge=0),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """IRRF 2026 mensal (tabela progressiva + redutor Lei 15.270/2025)."""
    return calc_irrf(rendimento, inss, dependentes=dependentes, pensao=pensao)


@router.post("/correcao-monetaria")
async def correcao_monetaria(req: CorrecaoIn, cu: User = Depends(require_roles(_EQUIPE))):
    """Atualização monetária por índice oficial (BCB SGS) + juros de mora.

    Índices: ipca/ipca_e/inpc/selic/tr (legado bcb_service) e, com
    INDICES_BCB_ENABLED, qualquer série mensal do indices_service (igpm,
    ipca15, cdi_mensal, taxa_legal…). Memória mês a mês. MINUTA — HITL.
    """
    try:
        # Séries além das legadas → fonte oficial nova (cache persistente).
        if req.indice not in bcb_service.SERIES:
            from app.core.config import get_settings
            from app.services import indices_service
            if (get_settings().INDICES_BCB_ENABLED
                    and req.indice in indices_service.SERIES):
                return await indices_service.atualizar_valor(
                    req.valor, req.indice, req.data_inicial, req.data_final,
                    juros_mora_pct_mes=req.juros_mora_pct_mes,
                )
        return await bcb_service.atualizar_valor(
            req.valor, req.data_inicial, req.data_final,
            indice=req.indice, juros_mora_pct_mes=req.juros_mora_pct_mes,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        logger.exception("Falha ao consultar o BCB (correção monetária)")
        raise HTTPException(status_code=502, detail="Falha ao consultar o serviço do BCB")


@router.get("/prescricao/tipos")
async def prescricao_tipos(cu: User = Depends(require_roles(_EQUIPE))):
    """Catálogo de prazos prescricionais/decadenciais com base legal."""
    return {
        k: {"rotulo": v["rotulo"], "tipo": v["tipo"], "base_legal": v["base_legal"],
            "duracao": (f"{v['anos']} ano(s)" if "anos" in v else f"{v['dias']} dia(s)")}
        for k, v in PRAZOS.items()
    }


@router.post("/prescricao")
async def prescricao(req: PrescricaoIn, cu: User = Depends(require_roles(_EQUIPE))):
    """Calcula data-limite e situação de um prazo prescricional/decadencial.

    MINUTA (HITL) — não considera suspensões/interrupções do caso concreto.
    """
    try:
        return calc_prescricao(EntradaPrescricao(chave=req.chave, termo_inicial=req.termo_inicial))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/custas-tjmg")
async def custas_tjmg_endpoint(
    valor_causa: float = Query(..., gt=0),
    grupo: int = Query(1, ge=1, le=7,
                       description="Grupo da tabela oficial: 1 cível/fazenda, "
                                   "2 família/JEC, 3 sucessões, 6 cautelar/"
                                   "jurisd. voluntária, 7 mandado de segurança"),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Custas iniciais + Taxa Judiciária TJMG (1ª instância, tabela oficial
    2026 — Anexo I da Lei 14.939/2003). Resultado é MINUTA: a guia oficial
    se emite no sistema do TJMG. Grupos 4/5 (rubricas fixas) seguem 503."""
    return custas_tjmg.analisar(valor_causa, grupo=grupo)
