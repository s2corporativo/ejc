# ── app/routers/infosimples_receita.py ───────────────────────────────────────
# Caso de uso Infosimples #2 — situação cadastral na Receita Federal.
#
#   POST /infosimples/receita/cpf  — caminho receita-federal/cpf
#   POST /infosimples/receita/cnpj — caminho receita-federal/cnpj
#   Ambos advogado+ (require_roles) e rate limit 10/min por usuário.
#
# CUSTO: consultas PAGAS — flag/teto/cache no infosimples_service.
# LGPD/PII: CPF e data de nascimento são mascarados nos logs/audit
# (infosimples_service.mascarar_parametros); o retorno BRUTO da Receita não é
# persistido além do cache do dia (necessário para não pagar duas vezes a
# mesma consulta; purga automática em _RETENCAO_DIAS). A resposta completa
# vai só ao chamador; o audit guarda apenas o resumo mascarado.
# Validação de DV de CPF/CNPJ ANTES de chamar a API: consulta com documento
# inválido seria dinheiro jogado fora.
from __future__ import annotations

import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import require_roles
from app.models.user import User
from app.services import infosimples_service

logger = logging.getLogger("ejc.infosimples")

router = APIRouter(
    prefix="/infosimples/receita", tags=["Infosimples (consultas pagas)"]
)

_ADVOGADO_MAIS = require_roles(["advogado"])


# ── Validação de dígitos verificadores (evita pagar por consulta inválida) ────

def _cpf_valido(cpf: str) -> bool:
    d = re.sub(r"\D", "", cpf or "")
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        dv = (soma * 10) % 11 % 10
        if dv != int(d[n]):
            return False
    return True


def _cnpj_valido(cnpj: str) -> bool:
    d = re.sub(r"\D", "", cnpj or "")
    if len(d) != 14 or d == d[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, n in ((pesos1, 12), (pesos2, 13)):
        soma = sum(int(d[i]) * pesos[i] for i in range(n))
        dv = 11 - (soma % 11)
        dv = 0 if dv >= 10 else dv
        if dv != int(d[n]):
            return False
    return True


# ── Schemas (documentam os parâmetros repassados à Infosimples) ───────────────

class ReceitaCPFIn(BaseModel):
    """Consulta de CPF na Receita Federal (receita-federal/cpf).

    A Receita exige CPF + data de nascimento para emitir a situação
    cadastral. Parâmetros repassados à Infosimples: `cpf` (11 dígitos) e
    `birthdate` (dd/mm/aaaa).
    """
    cpf: str = Field(description="CPF (11 dígitos, com ou sem máscara)")
    data_nascimento: str = Field(
        description="Data de nascimento do titular, formato dd/mm/aaaa "
                    "(exigida pela consulta da Receita)."
    )

    @field_validator("cpf")
    @classmethod
    def _v_cpf(cls, v: str) -> str:
        d = re.sub(r"\D", "", v or "")
        if not _cpf_valido(d):
            raise ValueError("CPF inválido (dígitos verificadores não conferem).")
        return d

    @field_validator("data_nascimento")
    @classmethod
    def _v_nasc(cls, v: str) -> str:
        try:
            return datetime.strptime((v or "").strip(), "%d/%m/%Y").strftime("%d/%m/%Y")
        except ValueError:
            raise ValueError("data_nascimento inválida — use o formato dd/mm/aaaa.")


class ReceitaCNPJIn(BaseModel):
    """Consulta de CNPJ na Receita Federal (receita-federal/cnpj).

    Parâmetro repassado à Infosimples: `cnpj` (14 dígitos).
    """
    cnpj: str = Field(description="CNPJ (14 dígitos, com ou sem máscara)")

    @field_validator("cnpj")
    @classmethod
    def _v_cnpj(cls, v: str) -> str:
        d = re.sub(r"\D", "", v or "")
        if not _cnpj_valido(d):
            raise ValueError("CNPJ inválido (dígitos verificadores não conferem).")
        return d


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _executar(db: AsyncSession, cu: User, caminho: str, parametros: dict) -> dict:
    try:
        return await infosimples_service.consultar(
            db, caminho, parametros,
            user_id=cu.id, user_role=getattr(cu.role, "value", str(cu.role)),
        )
    except (
        infosimples_service.IntegracaoDesligadaError,
        infosimples_service.LimiteDiarioAtingidoError,
        infosimples_service.InfosimplesConsultaError,
        infosimples_service.InfosimplesIndisponivelError,
    ) as e:
        status_code, detail = infosimples_service.http_status_para_erro(e)
        raise HTTPException(status_code=status_code, detail=detail)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/cpf", dependencies=[Depends(rate_limit("infosimples_receita", 10))],
)
async def consultar_cpf(
    body: ReceitaCPFIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_ADVOGADO_MAIS),
):
    """Situação cadastral de CPF na Receita Federal (consulta PAGA).

    Retorna nome oficial e situação cadastral normalizados + dados brutos ao
    chamador. Nada além do resumo mascarado é gravado no audit; o cache do
    dia evita cobrança dupla e é purgado automaticamente.
    """
    resultado = await _executar(
        db, cu, "receita-federal/cpf",
        {"cpf": body.cpf, "birthdate": body.data_nascimento},
    )
    dados = resultado.get("data") or []
    if not dados:
        raise HTTPException(
            status_code=404,
            detail="CPF não localizado na Receita Federal pela Infosimples "
                   "(confira o CPF e a data de nascimento).",
        )
    return {
        **infosimples_service.normalizar_receita_cpf(dados[0]),
        "cache": bool(resultado.get("cache")),
        "site_receipts": resultado.get("site_receipts") or [],
        "dados": dados[0],
    }


@router.post(
    "/cnpj", dependencies=[Depends(rate_limit("infosimples_receita", 10))],
)
async def consultar_cnpj(
    body: ReceitaCNPJIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_ADVOGADO_MAIS),
):
    """Situação cadastral de CNPJ na Receita Federal (consulta PAGA).

    Retorna razão social, nome fantasia e situação cadastral normalizados +
    dados brutos ao chamador (CNPJ é dado público de empresa).
    """
    resultado = await _executar(
        db, cu, "receita-federal/cnpj", {"cnpj": body.cnpj},
    )
    dados = resultado.get("data") or []
    if not dados:
        raise HTTPException(
            status_code=404,
            detail="CNPJ não localizado na Receita Federal pela Infosimples.",
        )
    return {
        **infosimples_service.normalizar_receita_cnpj(dados[0]),
        "cache": bool(resultado.get("cache")),
        "site_receipts": resultado.get("site_receipts") or [],
        "dados": dados[0],
    }
