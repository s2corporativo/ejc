"""
Router de Diplomacia Digital — EJC v3.0
Estratégia de Acordos e Liquidez Judicial.

P1 (2026-07-05):
- /calcular-acordo usa a Selic REAL do BCB (bcb_service.selic_anualizada,
  série 4390 anualizada, com fallback determinístico 10,75% + cache negativo)
  quando o caller não informa `selic_anual` — mesmo padrão de
  routers/visual_law.py::breakeven. Chaves novas são ADITIVAS (selic_fonte).

REMOÇÃO (2026-08-02, Bloco 4 do plano de lançamento):
Os endpoints `/dossie-pressao` e `/analisar-magistrado` foram REMOVIDOS por
decisão do escritório, não por defeito técnico. Um "dossiê de pressão" e uma
"análise de magistrado" num sistema de escritório de advocacia são risco
reputacional e disciplinar indefensável se expostos numa perícia ou numa
representação — independentemente do que o código faça, e ambos estavam sem uso
(nenhuma tela do sistema os chamava).

Não reintroduza nenhum dos dois sem decisão escrita do titular. O que
permanece aqui é o cálculo de ponto de equilíbrio para acordo, que é
matemática financeira legítima e está em uso pela tela CalculadoraAcordo.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.models.user import User
from app.services import bcb_service
from app.services.diplomacia_digital import diplomacia

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
