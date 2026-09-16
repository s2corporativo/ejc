"""Sub-router tributário: PAF federal versionado após LC 227/2026.

Substitui somente a rota histórica de auto de infração no agregador ramos.py.
O handler antigo permanece no arquivo legado para histórico/rollback, mas não é
montado quando o agregador canônico é usado.
"""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import require_roles_exact
from app.models.user import User
from app.routers.ramos_comum import _EQUIPE, _com_regra
from app.services.homologacao_ferramentas import selo_homologacao
from app.services.tributario_paf import (
    FONTES_PAF,
    VERSAO_REGRA_PAF,
    calcular_prazo_impugnacao_paf,
)

router = APIRouter(tags=["Áreas de Atuação"])
ROTA_AUTO_INFRACAO = "/tributario/ferramentas/auto-infracao-prazos"


@router.get(ROTA_AUTO_INFRACAO)
@_com_regra("trib_auto_infracao_prazos")
async def trib_auto_infracao_prazos(
    data_ciencia: date,
    valor_multa: float = Query(0.0, ge=0),
    esfera: Literal["federal", "estadual", "municipal"] = "federal",
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """PAF federal com regra temporal vigente; não infere prazo de outro ente."""
    if esfera != "federal":
        raise HTTPException(
            422,
            detail=(
                "Prazo não calculado: processo tributário estadual/municipal exige "
                "identificação do ente, norma processual vigente e marco de ciência. "
                "Não é seguro reutilizar o prazo federal por analogia."
            ),
        )

    prazo = calcular_prazo_impugnacao_paf(data_ciencia)
    vencimento = prazo["vencimento"]
    dias_calendario_restantes = (vencimento - date.today()).days

    out = {
        "esfera": "federal",
        "data_ciencia": data_ciencia,
        "prazo_impugnacao": prazo["prazo"],
        "criterio_temporal": prazo["criterio"],
        "componentes_calculo": prazo["componentes"],
        "vencimento_impugnacao": vencimento,
        "dias_calendario_restantes": max(dias_calendario_restantes, 0),
        "vencido": dias_calendario_restantes < 0,
        "efeito_da_impugnacao": (
            "Impugnação tempestiva instaura a fase litigiosa e suspende a "
            "exigibilidade do crédito tributário (CTN art. 151, III)."
        ),
        "reducoes_multa_de_oficio": {
            "pagamento_ou_compensacao_em_30_dias": {
                "reducao_pct": 50,
                "multa_reduzida": round(valor_multa * 0.50, 2),
            },
            "parcelamento_requerido_em_30_dias": {
                "reducao_pct": 40,
                "multa_reduzida": round(valor_multa * 0.60, 2),
            },
            "pagamento_ou_compensacao_em_30_dias_da_decisao_1a_instancia": {
                "reducao_pct": 30,
                "multa_reduzida": round(valor_multa * 0.70, 2),
            },
            "parcelamento_em_30_dias_da_decisao_1a_instancia": {
                "reducao_pct": 20,
                "multa_reduzida": round(valor_multa * 0.80, 2),
            },
            "base": "Lei 8.218/1991 art. 6º",
        },
        "fluxo_recursal": [
            "Impugnação à DRJ — prazo calculado acima conforme art. 15 do Decreto 70.235/72",
            "Recurso voluntário ao CARF — 20 dias úteis, observada a mesma transição de 2026 (art. 33)",
            "Recurso especial/CSRF — verificar cabimento e prazo no RICARF vigente; este endpoint não calcula essa etapa",
        ],
        "fontes": FONTES_PAF + [
            "CTN art. 151, III",
            "Lei 8.218/1991 art. 6º — reduções de multa de ofício",
        ],
        "vigencia_regra": (
            "LC 227/2026 vigente desde 14/01/2026; transição do ADI RFB 2/2026 "
            "para intimações até 31/03/2026"
        ),
        "versao_regra_especifica": VERSAO_REGRA_PAF,
        "aviso": (
            "MINUTA — confirmar data e forma de ciência, expediente/calendário "
            "aplicável e eventual regra específica do lançamento antes de usar "
            "como prazo fatal."
        ),
    }
    return selo_homologacao(ROTA_AUTO_INFRACAO, out)
