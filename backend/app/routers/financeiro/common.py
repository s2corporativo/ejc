"""Visão financeira consolidada — tela única.

GET /api/v1/financeiro/consolidado?competencia=YYYY-MM
GET /api/v1/financeiro/atencao
GET /api/v1/financeiro/demonstrativo?competencia=YYYY-MM
GET /api/v1/financeiro/fechamento-inteligente?competencia=YYYY-MM

Princípio operacional: caixa usa pagamentos/baixas efetivas; competência usa
vencimento contratual dos honorários e a competência declarada das despesas.
O demonstrativo e o pré-fechamento são GERENCIAIS e não substituem escrituração,
DRE contábil ou validação fiscal pelo profissional responsável.
"""

# Namespace compartilhado pelos submódulos financeiros; alguns imports existem
# deliberadamente para reexportação explícita.
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fee import FeeTipo
from app.models.user import User


router = APIRouter(prefix="/financeiro", tags=["Financeiro Consolidado"])

_Q2 = Decimal("0.01")
_Q1 = Decimal("0.1")


def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(_Q2, ROUND_HALF_UP)


_suc = getattr(FeeTipo, "sucumbencia", None)
_SUCUMB = _suc.value if _suc is not None else "sucumbencia"
_GESTOR_FIN = {"superadmin", "admin", "socio", "financeiro"}


def _exigir_financeiro(cu: User) -> None:
    if cu.role.value not in _GESTOR_FIN:
        raise HTTPException(403, "Acesso restrito a gestão/financeiro")


_GESTOR_REGRAS = {"superadmin", "admin", "socio"}


class CommissionRuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=2, max_length=120)
    escopo: Literal["padrao", "area", "advogado", "caso"]
    percentual_advogado: Decimal = Field(ge=0, le=100)
    descontar_despesas: bool = True
    prioridade: int = Field(100, ge=0, le=10000)
    ativo: bool = True
    area: Optional[str] = Field(None, max_length=50)
    advogado_id: Optional[str] = Field(None, max_length=36)
    case_id: Optional[str] = Field(None, max_length=36)
    vigencia_inicio: date = Field(default_factory=date.today)
    vigencia_fim: Optional[date] = None

    @model_validator(mode="after")
    def validar_escopo(self):
        if self.vigencia_fim and self.vigencia_fim < self.vigencia_inicio:
            raise ValueError("vigência final não pode ser anterior à inicial")
        if self.escopo == "area" and not self.area:
            raise ValueError("regra por área exige area")
        if self.escopo == "advogado" and not self.advogado_id:
            raise ValueError("regra por advogado exige advogado_id")
        if self.escopo == "caso" and not self.case_id:
            raise ValueError("regra por caso exige case_id")
        return self


class CommissionRulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: Optional[str] = Field(None, min_length=2, max_length=120)
    percentual_advogado: Optional[Decimal] = Field(None, ge=0, le=100)
    descontar_despesas: Optional[bool] = None
    prioridade: Optional[int] = Field(None, ge=0, le=10000)
    ativo: Optional[bool] = None
    vigencia_fim: Optional[date] = None


class CommissionAdjustmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valor_advogado: Decimal
    valor_escritorio: Optional[Decimal] = None
    motivo: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def validar_valor(self):
        if self.valor_advogado == 0 and (self.valor_escritorio or Decimal("0")) == 0:
            raise ValueError("ajuste deve possuir valor diferente de zero")
        return self


class CommissionBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    withdrawal_ids: list[str] = Field(min_length=1, max_length=200)
    payment_method: Literal["pix", "transferencia", "ted", "dinheiro", "outro"]
    paid_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payment_reference: Optional[str] = Field(None, max_length=120)
    comprovante_doc_id: Optional[str] = Field(None, max_length=36)
    observacao: Optional[str] = Field(None, max_length=1000)


class CommissionCloseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    competencia: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class FinanceCloseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    competencia: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class FinancePolicyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    double_approval_threshold: Decimal = Field(ge=0, le=1000000000)


class ReconcileConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bank_transaction_id: str = Field(min_length=1, max_length=36)
    target_type: Literal["fee_payment", "office_expense", "commission_batch"]
    target_id: str = Field(min_length=1, max_length=36)


def _exigir_gestor_regras(cu: User) -> None:
    if cu.role.value not in _GESTOR_REGRAS:
        raise HTTPException(403, "Alteração de regras exige sócio ou administração")


def _competencia_atual(competencia: Optional[str]) -> str:
    if competencia:
        return competencia
    t = date.today()
    return f"{t.year}-{t.month:02d}"


def _month_bounds(competencia: str) -> tuple[date, date]:
    ano, mes = (int(v) for v in competencia.split("-"))
    inicio = date(ano, mes, 1)
    fim = date(ano + (1 if mes == 12 else 0), 1 if mes == 12 else mes + 1, 1)
    return inicio, fim




async def _commission_conference(db: AsyncSession, competencia: str) -> dict:
    inicio, fim = _month_bounds(competencia)

    sem_rateio = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) AS qtd, COALESCE(SUM(fp.valor), 0) AS valor
                FROM fee_payments fp
                JOIN fees f ON f.id=fp.fee_id
                LEFT JOIN case_receipt_allocations a ON a.fee_payment_id=fp.id
                WHERE fp.data_pagamento >= :inicio
                  AND fp.data_pagamento < :fim
                  AND f.deleted_at IS NULL
                  AND f.case_id IS NOT NULL
                  AND CAST(f.tipo AS text) <> 'custas_despesas'
                  AND a.id IS NULL
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).mappings().first()

    pendencias = (
        await db.execute(
            text(
                """
                WITH ajustes AS (
                    SELECT allocation_id, COALESCE(SUM(valor_advogado),0) AS total
                    FROM commission_adjustments
                    GROUP BY allocation_id
                )
                SELECT
                    SUM(CASE WHEN a.withdrawal_id IS NULL
                                  AND a.valor_advogado + COALESCE(aj.total,0) > 0
                             THEN 1 ELSE 0 END) AS calculadas,
                    SUM(CASE WHEN pw.status='pendente' THEN 1 ELSE 0 END) AS aprovar,
                    SUM(CASE WHEN pw.status='aprovado' THEN 1 ELSE 0 END) AS pagar
                FROM case_receipt_allocations a
                JOIN fee_payments fp ON fp.id=a.fee_payment_id
                LEFT JOIN ajustes aj ON aj.allocation_id=a.id
                LEFT JOIN partner_withdrawals pw
                  ON pw.id=a.withdrawal_id AND pw.deleted_at IS NULL
                WHERE fp.data_pagamento >= :inicio
                  AND fp.data_pagamento < :fim
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).mappings().first()

    ajustes = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) AS qtd,
                       COALESCE(SUM(ca.valor_advogado-ca.applied_value),0) AS valor
                FROM commission_adjustments ca
                WHERE ca.created_at >= :inicio
                  AND ca.created_at < :fim
                  AND ca.valor_advogado <> ca.applied_value
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).mappings().first()

    sem_comprovante = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) AS qtd
                FROM partner_withdrawals
                WHERE status='pago'
                  AND paid_at >= :inicio
                  AND paid_at < :fim
                  AND comprovante_doc_id IS NULL
                  AND deleted_at IS NULL
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).scalar() or 0

    itens: list[dict] = []
    if int(sem_rateio["qtd"] or 0):
        itens.append(
            {
                "codigo": "recebimentos_sem_rateio",
                "severidade": "bloqueio",
                "titulo": "Recebimentos sem comissão/rateio",
                "qtd": int(sem_rateio["qtd"] or 0),
                "valor": _money(sem_rateio["valor"]),
            }
        )
    for codigo, titulo, qtd in (
        ("comissoes_calculadas", "Comissões ainda não enviadas para aprovação", pendencias["calculadas"]),
        ("comissoes_aprovar", "Comissões aguardando aprovação", pendencias["aprovar"]),
        ("comissoes_pagar", "Comissões aprovadas ainda não pagas", pendencias["pagar"]),
    ):
        if int(qtd or 0):
            itens.append(
                {
                    "codigo": codigo,
                    "severidade": "bloqueio",
                    "titulo": titulo,
                    "qtd": int(qtd or 0),
                    "valor": None,
                }
            )
    if int(ajustes["qtd"] or 0):
        itens.append(
            {
                "codigo": "ajustes_pendentes",
                "severidade": "revisao",
                "titulo": "Ajustes aguardando compensação",
                "qtd": int(ajustes["qtd"] or 0),
                "valor": _money(ajustes["valor"]),
            }
        )
    if int(sem_comprovante):
        itens.append(
            {
                "codigo": "pagamentos_sem_comprovante",
                "severidade": "revisao",
                "titulo": "Pagamentos sem comprovante documental",
                "qtd": int(sem_comprovante),
                "valor": None,
            }
        )
    bloqueios = sum(1 for item in itens if item["severidade"] == "bloqueio")
    return {
        "competencia": competencia,
        "pronto": bloqueios == 0,
        "bloqueios": bloqueios,
        "itens": itens,
    }


async def _commission_statement(
    db: AsyncSession,
    competencia: str,
    advogado_id: str | None = None,
) -> dict:
    inicio, fim = _month_bounds(competencia)
    rows = (
        await db.execute(
            text(
                """
                WITH ajustes AS (
                    SELECT
                        allocation_id,
                        COALESCE(SUM(valor_advogado),0) AS adv,
                        COALESCE(SUM(valor_escritorio),0) AS esc,
                        COALESCE(SUM(valor_advogado-applied_value),0) AS pendente
                    FROM commission_adjustments
                    GROUP BY allocation_id
                )
                SELECT
                    a.id,
                    a.advogado_responsavel_id AS advogado_id,
                    u.full_name AS advogado,
                    c.titulo AS caso,
                    c.numero_interno,
                    COALESCE(cl.nome,cl.razao_social,'Cliente') AS cliente,
                    fp.data_pagamento,
                    a.bruto_recebido,
                    a.despesas_deduzidas,
                    a.base_liquida,
                    a.percentual_advogado,
                    a.valor_advogado + COALESCE(aj.adv,0) AS comissao_efetiva,
                    a.valor_escritorio + COALESCE(aj.esc,0) AS escritorio_efetivo,
                    COALESCE(aj.pendente,0) AS ajuste_pendente,
                    cr.nome AS regra,
                    cr.escopo AS regra_escopo,
                    pw.status AS pagamento_status,
                    pw.partner_share AS valor_pago,
                    pw.paid_at,
                    pw.payment_method,
                    pw.payment_reference,
                    pw.comprovante_doc_id
                FROM case_receipt_allocations a
                JOIN fee_payments fp ON fp.id=a.fee_payment_id
                JOIN fees f ON f.id=fp.fee_id
                JOIN cases c ON c.id=a.case_id
                LEFT JOIN clients cl ON cl.id=f.client_id AND cl.deleted_at IS NULL
                LEFT JOIN users u ON u.id=a.advogado_responsavel_id
                LEFT JOIN commission_rules cr ON cr.id=a.commission_rule_id
                LEFT JOIN partner_withdrawals pw
                  ON pw.id=a.withdrawal_id AND pw.deleted_at IS NULL
                LEFT JOIN ajustes aj ON aj.allocation_id=a.id
                WHERE fp.data_pagamento >= :inicio
                  AND fp.data_pagamento < :fim
                  AND (CAST(:advogado_id AS varchar) IS NULL OR a.advogado_responsavel_id=CAST(:advogado_id AS varchar))
                ORDER BY u.full_name, fp.data_pagamento, a.created_at
                """
            ),
            {"inicio": inicio, "fim": fim, "advogado_id": advogado_id},
        )
    ).mappings().all()
    data = [dict(r) for r in rows]

    resumo = {
        "recebido": _money(sum((Decimal(str(r["bruto_recebido"] or 0)) for r in data), Decimal("0"))),
        "despesas": _money(sum((Decimal(str(r["despesas_deduzidas"] or 0)) for r in data), Decimal("0"))),
        "comissoes": _money(sum((Decimal(str(r["comissao_efetiva"] or 0)) for r in data), Decimal("0"))),
        "escritorio": _money(sum((Decimal(str(r["escritorio_efetivo"] or 0)) for r in data), Decimal("0"))),
        "pago": _money(
            sum(
                (
                    Decimal(str(r["valor_pago"] or 0))
                    for r in data
                    if r["pagamento_status"] == "pago"
                ),
                Decimal("0"),
            )
        ),
        "ajustes_pendentes": _money(
            sum((Decimal(str(r["ajuste_pendente"] or 0)) for r in data), Decimal("0"))
        ),
    }

    grupos: dict[str, dict] = {}
    for r in data:
        aid = r.get("advogado_id") or "sem-responsavel"
        g = grupos.setdefault(
            aid,
            {
                "advogado_id": r.get("advogado_id"),
                "advogado": r.get("advogado") or "Sem responsável",
                "recebido": Decimal("0"),
                "comissoes": Decimal("0"),
                "pago": Decimal("0"),
                "saldo": Decimal("0"),
            },
        )
        g["recebido"] += Decimal(str(r["bruto_recebido"] or 0))
        comissao = Decimal(str(r["comissao_efetiva"] or 0))
        g["comissoes"] += comissao
        if r["pagamento_status"] == "pago":
            g["pago"] += Decimal(str(r["valor_pago"] or 0))
        else:
            g["saldo"] += max(comissao, Decimal("0"))

    por_advogado = [
        {
            **g,
            "recebido": _money(g["recebido"]),
            "comissoes": _money(g["comissoes"]),
            "pago": _money(g["pago"]),
            "saldo": _money(g["saldo"]),
        }
        for g in sorted(grupos.values(), key=lambda x: x["advogado"].casefold())
    ]
    return {
        "competencia": competencia,
        "advogado_id": advogado_id,
        "resumo": resumo,
        "por_advogado": por_advogado,
        "data": data,
    }
def _classificar_fechamento(itens: list[dict]) -> tuple[str, int]:
    """Classifica o pré-fechamento sem persistir decisão de negócio."""
    bloqueios = sum(1 for item in itens if item.get("severidade") == "bloqueio")
    revisoes = sum(1 for item in itens if item.get("severidade") == "revisao")
    score = max(0, 100 - (bloqueios * 25) - (revisoes * 7))
    if bloqueios:
        return "bloqueado", score
    if revisoes:
        return "revisao", score
    return "pronto", score



# Internal shared surface for the split finance routers.
__all__ = [name for name in globals() if not name.startswith("__")]
