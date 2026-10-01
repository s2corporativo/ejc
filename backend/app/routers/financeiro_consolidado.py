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
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.rate_limit import rate_limit
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.fee import CommissionRule, FeeTipo
from app.models.user import User
from app.services.fee_ledger_compat import LEDGER_COMPAT_CTES

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


@router.get("/consolidado", dependencies=[Depends(rate_limit("fin-consolidado", 60))])
async def consolidado(
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    competencia = _competencia_atual(competencia)
    mes_ref = date.fromisoformat(f"{competencia}-01")

    fees = (
        await db.execute(
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"""
                WITH {LEDGER_COMPAT_CTES},
                saldos AS (
                    SELECT
                        f.id,
                        CAST(f.tipo AS text) AS tipo,
                        f.descricao,
                        CAST(f.status AS text) AS status,
                        GREATEST(
                            COALESCE(f.valor, 0) - COALESCE(pe.total_pago, 0),
                            0
                        ) AS saldo
                    FROM fees f
                    LEFT JOIN pagamentos_efetivos pe ON pe.fee_id = f.id
                    WHERE f.deleted_at IS NULL
                ),
                pagamentos_mes AS (
                    SELECT
                        re.valor,
                        CAST(f.tipo AS text) AS tipo,
                        f.descricao
                    FROM recebimentos_efetivos re
                    JOIN fees f ON f.id = re.fee_id
                    WHERE f.deleted_at IS NULL
                      AND date_trunc('month', re.data_pagamento)
                          = date_trunc('month', CAST(:mes AS date))
                )
                SELECT
                    (SELECT COALESCE(SUM(valor), 0) FROM pagamentos_mes)
                        AS recebido_mes,
                    COALESCE(SUM(saldo) FILTER (WHERE status='pendente'), 0)
                        AS a_receber,
                    COALESCE(SUM(saldo) FILTER (WHERE status='atrasado'), 0)
                        AS atrasado,
                    (SELECT COALESCE(SUM(valor), 0) FROM pagamentos_mes
                        WHERE tipo IN ('fixo','misto','por_hora')
                          AND descricao NOT ILIKE '%sucumb%') AS rec_contratual,
                    (SELECT COALESCE(SUM(valor), 0) FROM pagamentos_mes
                        WHERE tipo='exito'
                          AND descricao NOT ILIKE '%sucumb%') AS rec_exito,
                    (SELECT COALESCE(SUM(valor), 0) FROM pagamentos_mes
                        WHERE tipo = '{_SUCUMB}' OR descricao ILIKE '%sucumb%')
                        AS rec_sucumbencia,
                    (SELECT COALESCE(SUM(valor), 0) FROM pagamentos_mes
                        WHERE tipo='custas_despesas') AS rec_custas,
                    COALESCE(SUM(saldo) FILTER (
                        WHERE status IN ('pendente','atrasado')
                          AND tipo IN ('fixo','misto','por_hora')
                          AND descricao NOT ILIKE '%sucumb%'
                    ), 0) AS prev_contratual,
                    COALESCE(SUM(saldo) FILTER (
                        WHERE status IN ('pendente','atrasado')
                          AND tipo='exito'
                          AND descricao NOT ILIKE '%sucumb%'
                    ), 0) AS prev_exito,
                    COALESCE(SUM(saldo) FILTER (
                        WHERE status IN ('pendente','atrasado')
                          AND (tipo = '{_SUCUMB}' OR descricao ILIKE '%sucumb%')
                    ), 0) AS prev_sucumbencia,
                    COALESCE(SUM(saldo) FILTER (
                        WHERE status IN ('pendente','atrasado')
                          AND tipo='custas_despesas'
                    ), 0) AS prev_custas,
                    (
                        SELECT COUNT(*)
                        FROM fees f2
                        WHERE f2.deleted_at IS NULL
                          AND f2.valor IS NULL
                          AND f2.percentual_exito IS NOT NULL
                          AND CAST(f2.status AS text) IN ('pendente','atrasado')
                    ) AS percentuais_sem_valor
                FROM saldos
                """
            ),
            {"mes": mes_ref},
        )
    ).mappings().first()
    bruto = dict(fees)
    percentuais_sem_valor = int(bruto.pop("percentuais_sem_valor") or 0)
    fees = {k: _money(v) for k, v in bruto.items()}

    desp = (
        await db.execute(
            text(
                """
                SELECT
                  COALESCE(SUM(valor) FILTER (WHERE status='pago'), 0) AS pago,
                  COALESCE(SUM(valor) FILTER (WHERE status='pendente'), 0) AS a_pagar,
                  COALESCE(SUM(valor) FILTER (
                      WHERE tipo='fixo' AND status!='cancelado'
                  ), 0) AS fixo,
                  COALESCE(SUM(valor) FILTER (
                      WHERE tipo='variavel' AND status!='cancelado'
                  ), 0) AS variavel
                FROM office_expenses
                WHERE deleted_at IS NULL AND competencia = :comp
                """
            ),
            {"comp": competencia},
        )
    ).mappings().first()
    desp = {k: _money(v) for k, v in dict(desp).items()}

    saidas_caixa_mes = _money(
        (
            await db.execute(
                text(
                    """
                    SELECT COALESCE(SUM(valor), 0)
                    FROM office_expenses
                    WHERE deleted_at IS NULL
                      AND status = 'pago'
                      AND pago_em IS NOT NULL
                      AND date_trunc('month', pago_em)
                          = date_trunc('month', CAST(:mes AS date))
                    """
                ),
                {"mes": mes_ref},
            )
        ).scalar()
    )

    por_cat = (
        await db.execute(
            text(
                """
                SELECT categoria, COALESCE(SUM(valor),0) AS total, COUNT(*) AS qtd
                FROM office_expenses
                WHERE deleted_at IS NULL
                  AND status != 'cancelado'
                  AND competencia = :comp
                GROUP BY categoria ORDER BY total DESC
                """
            ),
            {"comp": competencia},
        )
    ).mappings().all()
    por_categoria = [
        {
            "categoria": r["categoria"],
            "total": _money(r["total"]),
            "qtd": int(r["qtd"]),
        }
        for r in por_cat
    ]

    recebido = fees["recebido_mes"]
    despesas_pagas_competencia = desp["pago"]
    caixa = _money(recebido - saidas_caixa_mes)
    margem = (
        (caixa / recebido * 100).quantize(_Q1, ROUND_HALF_UP)
        if recebido
        else Decimal("0")
    )

    return {
        "competencia": competencia,
        "caixa_periodo": caixa,
        "margem_pct": margem,
        "fluxo_caixa": {
            "entradas": recebido,
            "saidas": saidas_caixa_mes,
            "saldo_periodo": caixa,
        },
        "receitas": {
            "recebido_mes": recebido,
            "a_receber": fees["a_receber"],
            "atrasado": fees["atrasado"],
            "contratual": fees["rec_contratual"],
            "exito": fees["rec_exito"],
            "sucumbencia": fees["rec_sucumbencia"],
            "custas": fees["rec_custas"],
            "percentuais_sem_valor": percentuais_sem_valor,
            "previsto": {
                "contratual": fees["prev_contratual"],
                "exito": fees["prev_exito"],
                "sucumbencia": fees["prev_sucumbencia"],
                "custas": fees["prev_custas"],
                "total": _money(
                    fees["prev_contratual"]
                    + fees["prev_exito"]
                    + fees["prev_sucumbencia"]
                    + fees["prev_custas"]
                ),
            },
        },
        "despesas": {
            "pagas": despesas_pagas_competencia,
            "saidas_caixa_mes": saidas_caixa_mes,
            "a_pagar": desp["a_pagar"],
            "fixo": desp["fixo"],
            "variavel": desp["variavel"],
            "por_categoria": por_categoria,
        },
    }


@router.get("/atencao", dependencies=[Depends(rate_limit("fin-atencao", 60))])
async def pendencias_operacionais(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Fila curta do que exige decisão financeira sem expor PII no resumo."""
    _exigir_financeiro(cu)
    hoje = date.today()
    em_7_dias = hoje + timedelta(days=7)
    ha_30_dias = hoje - timedelta(days=30)

    hon = (
        await db.execute(
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"""
                WITH {LEDGER_COMPAT_CTES}
                SELECT COUNT(*) AS qtd,
                       COALESCE(SUM(GREATEST(f.valor - COALESCE(pe.total_pago, 0), 0)), 0) AS total
                FROM fees f
                LEFT JOIN pagamentos_efetivos pe ON pe.fee_id = f.id
                WHERE f.deleted_at IS NULL
                  AND f.valor IS NOT NULL
                  AND CAST(f.status AS text) IN ('pendente','atrasado')
                  AND f.data_vencimento < :hoje
                  AND GREATEST(f.valor - COALESCE(pe.total_pago, 0), 0) > 0
                """
            ),
            {"hoje": hoje},
        )
    ).mappings().first()

    despesas = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE vencimento < :hoje) AS vencidas_qtd,
                    COALESCE(SUM(valor) FILTER (WHERE vencimento < :hoje), 0) AS vencidas_total,
                    COUNT(*) FILTER (
                        WHERE vencimento >= :hoje AND vencimento <= :limite
                    ) AS proximas_qtd,
                    COALESCE(SUM(valor) FILTER (
                        WHERE vencimento >= :hoje AND vencimento <= :limite
                    ), 0) AS proximas_total
                FROM office_expenses
                WHERE deleted_at IS NULL
                  AND status = 'pendente'
                  AND vencimento IS NOT NULL
                """
            ),
            {"hoje": hoje, "limite": em_7_dias},
        )
    ).mappings().first()

    sem_comprovante = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) AS qtd, COALESCE(SUM(fp.valor), 0) AS total
                FROM fee_payments fp
                JOIN fees f ON f.id = fp.fee_id
                WHERE f.deleted_at IS NULL
                  AND fp.comprovante_doc_id IS NULL
                  AND fp.data_pagamento >= :inicio
                """
            ),
            {"inicio": ha_30_dias},
        )
    ).mappings().first()

    percentuais_sem_base = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fees
                WHERE deleted_at IS NULL
                  AND valor IS NULL
                  AND percentual_exito IS NOT NULL
                  AND CAST(status AS text) IN ('pendente','atrasado')
                """
            )
        )
    ).scalar() or 0

    contratos = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM office_contracts
                WHERE deleted_at IS NULL
                  AND status = 'vigente'
                  AND end_date IS NOT NULL
                  AND end_date >= CURRENT_DATE
                  AND end_date <= CURRENT_DATE
                        + make_interval(days => COALESCE(alert_days_before, 30))
                """
            )
        )
    ).scalar() or 0

    itens = []
    if int(hon["qtd"] or 0):
        itens.append({
            "codigo": "honorarios_vencidos",
            "prioridade": "alta",
            "titulo": "Honorários vencidos",
            "qtd": int(hon["qtd"] or 0),
            "valor": _money(hon["total"]),
            # Sem filtro de status: o card conta pendentes vencidos E atrasados.
            "acao": {"tab": "honorarios"},
        })
    if int(despesas["vencidas_qtd"] or 0):
        itens.append({
            "codigo": "despesas_vencidas",
            "prioridade": "alta",
            "titulo": "Despesas vencidas",
            "qtd": int(despesas["vencidas_qtd"] or 0),
            "valor": _money(despesas["vencidas_total"]),
            "acao": {"tab": "despesas", "status": "pendente"},
        })
    if int(despesas["proximas_qtd"] or 0):
        itens.append({
            "codigo": "despesas_proximas",
            "prioridade": "media",
            "titulo": "Despesas vencem nos próximos 7 dias",
            "qtd": int(despesas["proximas_qtd"] or 0),
            "valor": _money(despesas["proximas_total"]),
            "acao": {"tab": "despesas", "status": "pendente"},
        })
    if int(sem_comprovante["qtd"] or 0):
        itens.append({
            "codigo": "pagamentos_sem_comprovante",
            "prioridade": "baixa",
            "titulo": "Pagamentos sem comprovante nos últimos 30 dias",
            "qtd": int(sem_comprovante["qtd"] or 0),
            "valor": _money(sem_comprovante["total"]),
            "acao": {"tab": "honorarios"},
        })
    if int(percentuais_sem_base):
        itens.append({
            "codigo": "percentuais_sem_base",
            "prioridade": "media",
            "titulo": "Honorários percentuais sem base monetária",
            "qtd": int(percentuais_sem_base),
            "valor": None,
            "acao": {"tab": "honorarios"},
        })
    if int(contratos):
        itens.append({
            "codigo": "contratos_vencendo",
            "prioridade": "media",
            "titulo": "Contratos dentro da janela individual de alerta",
            "qtd": int(contratos),
            "valor": None,
            "acao": {"tab": "contratos"},
        })

    ordem = {"alta": 0, "media": 1, "baixa": 2}
    itens.sort(key=lambda item: ordem[item["prioridade"]])
    return {"gerado_em": hoje.isoformat(), "total": len(itens), "itens": itens}


@router.get("/demonstrativo", dependencies=[Depends(rate_limit("fin-demonstrativo", 30))])
async def demonstrativo_gerencial(
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Separa competência operacional de fluxo de caixa."""
    _exigir_financeiro(cu)
    competencia = _competencia_atual(competencia)
    mes_ref = date.fromisoformat(f"{competencia}-01")

    rec = (
        await db.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(valor) FILTER (
                        WHERE valor IS NOT NULL AND status != 'cancelado'
                    ), 0) AS receitas_competencia,
                    COUNT(*) FILTER (
                        WHERE valor IS NULL AND percentual_exito IS NOT NULL
                          AND status != 'cancelado'
                    ) AS percentuais_sem_base
                FROM fees
                WHERE deleted_at IS NULL
                  AND date_trunc('month', data_vencimento)
                      = date_trunc('month', CAST(:mes AS date))
                """
            ),
            {"mes": mes_ref},
        )
    ).mappings().first()

    despesas_comp = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(valor), 0)
                FROM office_expenses
                WHERE deleted_at IS NULL
                  AND status != 'cancelado'
                  AND competencia = :comp
                """
            ),
            {"comp": competencia},
        )
    ).scalar()

    entradas_caixa = (
        await db.execute(
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"""
                WITH {LEDGER_COMPAT_CTES}
                SELECT COALESCE(SUM(re.valor), 0)
                FROM recebimentos_efetivos re
                JOIN fees f ON f.id = re.fee_id
                WHERE f.deleted_at IS NULL
                  AND date_trunc('month', re.data_pagamento)
                      = date_trunc('month', CAST(:mes AS date))
                """
            ),
            {"mes": mes_ref},
        )
    ).scalar()

    saidas_caixa = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(valor), 0)
                FROM office_expenses
                WHERE deleted_at IS NULL
                  AND status = 'pago'
                  AND pago_em IS NOT NULL
                  AND date_trunc('month', pago_em)
                      = date_trunc('month', CAST(:mes AS date))
                """
            ),
            {"mes": mes_ref},
        )
    ).scalar()

    receitas_comp = _money(rec["receitas_competencia"])
    despesas_comp = _money(despesas_comp)
    entradas_caixa = _money(entradas_caixa)
    saidas_caixa = _money(saidas_caixa)

    return {
        "competencia": competencia,
        "natureza": "gerencial_nao_contabil",
        "criterios": {
            "receita_competencia": "mês de data_vencimento do honorário",
            "despesa_competencia": "office_expenses.competencia",
            "entrada_caixa": "fee_payments.data_pagamento; fallback legado não duplicante",
            "saida_caixa": "office_expenses.pago_em",
        },
        "competencia_operacional": {
            "receitas": receitas_comp,
            "despesas": despesas_comp,
            "resultado": _money(receitas_comp - despesas_comp),
            "percentuais_sem_base_monetaria": int(rec["percentuais_sem_base"] or 0),
        },
        "fluxo_caixa": {
            "entradas": entradas_caixa,
            "saidas": saidas_caixa,
            "saldo_periodo": _money(entradas_caixa - saidas_caixa),
        },
        "aviso": (
            "Demonstrativo gerencial do EJC. Não substitui escrituração, DRE ou "
            "validação contábil/fiscal pelo profissional responsável."
        ),
    }



@router.get("/operacional", dependencies=[Depends(rate_limit("fin-operacional", 60))])
async def painel_operacional(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    hoje = date.today()
    limite = hoje + timedelta(days=30)
    # SQL composto apenas por CTE constante e bind params; sem entrada estrutural do usuário.
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    recebiveis=(await db.execute(text(f"""
        WITH {LEDGER_COMPAT_CTES}
        SELECT f.id,f.descricao,f.data_vencimento,
          GREATEST(COALESCE(f.valor,0)-COALESCE(pe.total_pago,0),0) AS saldo,
          f.client_id,f.case_id,COALESCE(cl.nome,cl.razao_social,'Cliente') AS cliente,
          c.titulo AS caso
        FROM fees f
        LEFT JOIN pagamentos_efetivos pe ON pe.fee_id=f.id
        LEFT JOIN clients cl ON cl.id=f.client_id AND cl.deleted_at IS NULL
        LEFT JOIN cases c ON c.id=f.case_id AND c.deleted_at IS NULL
        WHERE f.deleted_at IS NULL
          AND CAST(f.status AS text) IN ('pendente','atrasado')
          AND f.valor IS NOT NULL
          AND f.data_vencimento BETWEEN :hoje AND :limite
          AND GREATEST(COALESCE(f.valor,0)-COALESCE(pe.total_pago,0),0)>0
        ORDER BY f.data_vencimento,f.id LIMIT 8
    """),{"hoje":hoje,"limite":limite})).mappings().all()
    pagamentos=(await db.execute(text("""
        SELECT id,descricao,valor,vencimento,categoria
        FROM office_expenses
        WHERE deleted_at IS NULL AND status='pendente'
          AND vencimento BETWEEN :hoje AND :limite
        ORDER BY vencimento,id LIMIT 8
    """),{"hoje":hoje,"limite":limite})).mappings().all()
    # SQL composto apenas por CTE constante e bind params; sem entrada estrutural do usuário.
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    inad=(await db.execute(text(f"""
        WITH {LEDGER_COMPAT_CTES}
        SELECT COUNT(DISTINCT f.client_id) AS clientes,COUNT(*) AS titulos,
          COALESCE(SUM(GREATEST(COALESCE(f.valor,0)-COALESCE(pe.total_pago,0),0)),0) AS valor
        FROM fees f LEFT JOIN pagamentos_efetivos pe ON pe.fee_id=f.id
        WHERE f.deleted_at IS NULL
          AND CAST(f.status AS text) IN ('pendente','atrasado')
          AND f.valor IS NOT NULL AND f.data_vencimento < :hoje
          AND GREATEST(COALESCE(f.valor,0)-COALESCE(pe.total_pago,0),0)>0
    """),{"hoje":hoje})).mappings().first()
    # SQL composto apenas por CTE constante e bind params; sem entrada estrutural do usuário.
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    totais=(await db.execute(text(f"""
        WITH {LEDGER_COMPAT_CTES},
        entradas AS (
          SELECT COALESCE(SUM(GREATEST(COALESCE(f.valor,0)-COALESCE(pe.total_pago,0),0)),0) total
          FROM fees f LEFT JOIN pagamentos_efetivos pe ON pe.fee_id=f.id
          WHERE f.deleted_at IS NULL AND CAST(f.status AS text) IN ('pendente','atrasado')
            AND f.valor IS NOT NULL AND f.data_vencimento BETWEEN :hoje AND :limite
        ),
        saidas AS (
          SELECT COALESCE(SUM(valor),0) total FROM office_expenses
          WHERE deleted_at IS NULL AND status='pendente' AND vencimento BETWEEN :hoje AND :limite
        )
        SELECT (SELECT total FROM entradas) entradas,(SELECT total FROM saidas) saidas
    """),{"hoje":hoje,"limite":limite})).mappings().first()
    # SQL composto apenas por CTE constante e bind params; sem entrada estrutural do usuário.
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    mov=(await db.execute(text(f"""
        WITH {LEDGER_COMPAT_CTES}, mov AS (
          SELECT 'entrada'::text natureza,re.data_pagamento data,f.descricao,re.valor,
                 f.id referencia_id,f.client_id,f.case_id,
                 COALESCE(cl.nome,cl.razao_social,'Cliente') cliente,c.titulo caso
          FROM recebimentos_efetivos re JOIN fees f ON f.id=re.fee_id
          LEFT JOIN clients cl ON cl.id=f.client_id AND cl.deleted_at IS NULL
          LEFT JOIN cases c ON c.id=f.case_id AND c.deleted_at IS NULL
          WHERE f.deleted_at IS NULL
          UNION ALL
          SELECT 'saida',oe.pago_em,oe.descricao,oe.valor,oe.id,NULL,NULL,NULL,NULL
          FROM office_expenses oe
          WHERE oe.deleted_at IS NULL AND oe.status='pago' AND oe.pago_em IS NOT NULL
        )
        SELECT * FROM mov WHERE data IS NOT NULL ORDER BY data DESC,referencia_id DESC LIMIT 12
    """))).mappings().all()
    e=_money(totais["entradas"]); sai=_money(totais["saidas"])
    return {
      "proximos_30_dias":{"entradas":e,"saidas":sai,"saldo":_money(e-sai)},
      "inadimplencia":{"clientes":int(inad["clientes"] or 0),"titulos":int(inad["titulos"] or 0),"valor":_money(inad["valor"])},
      "proximos_recebimentos":[{"id":r["id"],"descricao":r["descricao"],"vencimento":r["data_vencimento"],"valor":_money(r["saldo"]),"client_id":r["client_id"],"case_id":r["case_id"],"cliente":r["cliente"],"caso":r["caso"]} for r in recebiveis],
      "proximos_pagamentos":[{"id":r["id"],"descricao":r["descricao"],"vencimento":r["vencimento"],"valor":_money(r["valor"]),"categoria":r["categoria"]} for r in pagamentos],
      "movimentacoes_recentes":[{"natureza":r["natureza"],"data":r["data"],"descricao":r["descricao"],"valor":_money(r["valor"]),"referencia_id":r["referencia_id"],"client_id":r["client_id"],"case_id":r["case_id"],"cliente":r["cliente"],"caso":r["caso"]} for r in mov],
    }




@router.get("/politica")
async def politica_financeira(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    row = (
        await db.execute(
            text(
                """
                SELECT id,double_approval_threshold,updated_by,created_at,updated_at
                FROM finance_policy_settings
                WHERE id='default'
                """
            )
        )
    ).mappings().first()
    return dict(row) if row else {"id": "default", "double_approval_threshold": 10000}


@router.patch("/politica")
async def atualizar_politica_financeira(
    body: FinancePolicyPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_gestor_regras(cu)
    antes = (
        await db.execute(
            text(
                """
                SELECT double_approval_threshold
                FROM finance_policy_settings
                WHERE id='default'
                FOR UPDATE
                """
            )
        )
    ).scalar_one_or_none()
    await db.execute(
        text(
            """
            INSERT INTO finance_policy_settings
                (id,double_approval_threshold,updated_by,created_at,updated_at)
            VALUES
                ('default',:limite,:uid,NOW(),NOW())
            ON CONFLICT (id) DO UPDATE
            SET double_approval_threshold=EXCLUDED.double_approval_threshold,
                updated_by=EXCLUDED.updated_by,
                updated_at=NOW()
            """
        ),
        {"limite": body.double_approval_threshold, "uid": cu.id},
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "UPDATE",
        "finance_policy_settings",
        "default",
        detalhes="Alçada financeira atualizada.",
        dados_antes={"double_approval_threshold": str(antes or 0)},
        dados_depois={
            "double_approval_threshold": str(body.double_approval_threshold)
        },
    )
    await db.commit()
    return {
        "id": "default",
        "double_approval_threshold": body.double_approval_threshold,
    }


@router.get("/aprovacoes")
async def listar_aprovacoes_financeiras(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    rows = (
        await db.execute(
            text(
                """
                SELECT a.*, req.full_name AS solicitado_por_nome,
                       apr.full_name AS aprovado_por_nome
                FROM finance_payment_approvals a
                LEFT JOIN users req ON req.id=a.requested_by
                LEFT JOIN users apr ON apr.id=a.approved_by
                WHERE (CAST(:status AS text) IS NULL OR a.status=:status)
                ORDER BY a.requested_at DESC
                LIMIT 300
                """
            ),
            {"status": status},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


@router.post("/aprovacoes/{approval_id}/aprovar")
async def aprovar_pagamento_financeiro(
    approval_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_gestor_regras(cu)
    from app.models.audit_log import criar_audit_log
    from app.services.finance_governance import aprovar_solicitacao

    resultado = await aprovar_solicitacao(db, approval_id, cu)
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "APPROVE",
        "finance_payment_approvals",
        approval_id,
        detalhes="Segunda aprovação financeira concedida.",
        dados_depois={
            "entity_type": resultado["entity_type"],
            "entity_id": resultado["entity_id"],
            "amount": str(resultado["amount"]),
        },
    )
    await db.commit()
    return resultado


@router.get("/rentabilidade")
async def rentabilidade_financeira(
    competencia: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    inicio, fim = _month_bounds(competencia)
    rows = (
        await db.execute(
            text(
                """
                WITH caixa AS (
                    SELECT f.case_id, SUM(fp.valor) AS recebido
                    FROM fee_payments fp
                    JOIN fees f ON f.id=fp.fee_id
                    WHERE f.deleted_at IS NULL
                      AND f.case_id IS NOT NULL
                      AND fp.data_pagamento >= :inicio
                      AND fp.data_pagamento < :fim
                    GROUP BY f.case_id
                ),
                estornos AS (
                    SELECT f.case_id, SUM(fe.valor) AS valor
                    FROM fee_estornos fe
                    JOIN fees f ON f.id=fe.fee_id
                    WHERE f.deleted_at IS NULL
                      AND f.case_id IS NOT NULL
                      AND fe.data_estorno >= :inicio
                      AND fe.data_estorno < :fim
                    GROUP BY f.case_id
                ),
                despesas AS (
                    SELECT case_id, SUM(valor) AS valor
                    FROM centro_custos
                    WHERE deleted_at IS NULL
                      AND CAST(tipo AS text)='despesa'
                      AND pago=TRUE
                      AND COALESCE(data_pagamento,data_lancamento) >= :inicio
                      AND COALESCE(data_pagamento,data_lancamento) < :fim
                    GROUP BY case_id
                ),
                comissoes AS (
                    SELECT a.case_id, SUM(a.valor_advogado) AS valor
                    FROM case_receipt_allocations a
                    JOIN fee_payments fp ON fp.id=a.fee_payment_id
                    WHERE fp.data_pagamento >= :inicio
                      AND fp.data_pagamento < :fim
                    GROUP BY a.case_id
                ),
                ajustes AS (
                    SELECT a.case_id, SUM(ca.valor_advogado) AS valor
                    FROM commission_adjustments ca
                    JOIN case_receipt_allocations a ON a.id=ca.allocation_id
                    WHERE ca.created_at >= :inicio
                      AND ca.created_at < :fim
                    GROUP BY a.case_id
                )
                SELECT
                    c.id AS case_id,
                    c.client_id,
                    c.numero_interno,
                    c.titulo AS caso,
                    COALESCE(cl.nome,cl.razao_social,'Cliente') AS cliente,
                    COALESCE(cx.recebido,0)-COALESCE(es.valor,0) AS recebido,
                    COALESCE(dp.valor,0) AS despesas,
                    COALESCE(cm.valor,0)+COALESCE(aj.valor,0) AS comissoes,
                    COALESCE(cx.recebido,0)-COALESCE(es.valor,0)
                      -COALESCE(dp.valor,0)
                      -COALESCE(cm.valor,0)-COALESCE(aj.valor,0) AS resultado
                FROM cases c
                LEFT JOIN clients cl ON cl.id=c.client_id AND cl.deleted_at IS NULL
                LEFT JOIN caixa cx ON cx.case_id=c.id
                LEFT JOIN estornos es ON es.case_id=c.id
                LEFT JOIN despesas dp ON dp.case_id=c.id
                LEFT JOIN comissoes cm ON cm.case_id=c.id
                LEFT JOIN ajustes aj ON aj.case_id=c.id
                WHERE c.deleted_at IS NULL
                  AND (
                    COALESCE(cx.recebido,0)<>0
                    OR COALESCE(es.valor,0)<>0
                    OR COALESCE(dp.valor,0)<>0
                    OR COALESCE(cm.valor,0)<>0
                    OR COALESCE(aj.valor,0)<>0
                  )
                ORDER BY resultado DESC,c.numero_interno
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).mappings().all()
    casos = [dict(r) for r in rows]
    clientes: dict[str, dict] = {}
    for row in casos:
        key = row["client_id"] or "sem-cliente"
        item = clientes.setdefault(
            key,
            {
                "client_id": row["client_id"],
                "cliente": row["cliente"],
                "recebido": Decimal("0"),
                "despesas": Decimal("0"),
                "comissoes": Decimal("0"),
                "resultado": Decimal("0"),
                "casos": 0,
            },
        )
        for campo in ("recebido", "despesas", "comissoes", "resultado"):
            item[campo] += Decimal(str(row[campo] or 0))
        item["casos"] += 1
    clientes_out = [
        {
            **item,
            "recebido": _money(item["recebido"]),
            "despesas": _money(item["despesas"]),
            "comissoes": _money(item["comissoes"]),
            "resultado": _money(item["resultado"]),
        }
        for item in sorted(
            clientes.values(),
            key=lambda x: x["resultado"],
            reverse=True,
        )
    ]
    total_recebido = _money(
        sum((Decimal(str(r["recebido"] or 0)) for r in casos), Decimal("0"))
    )
    total_despesas = _money(
        sum((Decimal(str(r["despesas"] or 0)) for r in casos), Decimal("0"))
    )
    total_comissoes = _money(
        sum((Decimal(str(r["comissoes"] or 0)) for r in casos), Decimal("0"))
    )
    resultado_casos = _money(
        sum((Decimal(str(r["resultado"] or 0)) for r in casos), Decimal("0"))
    )
    despesas_escritorio = _money(
        (
            await db.execute(
                text(
                    """
                    SELECT COALESCE(SUM(valor),0)
                    FROM office_expenses
                    WHERE deleted_at IS NULL
                      AND status='pago'
                      AND pago_em >= :inicio
                      AND pago_em < :fim
                    """
                ),
                {"inicio": inicio, "fim": fim},
            )
        ).scalar()
    )
    total_resultado = _money(resultado_casos - despesas_escritorio)
    return {
        "competencia": competencia,
        "resumo": {
            "recebido": total_recebido,
            "despesas_casos": total_despesas,
            "comissoes": total_comissoes,
            "resultado_casos": resultado_casos,
            "despesas_escritorio": despesas_escritorio,
            "resultado_escritorio": total_resultado,
        },
        "casos": casos,
        "clientes": clientes_out,
    }


@router.get("/distribuicao-disponivel")
async def distribuicao_disponivel(
    competencia: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    from app.services.finance_governance import resultado_disponivel_distribuicao

    return await resultado_disponivel_distribuicao(db, competencia)


@router.get("/fechamentos/{competencia}")
async def obter_fechamento_financeiro(
    competencia: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    if not __import__("re").fullmatch(r"\d{4}-(0[1-9]|1[0-2])", competencia):
        raise HTTPException(422, "competencia inválida: use AAAA-MM")
    row = (
        await db.execute(
            text(
                """
                SELECT id,competencia,snapshot_json,closed_by,closed_at,created_at
                FROM finance_month_closings
                WHERE competencia=:competencia
                """
            ),
            {"competencia": competencia},
        )
    ).mappings().first()
    return dict(row) if row else {"competencia": competencia, "fechado": False}


@router.post("/fechamentos", status_code=201)
async def fechar_competencia_financeira(
    body: FinanceCloseIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_gestor_regras(cu)
    existente = (
        await db.execute(
            text(
                "SELECT id FROM finance_month_closings WHERE competencia=:c"
            ),
            {"c": body.competencia},
        )
    ).scalar_one_or_none()
    if existente:
        raise HTTPException(409, "Competência financeira já está fechada")

    pre = await fechamento_inteligente(body.competencia, db, cu)
    if pre.get("total_bloqueios", 0) > 0:
        raise HTTPException(
            409,
            detail={
                "message": "Fechamento bloqueado por inconsistências financeiras",
                "bloqueios": pre.get("bloqueios", []),
            },
        )
    rent = await rentabilidade_financeira(body.competencia, db, cu)
    snapshot = {
        "pre_fechamento": pre,
        "rentabilidade": rent,
        "demonstrativo": pre.get("snapshot"),
    }
    cid = str(uuid4())
    agora = datetime.now(timezone.utc)
    await db.execute(
        text(
            """
            INSERT INTO finance_month_closings
                (id,competencia,snapshot_json,closed_by,closed_at,created_at)
            VALUES
                (:id,:competencia,CAST(:snapshot AS jsonb),:closed_by,:closed_at,NOW())
            """
        ),
        {
            "id": cid,
            "competencia": body.competencia,
            "snapshot": json.dumps(snapshot, default=str, ensure_ascii=False),
            "closed_by": cu.id,
            "closed_at": agora,
        },
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CLOSE",
        "finance_month_closings",
        cid,
        detalhes=f"Competência financeira {body.competencia} fechada.",
        dados_depois={"competencia": body.competencia},
    )
    await db.commit()
    return {
        "id": cid,
        "competencia": body.competencia,
        "closed_at": agora,
        "snapshot": snapshot,
    }


@router.get("/excecoes")
async def excecoes_financeiras(
    competencia: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    inicio, fim = _month_bounds(competencia)
    itens: list[dict] = []

    duplicados = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT client_id,COALESCE(case_id,''),descricao,valor,data_vencimento
                    FROM fees
                    WHERE deleted_at IS NULL
                      AND CAST(status AS text) <> 'cancelado'
                    GROUP BY client_id,COALESCE(case_id,''),descricao,valor,data_vencimento
                    HAVING COUNT(*) > 1
                ) x
                """
            )
        )
    ).scalar() or 0
    if duplicados:
        itens.append(
            {
                "codigo": "possiveis_duplicidades",
                "titulo": "Possíveis honorários duplicados",
                "qtd": int(duplicados),
                "severidade": "revisao",
            }
        )

    sem_caso = (
        await db.execute(
            text(
                """
                SELECT COUNT(*),COALESCE(SUM(fp.valor),0)
                FROM fee_payments fp
                JOIN fees f ON f.id=fp.fee_id
                WHERE f.deleted_at IS NULL
                  AND f.case_id IS NULL
                  AND fp.data_pagamento >= :inicio
                  AND fp.data_pagamento < :fim
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).first()
    if sem_caso and int(sem_caso[0] or 0):
        itens.append(
            {
                "codigo": "recebimentos_sem_caso",
                "titulo": "Recebimentos sem caso vinculado",
                "qtd": int(sem_caso[0] or 0),
                "valor": _money(sem_caso[1]),
                "severidade": "revisao",
            }
        )

    sem_comprovante = (
        await db.execute(
            text(
                """
                SELECT COUNT(*),COALESCE(SUM(partner_share),0)
                FROM partner_withdrawals
                WHERE deleted_at IS NULL
                  AND status='pago'
                  AND paid_at >= :inicio
                  AND paid_at < :fim
                  AND comprovante_doc_id IS NULL
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).first()
    if sem_comprovante and int(sem_comprovante[0] or 0):
        itens.append(
            {
                "codigo": "comissoes_sem_comprovante",
                "titulo": "Comissões pagas sem comprovante",
                "qtd": int(sem_comprovante[0] or 0),
                "valor": _money(sem_comprovante[1]),
                "severidade": "revisao",
            }
        )

    sem_responsavel = (
        await db.execute(
            text(
                """
                SELECT COUNT(*),COALESCE(SUM(fp.valor),0)
                FROM fee_payments fp
                JOIN fees f ON f.id=fp.fee_id
                JOIN cases c ON c.id=f.case_id AND c.deleted_at IS NULL
                LEFT JOIN case_receipt_allocations a ON a.fee_payment_id=fp.id
                WHERE f.deleted_at IS NULL
                  AND c.advogado_responsavel_id IS NULL
                  AND a.id IS NULL
                  AND fp.data_pagamento >= :inicio
                  AND fp.data_pagamento < :fim
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).first()
    if sem_responsavel and int(sem_responsavel[0] or 0):
        itens.append(
            {
                "codigo": "comissoes_sem_responsavel",
                "titulo": "Recebimentos sem responsável para comissão",
                "qtd": int(sem_responsavel[0] or 0),
                "valor": _money(sem_responsavel[1]),
                "severidade": "bloqueio",
            }
        )

    recon_pendente = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM bank_transactions bt
                JOIN bank_analyses ba ON ba.id=bt.analysis_id
                WHERE ba.deleted_at IS NULL
                  AND bt.data >= :inicio
                  AND bt.data < :fim
                  AND NOT EXISTS (
                    SELECT 1 FROM finance_reconciliation_matches rm
                    WHERE rm.bank_transaction_id=bt.id
                      AND rm.status='confirmado'
                  )
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).scalar() or 0
    if recon_pendente:
        itens.append(
            {
                "codigo": "extrato_nao_conciliado",
                "titulo": "Movimentos bancários ainda não conciliados",
                "qtd": int(recon_pendente),
                "severidade": "revisao",
            }
        )

    rent = await rentabilidade_financeira(competencia, db, cu)
    if Decimal(str(rent["resumo"]["resultado_escritorio"])) < 0:
        itens.append(
            {
                "codigo": "resultado_negativo",
                "titulo": "Resultado líquido do escritório negativo",
                "qtd": 1,
                "valor": rent["resumo"]["resultado_escritorio"],
                "severidade": "alta",
            }
        )

    return {
        "competencia": competencia,
        "itens": itens,
        "total": len(itens),
        "bloqueios": sum(1 for i in itens if i["severidade"] == "bloqueio"),
    }


@router.get("/conciliacao/{analysis_id}")
async def sugestoes_conciliacao_bancaria(
    analysis_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    analise = (
        await db.execute(
            text(
                """
                SELECT id,arquivo_nome,banco,periodo_inicio,periodo_fim
                FROM bank_analyses
                WHERE id=:id AND deleted_at IS NULL
                """
            ),
            {"id": analysis_id},
        )
    ).mappings().first()
    if not analise:
        raise HTTPException(404, "Extrato bancário não encontrado")

    candidatos = (
        await db.execute(
            text(
                """
                WITH candidatos AS (
                    SELECT fp.id target_id,'fee_payment'::text target_type,
                           fp.data_pagamento AS data,fp.valor,
                           ('Recebimento · ' || f.descricao) AS label,
                           'credito'::text AS tipo
                    FROM fee_payments fp
                    JOIN fees f ON f.id=fp.fee_id
                    WHERE f.deleted_at IS NULL
                    UNION ALL
                    SELECT oe.id,'office_expense',oe.pago_em,oe.valor,
                           ('Despesa · ' || oe.descricao),'debito'
                    FROM office_expenses oe
                    WHERE oe.deleted_at IS NULL
                      AND oe.status='pago'
                      AND oe.pago_em IS NOT NULL
                    UNION ALL
                    SELECT b.id,'commission_batch',CAST(b.paid_at AS date),b.total_pago,
                           ('Comissões · ' || b.competencia),'debito'
                    FROM commission_payment_batches b
                )
                SELECT
                    bt.id AS bank_transaction_id,
                    bt.data AS bank_date,
                    bt.descricao AS bank_description,
                    bt.valor AS bank_value,
                    bt.tipo AS bank_type,
                    c.target_id,c.target_type,c.data AS target_date,
                    c.valor AS target_value,c.label,
                    CASE
                      WHEN bt.data=c.data THEN 1.0000
                      WHEN ABS(bt.data-c.data)=1 THEN 0.9500
                      ELSE 0.9000
                    END AS confidence
                FROM bank_transactions bt
                JOIN candidatos c
                  ON c.tipo=bt.tipo
                 AND ABS(c.valor-bt.valor) <= 0.01
                 AND c.data BETWEEN bt.data-3 AND bt.data+3
                WHERE bt.analysis_id=:analysis_id
                ORDER BY bt.data,confidence DESC,c.target_type
                """
            ),
            {"analysis_id": analysis_id},
        )
    ).mappings().all()

    for row in candidatos:
        await db.execute(
            text(
                """
                INSERT INTO finance_reconciliation_matches
                    (id,bank_transaction_id,target_type,target_id,confidence,
                     status,reason,created_by,created_at)
                VALUES
                    (:id,:bank_tx,:target_type,:target_id,:confidence,
                     'sugerido',:reason,:created_by,NOW())
                ON CONFLICT (bank_transaction_id,target_type,target_id)
                DO UPDATE SET
                    confidence=EXCLUDED.confidence,
                    reason=EXCLUDED.reason
                WHERE finance_reconciliation_matches.status='sugerido'
                """
            ),
            {
                "id": str(uuid4()),
                "bank_tx": row["bank_transaction_id"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "confidence": row["confidence"],
                "reason": "Mesmo valor e data em janela de até 3 dias.",
                "created_by": cu.id,
            },
        )
    await db.commit()

    rows = (
        await db.execute(
            text(
                """
                WITH candidatos AS (
                    SELECT fp.id target_id,'fee_payment'::text target_type,
                           fp.data_pagamento AS data,fp.valor,
                           ('Recebimento · ' || f.descricao) AS label
                    FROM fee_payments fp
                    JOIN fees f ON f.id=fp.fee_id
                    WHERE f.deleted_at IS NULL
                    UNION ALL
                    SELECT oe.id,'office_expense',oe.pago_em,oe.valor,
                           ('Despesa · ' || oe.descricao)
                    FROM office_expenses oe
                    WHERE oe.deleted_at IS NULL
                    UNION ALL
                    SELECT b.id,'commission_batch',CAST(b.paid_at AS date),b.total_pago,
                           ('Comissões · ' || b.competencia)
                    FROM commission_payment_batches b
                )
                SELECT rm.*,bt.data AS bank_date,bt.descricao AS bank_description,
                       bt.valor AS bank_value,bt.tipo AS bank_type,
                       c.data AS target_date,c.valor AS target_value,c.label
                FROM finance_reconciliation_matches rm
                JOIN bank_transactions bt ON bt.id=rm.bank_transaction_id
                JOIN candidatos c
                  ON c.target_id=rm.target_id AND c.target_type=rm.target_type
                WHERE bt.analysis_id=:analysis_id
                ORDER BY bt.data,rm.status='confirmado' DESC,rm.confidence DESC
                """
            ),
            {"analysis_id": analysis_id},
        )
    ).mappings().all()

    total_txs = (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM bank_transactions WHERE analysis_id=:id"
            ),
            {"id": analysis_id},
        )
    ).scalar() or 0
    confirmados = len(
        {r["bank_transaction_id"] for r in rows if r["status"] == "confirmado"}
    )
    return {
        "analise": dict(analise),
        "total_transacoes": int(total_txs),
        "confirmados": confirmados,
        "pendentes": max(int(total_txs) - confirmados, 0),
        "sugestoes": [dict(r) for r in rows],
    }


@router.post("/conciliacao/confirmar")
async def confirmar_conciliacao_bancaria(
    body: ReconcileConfirmIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    row = (
        await db.execute(
            text(
                """
                SELECT id,status
                FROM finance_reconciliation_matches
                WHERE bank_transaction_id=:bank_tx
                  AND target_type=:target_type
                  AND target_id=:target_id
                FOR UPDATE
                """
            ),
            {
                "bank_tx": body.bank_transaction_id,
                "target_type": body.target_type,
                "target_id": body.target_id,
            },
        )
    ).mappings().first()
    if not row:
        raise HTTPException(404, "Sugestão de conciliação não encontrada")
    await db.execute(
        text(
            """
            UPDATE finance_reconciliation_matches
            SET status='rejeitado'
            WHERE bank_transaction_id=:bank_tx
              AND status='sugerido'
            """
        ),
        {"bank_tx": body.bank_transaction_id},
    )
    await db.execute(
        text(
            """
            UPDATE finance_reconciliation_matches
            SET status='confirmado',confirmed_by=:uid,confirmed_at=NOW()
            WHERE id=:id
            """
        ),
        {"uid": cu.id, "id": row["id"]},
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "RECONCILE",
        "finance_reconciliation_matches",
        row["id"],
        detalhes="Movimento bancário conciliado manualmente.",
        dados_depois=body.model_dump(),
    )
    await db.commit()
    return {"ok": True, "id": row["id"], "status": "confirmado"}


@router.get("/comissoes", dependencies=[Depends(rate_limit("fin-comissoes", 60))])
async def listar_comissoes(
    status: Optional[str] = None,
    search: Optional[str] = None,
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    inicio = fim = None
    if competencia:
        ano, mes = (int(v) for v in competencia.split("-"))
        inicio = date(ano, mes, 1)
        fim = date(ano + (1 if mes == 12 else 0), 1 if mes == 12 else mes + 1, 1)

    rows = (
        await db.execute(
            text(
                """
                WITH ajustes AS (
                    SELECT
                        allocation_id,
                        COALESCE(SUM(valor_advogado), 0) AS valor_advogado,
                        COALESCE(SUM(valor_escritorio), 0) AS valor_escritorio,
                        COALESCE(SUM(valor_advogado - applied_value), 0) AS saldo_pendente,
                        COUNT(*) AS qtd
                    FROM commission_adjustments
                    GROUP BY allocation_id
                )
                SELECT
                    a.id,
                    a.case_id,
                    a.fee_payment_id,
                    a.advogado_responsavel_id AS advogado_id,
                    u.full_name AS advogado,
                    c.titulo AS caso,
                    c.numero_interno,
                    COALESCE(cl.nome, cl.razao_social, 'Cliente') AS cliente,
                    fp.data_pagamento,
                    a.bruto_recebido,
                    a.despesas_deduzidas,
                    a.base_liquida,
                    a.percentual_advogado,
                    a.valor_advogado,
                    a.valor_escritorio,
                    a.valor_advogado + COALESCE(aj.valor_advogado, 0) AS valor_advogado_efetivo,
                    a.valor_escritorio + COALESCE(aj.valor_escritorio, 0) AS valor_escritorio_efetivo,
                    COALESCE(aj.valor_advogado, 0) AS ajustes_advogado,
                    COALESCE(aj.valor_escritorio, 0) AS ajustes_escritorio,
                    COALESCE(aj.saldo_pendente, 0) AS saldo_ajuste_pendente,
                    COALESCE(aj.qtd, 0) AS ajustes_qtd,
                    cr.nome AS regra_nome,
                    cr.escopo AS regra_escopo,
                    a.withdrawal_id,
                    pw.status AS withdrawal_status,
                    pw.partner_share AS valor_ordem_pagamento,
                    pw.approved_at,
                    pw.paid_at,
                    pw.payment_method,
                    pw.payment_reference,
                    pw.comprovante_doc_id,
                    pw.payment_batch_id,
                    CASE
                        WHEN a.valor_advogado + COALESCE(aj.valor_advogado, 0) <= 0 THEN 'estornada'
                        WHEN a.withdrawal_id IS NULL THEN 'calculada'
                        WHEN pw.status = 'pendente' THEN 'a_aprovar'
                        WHEN pw.status = 'aprovado' THEN 'a_pagar'
                        WHEN pw.status = 'pago' THEN 'paga'
                        WHEN pw.status = 'rejeitado' THEN 'rejeitada'
                        WHEN pw.status = 'cancelado' THEN 'estornada'
                        ELSE COALESCE(pw.status, 'calculada')
                    END AS status
                FROM case_receipt_allocations a
                JOIN fee_payments fp ON fp.id = a.fee_payment_id
                JOIN fees f ON f.id = fp.fee_id
                JOIN cases c ON c.id = a.case_id
                LEFT JOIN clients cl ON cl.id = f.client_id AND cl.deleted_at IS NULL
                LEFT JOIN users u ON u.id = a.advogado_responsavel_id
                LEFT JOIN commission_rules cr ON cr.id = a.commission_rule_id
                LEFT JOIN partner_withdrawals pw ON pw.id = a.withdrawal_id AND pw.deleted_at IS NULL
                LEFT JOIN ajustes aj ON aj.allocation_id = a.id
                WHERE f.deleted_at IS NULL
                  AND a.valor_advogado > 0
                  AND (CAST(:inicio AS date) IS NULL OR fp.data_pagamento >= CAST(:inicio AS date))
                  AND (CAST(:fim AS date) IS NULL OR fp.data_pagamento < CAST(:fim AS date))
                ORDER BY fp.data_pagamento DESC, a.created_at DESC
                LIMIT 1000
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).mappings().all()

    all_rows = [dict(r) for r in rows]
    data = list(all_rows)
    termo = (search or "").strip().casefold()
    if termo:
        data = [
            r
            for r in data
            if termo
            in " ".join(
                str(r.get(k) or "")
                for k in (
                    "advogado",
                    "cliente",
                    "caso",
                    "numero_interno",
                    "bruto_recebido",
                    "valor_advogado_efetivo",
                )
            ).casefold()
        ]
    if status:
        data = [r for r in data if r.get("status") == status]

    def total_por(st: str) -> Decimal:
        return _money(
            sum(
                (
                    Decimal(str(r["valor_advogado_efetivo"] or 0))
                    for r in all_rows
                    if r["status"] == st
                ),
                Decimal("0"),
            )
        )

    pagamentos_reais = (
        await db.execute(
            text(
                """
                WITH pagos AS (
                    SELECT
                        i.partner_id,
                        SUM(i.valor_pago) AS valor
                    FROM commission_payment_batch_items i
                    JOIN commission_payment_batches b ON b.id=i.batch_id
                    WHERE (CAST(:inicio AS timestamptz) IS NULL OR b.paid_at >= CAST(:inicio AS timestamptz))
                      AND (CAST(:fim AS timestamptz) IS NULL OR b.paid_at < CAST(:fim AS timestamptz))
                    GROUP BY i.partner_id
                    UNION ALL
                    SELECT
                        pw.partner_id,
                        SUM(pw.partner_share) AS valor
                    FROM partner_withdrawals pw
                    WHERE pw.deleted_at IS NULL
                      AND pw.status='pago'
                      AND pw.payment_batch_id IS NULL
                      AND (CAST(:inicio AS timestamptz) IS NULL OR pw.paid_at >= CAST(:inicio AS timestamptz))
                      AND (CAST(:fim AS timestamptz) IS NULL OR pw.paid_at < CAST(:fim AS timestamptz))
                    GROUP BY pw.partner_id
                )
                SELECT partner_id,COALESCE(SUM(valor),0) AS valor
                FROM pagos
                GROUP BY partner_id
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).mappings().all()
    pago_por_advogado = {
        str(r["partner_id"]): _money(r["valor"]) for r in pagamentos_reais
    }
    pago_periodo = _money(
        sum(pago_por_advogado.values(), Decimal("0"))
    )
    escritorio = _money(
        sum(
            (Decimal(str(r["valor_escritorio_efetivo"] or 0)) for r in all_rows),
            Decimal("0"),
        )
    )
    ajustes_pendentes = _money(
        sum(
            (Decimal(str(r["saldo_ajuste_pendente"] or 0)) for r in all_rows),
            Decimal("0"),
        )
    )

    por_advogado_map: dict[str, dict] = {}
    for r in all_rows:
        aid = r.get("advogado_id")
        if not aid:
            continue
        item = por_advogado_map.setdefault(
            aid,
            {
                "advogado_id": aid,
                "advogado": r.get("advogado") or "Advogado",
                "recebido": Decimal("0"),
                "comissao_gerada": Decimal("0"),
                "comissao_paga": Decimal("0"),
                "saldo": Decimal("0"),
                "ajustes_pendentes": Decimal("0"),
            },
        )
        item["recebido"] += Decimal(str(r.get("bruto_recebido") or 0))
        efetiva = Decimal(str(r.get("valor_advogado_efetivo") or 0))
        item["comissao_gerada"] += efetiva
        item["ajustes_pendentes"] += Decimal(str(r.get("saldo_ajuste_pendente") or 0))

    por_advogado = []
    for item in sorted(por_advogado_map.values(), key=lambda x: x["advogado"].casefold()):
        pago = pago_por_advogado.get(str(item["advogado_id"]), Decimal("0"))
        saldo = max(
            item["comissao_gerada"] - pago,
            Decimal("0"),
        )
        por_advogado.append(
            {
                **item,
                "recebido": _money(item["recebido"]),
                "comissao_gerada": _money(item["comissao_gerada"]),
                "comissao_paga": _money(pago),
                "saldo": _money(saldo),
                "ajustes_pendentes": _money(item["ajustes_pendentes"]),
            }
        )

    return {
        "competencia": competencia,
        "data": data,
        "resumo": {
            "calculada": total_por("calculada"),
            "a_aprovar": total_por("a_aprovar"),
            "a_pagar": total_por("a_pagar"),
            "paga_periodo": pago_periodo,
            "escritorio_total": escritorio,
            "ajustes_pendentes": ajustes_pendentes,
        },
        "por_advogado": por_advogado,
    }


@router.post("/comissoes/{allocation_id}/enviar-aprovacao")
async def enviar_comissao_para_aprovacao(
    allocation_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    row = (
        await db.execute(
            text(
                """
                SELECT a.*, c.titulo, c.numero_interno
                FROM case_receipt_allocations a
                JOIN cases c ON c.id = a.case_id
                WHERE a.id=:id
                FOR UPDATE
                """
            ),
            {"id": allocation_id},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(404, "Comissão não encontrada")
    if row["withdrawal_id"]:
        return {"ok": True, "withdrawal_id": row["withdrawal_id"], "already_exists": True}
    if not row["advogado_responsavel_id"] or _money(row["valor_advogado"]) <= 0:
        raise HTTPException(422, "Comissão sem advogado ou valor disponível para aprovação")

    wid = str(uuid4())
    await db.execute(
        text(
            """
            INSERT INTO partner_withdrawals
                (id, partner_id, gross_value, case_expenses, net_value,
                 partner_share, description, period_reference, status,
                 created_at, updated_at)
            VALUES
                (:id, :partner_id, :gross, :expenses, :net, :share,
                 :description, :ref, 'pendente', now(), now())
            """
        ),
        {
            "id": wid,
            "partner_id": row["advogado_responsavel_id"],
            "gross": row["bruto_recebido"],
            "expenses": row["despesas_deduzidas"],
            "net": row["base_liquida"],
            "share": row["valor_advogado"],
            "description": f"Comissão — {row['numero_interno'] or row['titulo']}",
            "ref": f"commission:{str(row['fee_payment_id'])[:29]}",
        },
    )
    await db.execute(
        text(
            "UPDATE case_receipt_allocations SET withdrawal_id=:wid WHERE id=:id"
        ),
        {"wid": wid, "id": allocation_id},
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "SUBMIT",
        "case_receipt_allocations",
        allocation_id,
        detalhes="Comissão enviada à fila de aprovação.",
        dados_depois={"withdrawal_id": wid},
    )
    await db.commit()
    return {"ok": True, "withdrawal_id": wid}




@router.post("/comissoes/{allocation_id}/ajustes", status_code=201)
async def criar_ajuste_comissao(
    allocation_id: str,
    body: CommissionAdjustmentIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    from app.services.commission_service import registrar_ajuste_comissao
    from app.services.finance_governance import competencia_de_data, exigir_competencia_aberta

    await exigir_competencia_aberta(
        db,
        competencia_de_data(date.today()),
        "Registrar ajuste de comissão",
    )
    valor_escritorio = (
        body.valor_escritorio
        if body.valor_escritorio is not None
        else -body.valor_advogado
    )
    try:
        resultado = await registrar_ajuste_comissao(
            db,
            allocation_id=allocation_id,
            valor_advogado=body.valor_advogado,
            valor_escritorio=valor_escritorio,
            motivo=body.motivo,
            user=cu,
            source_type="ajuste",
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    await db.commit()
    return resultado


@router.get("/comissoes/previsao")
async def previsao_comissoes(
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Estimativa separada do realizado; não deduz despesas futuras."""
    _exigir_financeiro(cu)
    inicio = fim = None
    if competencia:
        inicio, fim = _month_bounds(competencia)

    rows = (
        await db.execute(
            # SQL composto apenas por CTE constante e bind params; sem entrada estrutural do usuário.
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"""
                WITH {LEDGER_COMPAT_CTES},
                saldos AS (
                    SELECT
                        f.id,
                        f.case_id,
                        f.data_vencimento,
                        GREATEST(COALESCE(f.valor,0)-COALESCE(pe.total_pago,0),0) AS saldo
                    FROM fees f
                    LEFT JOIN pagamentos_efetivos pe ON pe.fee_id=f.id
                    WHERE f.deleted_at IS NULL
                      AND f.valor IS NOT NULL
                      AND CAST(f.status AS text) IN ('pendente','atrasado')
                )
                SELECT
                    s.id AS fee_id,
                    s.case_id,
                    s.data_vencimento,
                    s.saldo,
                    c.advogado_responsavel_id AS advogado_id,
                    u.full_name AS advogado,
                    c.titulo AS caso,
                    c.numero_interno,
                    COALESCE(cl.nome,cl.razao_social,'Cliente') AS cliente,
                    COALESCE(cr.percentual_advogado,50) AS percentual_advogado,
                    COALESCE(cr.nome,'Regra padrão 50/50') AS regra,
                    COALESCE(cr.escopo,'padrao') AS regra_escopo,
                    ROUND(s.saldo * COALESCE(cr.percentual_advogado,50) / 100, 2) AS comissao_prevista
                FROM saldos s
                JOIN cases c ON c.id=s.case_id AND c.deleted_at IS NULL
                LEFT JOIN users u ON u.id=c.advogado_responsavel_id
                LEFT JOIN clients cl ON cl.id=c.client_id AND cl.deleted_at IS NULL
                LEFT JOIN LATERAL (
                    SELECT r.percentual_advogado,r.nome,r.escopo
                    FROM commission_rules r
                    WHERE r.deleted_at IS NULL
                      AND r.ativo=TRUE
                      AND r.vigencia_inicio <= CURRENT_DATE
                      AND (r.vigencia_fim IS NULL OR r.vigencia_fim >= CURRENT_DATE)
                      AND (
                        (r.escopo='caso' AND r.case_id=c.id)
                        OR (r.escopo='advogado' AND r.advogado_id=c.advogado_responsavel_id)
                        OR (r.escopo='area' AND LOWER(r.area)=LOWER(CAST(c.area AS text)))
                        OR r.escopo='padrao'
                      )
                    ORDER BY
                      CASE r.escopo
                        WHEN 'caso' THEN 0
                        WHEN 'advogado' THEN 1
                        WHEN 'area' THEN 2
                        ELSE 3
                      END,
                      r.prioridade,
                      r.created_at DESC
                    LIMIT 1
                ) cr ON TRUE
                WHERE s.saldo > 0
                  AND c.advogado_responsavel_id IS NOT NULL
                  AND (CAST(:inicio AS date) IS NULL OR s.data_vencimento >= CAST(:inicio AS date))
                  AND (CAST(:fim AS date) IS NULL OR s.data_vencimento < CAST(:fim AS date))
                ORDER BY s.data_vencimento NULLS LAST,c.numero_interno
                LIMIT 1000
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).mappings().all()
    data = [dict(r) for r in rows]

    indeterminadas = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM fees f
                JOIN cases c ON c.id=f.case_id AND c.deleted_at IS NULL
                WHERE f.deleted_at IS NULL
                  AND f.valor IS NULL
                  AND f.percentual_exito IS NOT NULL
                  AND CAST(f.status AS text) IN ('pendente','atrasado')
                  AND c.advogado_responsavel_id IS NOT NULL
                  AND (CAST(:inicio AS date) IS NULL OR f.data_vencimento >= CAST(:inicio AS date))
                  AND (CAST(:fim AS date) IS NULL OR f.data_vencimento < CAST(:fim AS date))
                """
            ),
            {"inicio": inicio, "fim": fim},
        )
    ).scalar() or 0

    grupos: dict[str, dict] = {}
    for row in data:
        aid = row["advogado_id"]
        g = grupos.setdefault(
            aid,
            {
                "advogado_id": aid,
                "advogado": row["advogado"] or "Advogado",
                "saldo_contratado": Decimal("0"),
                "comissao_prevista": Decimal("0"),
                "qtd": 0,
            },
        )
        g["saldo_contratado"] += Decimal(str(row["saldo"] or 0))
        g["comissao_prevista"] += Decimal(str(row["comissao_prevista"] or 0))
        g["qtd"] += 1

    por_advogado = [
        {
            **g,
            "saldo_contratado": _money(g["saldo_contratado"]),
            "comissao_prevista": _money(g["comissao_prevista"]),
        }
        for g in sorted(grupos.values(), key=lambda x: x["advogado"].casefold())
    ]
    return {
        "competencia": competencia,
        "total": _money(
            sum(
                (Decimal(str(r["comissao_prevista"] or 0)) for r in data),
                Decimal("0"),
            )
        ),
        "saldo_contratado": _money(
            sum((Decimal(str(r["saldo"] or 0)) for r in data), Decimal("0"))
        ),
        "indeterminadas": int(indeterminadas),
        "por_advogado": por_advogado,
        "data": data,
        "aviso": (
            "Previsão gerencial sobre saldos contratuais conhecidos. "
            "Despesas futuras não são deduzidas; êxito sem base monetária fica apenas na contagem."
        ),
    }


@router.get("/comissoes/conferencia")
async def conferencia_comissoes(
    competencia: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    return await _commission_conference(db, competencia)


@router.get("/comissoes/extrato-mensal")
async def extrato_mensal_comissoes(
    competencia: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    advogado_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    if advogado_id and cu.role.value not in _GESTOR_FIN and str(cu.id) != advogado_id:
        raise HTTPException(403, "Sem permissão para consultar outro advogado")
    extrato = await _commission_statement(db, competencia, advogado_id)
    fechamento = (
        await db.execute(
            text(
                """
                SELECT id,competencia,snapshot_json,closed_by,closed_at
                FROM commission_month_closings
                WHERE competencia=:competencia
                """
            ),
            {"competencia": competencia},
        )
    ).mappings().first()
    extrato["fechamento"] = dict(fechamento) if fechamento else None
    return extrato


@router.get("/comissoes/fechamentos/{competencia}")
async def obter_fechamento_comissoes(
    competencia: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    if not __import__("re").fullmatch(r"\d{4}-(0[1-9]|1[0-2])", competencia):
        raise HTTPException(422, "competencia inválida: use AAAA-MM")
    row = (
        await db.execute(
            text(
                """
                SELECT id,competencia,snapshot_json,closed_by,closed_at,created_at
                FROM commission_month_closings
                WHERE competencia=:competencia
                """
            ),
            {"competencia": competencia},
        )
    ).mappings().first()
    return dict(row) if row else {"competencia": competencia, "fechado": False}


@router.post("/comissoes/fechamentos", status_code=201)
async def fechar_competencia_comissoes(
    body: CommissionCloseIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_gestor_regras(cu)
    existente = (
        await db.execute(
            text(
                "SELECT id FROM commission_month_closings WHERE competencia=:competencia"
            ),
            {"competencia": body.competencia},
        )
    ).scalar_one_or_none()
    if existente:
        raise HTTPException(409, "Competência de comissões já foi fechada")

    conferencia = await _commission_conference(db, body.competencia)
    if not conferencia["pronto"]:
        raise HTTPException(
            409,
            detail={
                "message": "Fechamento bloqueado por pendências de comissão",
                "conferencia": conferencia,
            },
        )

    snapshot = await _commission_statement(db, body.competencia)
    snapshot["conferencia"] = conferencia
    cid = str(uuid4())
    agora = datetime.now(timezone.utc)
    await db.execute(
        text(
            """
            INSERT INTO commission_month_closings
                (id,competencia,snapshot_json,closed_by,closed_at,created_at)
            VALUES
                (:id,:competencia,CAST(:snapshot AS jsonb),:closed_by,:closed_at,NOW())
            """
        ),
        {
            "id": cid,
            "competencia": body.competencia,
            "snapshot": json.dumps(snapshot, default=str, ensure_ascii=False),
            "closed_by": cu.id,
            "closed_at": agora,
        },
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CLOSE",
        "commission_month_closings",
        cid,
        detalhes=f"Competência de comissões {body.competencia} fechada em snapshot.",
        dados_depois={"competencia": body.competencia},
    )
    await db.commit()
    return {
        "id": cid,
        "competencia": body.competencia,
        "closed_at": agora,
        "snapshot": snapshot,
    }


@router.post("/comissoes/lotes-pagamento", status_code=201)
async def pagar_comissoes_em_lote(
    body: CommissionBatchIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    ids = list(dict.fromkeys(body.withdrawal_ids))
    if body.comprovante_doc_id:
        doc = (
            await db.execute(
                text(
                    "SELECT id FROM documents WHERE id=:id AND deleted_at IS NULL"
                ),
                {"id": body.comprovante_doc_id},
            )
        ).scalar_one_or_none()
        if not doc:
            raise HTTPException(422, "Comprovante documental não encontrado")

    withdrawals = (
        await db.execute(
            text(
                """
                SELECT pw.*,u.full_name AS advogado
                FROM partner_withdrawals pw
                LEFT JOIN users u ON u.id=pw.partner_id
                WHERE pw.id = ANY(CAST(:ids AS varchar[]))
                  AND pw.deleted_at IS NULL
                FOR UPDATE OF pw
                """
            ),
            {"ids": ids},
        )
    ).mappings().all()
    if len(withdrawals) != len(ids):
        raise HTTPException(404, "Uma ou mais comissões selecionadas não existem")

    from app.services.finance_governance import (
        competencia_de_data,
        exigir_competencia_aberta,
        limite_dupla_aprovacao,
    )
    competencia_pagamento = competencia_de_data(body.paid_at)
    await exigir_competencia_aberta(
        db, competencia_pagamento, "Pagar comissões"
    )
    limite = await limite_dupla_aprovacao(db)
    total_nominal = _money(
        sum((Decimal(str(r["partner_share"] or 0)) for r in withdrawals), Decimal("0"))
    )
    if total_nominal >= limite and any(
        str(r.get("approved_by") or "") == str(cu.id) for r in withdrawals
    ):
        raise HTTPException(
            403,
            (
                f"Lote de {float(total_nominal):.2f} excede a alçada de "
                f"{float(limite):.2f}; quem aprovou a comissão não pode executar "
                "o pagamento. É necessária segunda pessoa autorizada."
            ),
        )

    por_partner: dict[str, list[dict]] = {}
    for raw in withdrawals:
        row = dict(raw)
        if row["status"] != "aprovado":
            raise HTTPException(
                409,
                f"Comissão {row['id']} precisa estar aprovada antes do pagamento",
            )
        if str(row["partner_id"]) == str(cu.id):
            raise HTTPException(
                403,
                "Pagamento da própria comissão não é permitido — segregação de funções",
            )
        por_partner.setdefault(str(row["partner_id"]), []).append(row)

    batch_id = str(uuid4())
    itens_batch: list[dict] = []
    total_batch = Decimal("0")

    for partner_id, items in por_partner.items():
        valor_retiradas = _money(
            sum((Decimal(str(i["partner_share"] or 0)) for i in items), Decimal("0"))
        )
        disponivel = valor_retiradas
        ajuste_total = Decimal("0")
        ajustes_aplicados: list[str] = []

        ajustes = (
            await db.execute(
                text(
                    """
                    SELECT ca.id,ca.valor_advogado,ca.applied_value
                    FROM commission_adjustments ca
                    JOIN case_receipt_allocations a ON a.id=ca.allocation_id
                    WHERE a.advogado_responsavel_id=:partner_id
                      AND ca.valor_advogado <> ca.applied_value
                    ORDER BY
                      CASE WHEN ca.valor_advogado-ca.applied_value > 0 THEN 0 ELSE 1 END,
                      ca.created_at,
                      ca.id
                    FOR UPDATE OF ca
                    """
                ),
                {"partner_id": partner_id},
            )
        ).mappings().all()

        for aj in ajustes:
            restante = _money(
                Decimal(str(aj["valor_advogado"]))
                - Decimal(str(aj["applied_value"] or 0))
            )
            if restante == 0:
                continue
            if restante > 0:
                delta = restante
            else:
                if disponivel <= 0:
                    continue
                delta = max(restante, -disponivel)
            if delta == 0:
                continue
            novo_aplicado = _money(Decimal(str(aj["applied_value"] or 0)) + delta)
            await db.execute(
                text(
                    "UPDATE commission_adjustments SET applied_value=:valor WHERE id=:id"
                ),
                {"valor": novo_aplicado, "id": aj["id"]},
            )
            disponivel = _money(disponivel + delta)
            ajuste_total = _money(ajuste_total + delta)
            ajustes_aplicados.append(aj["id"])

        valor_pago = max(disponivel, Decimal("0"))
        total_batch = _money(total_batch + valor_pago)
        itens_batch.append(
            {
                "partner_id": partner_id,
                "advogado": items[0].get("advogado") or "Advogado",
                "withdrawal_ids": [i["id"] for i in items],
                "adjustment_ids": ajustes_aplicados,
                "valor_retiradas": valor_retiradas,
                "valor_ajustes": ajuste_total,
                "valor_pago": valor_pago,
            }
        )

    competencia = competencia_pagamento
    await db.execute(
        text(
            """
            INSERT INTO commission_payment_batches
                (id,competencia,payment_method,payment_reference,
                 comprovante_doc_id,observacao,total_pago,paid_by,paid_at,created_at)
            VALUES
                (:id,:competencia,:method,:reference,:doc_id,:observacao,
                 :total,:paid_by,:paid_at,NOW())
            """
        ),
        {
            "id": batch_id,
            "competencia": competencia,
            "method": body.payment_method,
            "reference": body.payment_reference,
            "doc_id": body.comprovante_doc_id,
            "observacao": body.observacao,
            "total": total_batch,
            "paid_by": cu.id,
            "paid_at": body.paid_at,
        },
    )

    from app.models.audit_log import criar_audit_log
    for item in itens_batch:
        item_id = str(uuid4())
        await db.execute(
            text(
                """
                INSERT INTO commission_payment_batch_items
                    (id,batch_id,partner_id,withdrawal_ids,adjustment_ids,
                     valor_retiradas,valor_ajustes,valor_pago,created_at)
                VALUES
                    (:id,:batch_id,:partner_id,CAST(:withdrawals AS jsonb),
                     CAST(:adjustments AS jsonb),:retiradas,:ajustes,:pago,NOW())
                """
            ),
            {
                "id": item_id,
                "batch_id": batch_id,
                "partner_id": item["partner_id"],
                "withdrawals": json.dumps(item["withdrawal_ids"]),
                "adjustments": json.dumps(item["adjustment_ids"]),
                "retiradas": item["valor_retiradas"],
                "ajustes": item["valor_ajustes"],
                "pago": item["valor_pago"],
            },
        )
        await db.execute(
            text(
                """
                UPDATE partner_withdrawals
                SET status='pago',
                    paid_at=:paid_at,
                    paid_by=:paid_by,
                    payment_method=:method,
                    payment_reference=:reference,
                    comprovante_doc_id=:doc_id,
                    payment_batch_id=:batch_id,
                    updated_at=NOW()
                WHERE id = ANY(CAST(:ids AS varchar[]))
                """
            ),
            {
                "paid_at": body.paid_at,
                "paid_by": cu.id,
                "method": body.payment_method,
                "reference": body.payment_reference,
                "doc_id": body.comprovante_doc_id,
                "batch_id": batch_id,
                "ids": item["withdrawal_ids"],
            },
        )
        for withdrawal_id in item["withdrawal_ids"]:
            await criar_audit_log(
                db,
                cu.id,
                cu.role.value,
                "PAY_BATCH",
                "partner_withdrawals",
                withdrawal_id,
                detalhes=f"Comissão paga no lote {batch_id}.",
                dados_depois={
                    "batch_id": batch_id,
                    "payment_method": body.payment_method,
                    "payment_reference": body.payment_reference,
                    "comprovante_doc_id": body.comprovante_doc_id,
                },
            )

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CREATE",
        "commission_payment_batches",
        batch_id,
        detalhes=f"Lote de pagamento de comissões: {len(ids)} retirada(s).",
        dados_depois={
            "competencia": competencia,
            "total_pago": str(total_batch),
            "itens": len(itens_batch),
        },
    )
    await db.commit()
    return {
        "id": batch_id,
        "competencia": competencia,
        "total_pago": total_batch,
        "itens": itens_batch,
    }


@router.get("/comissoes/regras", dependencies=[Depends(rate_limit("fin-comissoes-regras", 60))])
async def listar_regras_comissao(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    rows = (
        await db.execute(
            text(
                """
                SELECT r.*, u.full_name AS advogado_nome,
                       c.titulo AS caso_titulo, c.numero_interno
                FROM commission_rules r
                LEFT JOIN users u ON u.id = r.advogado_id
                LEFT JOIN cases c ON c.id = r.case_id
                WHERE r.deleted_at IS NULL
                ORDER BY r.ativo DESC,
                    CASE r.escopo WHEN 'caso' THEN 1 WHEN 'advogado' THEN 2
                         WHEN 'area' THEN 3 ELSE 4 END,
                    r.prioridade, r.created_at DESC
                """
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


@router.post("/comissoes/regras", status_code=201)
async def criar_regra_comissao(
    body: CommissionRuleIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_gestor_regras(cu)
    rid = str(uuid4())
    await db.execute(
        text(
            """
            INSERT INTO commission_rules
                (id,nome,escopo,area,advogado_id,case_id,percentual_advogado,
                 descontar_despesas,prioridade,ativo,vigencia_inicio,vigencia_fim,
                 created_by,created_at,updated_at)
            VALUES
                (:id,:nome,:escopo,:area,:advogado_id,:case_id,:pct,
                 :descontar,:prioridade,:ativo,:inicio,:fim,:created_by,now(),now())
            """
        ),
        {
            "id": rid, "nome": body.nome, "escopo": body.escopo,
            "area": body.area if body.escopo == "area" else None,
            "advogado_id": body.advogado_id if body.escopo == "advogado" else None,
            "case_id": body.case_id if body.escopo == "caso" else None,
            "pct": body.percentual_advogado, "descontar": body.descontar_despesas,
            "prioridade": body.prioridade, "ativo": body.ativo,
            "inicio": body.vigencia_inicio, "fim": body.vigencia_fim,
            "created_by": cu.id,
        },
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db, cu.id, cu.role.value, "CREATE", "commission_rules", rid,
        detalhes="Regra de comissão criada.",
        dados_depois=body.model_dump(mode="json"),
    )
    await db.commit()
    return {"id": rid, "ok": True}


@router.patch("/comissoes/regras/{rule_id}")
async def atualizar_regra_comissao(
    rule_id: str,
    body: CommissionRulePatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_gestor_regras(cu)
    atual = (
        await db.execute(
            text("SELECT * FROM commission_rules WHERE id=:id AND deleted_at IS NULL"),
            {"id": rule_id},
        )
    ).mappings().first()
    if not atual:
        raise HTTPException(404, "Regra de comissão não encontrada")
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "Nenhuma alteração informada")
    campos = {
        "nome": "nome",
        "percentual_advogado": "percentual_advogado",
        "descontar_despesas": "descontar_despesas",
        "prioridade": "prioridade",
        "ativo": "ativo",
        "vigencia_fim": "vigencia_fim",
    }
    valores = {campos[key]: value for key, value in changes.items()}
    valores["updated_at"] = datetime.now(timezone.utc)
    await db.execute(
        update(CommissionRule)
        .where(
            CommissionRule.id == rule_id,
            CommissionRule.deleted_at.is_(None),
        )
        .values(**valores)
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db, cu.id, cu.role.value, "UPDATE", "commission_rules", rule_id,
        dados_antes={k: atual.get(campos[k]) for k in changes},
        dados_depois=body.model_dump(exclude_unset=True, mode="json"),
    )
    await db.commit()
    return {"ok": True}


@router.delete("/comissoes/regras/{rule_id}")
async def remover_regra_comissao(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_gestor_regras(cu)
    if rule_id in {"commission-default-50", "commission-area-civil-0"}:
        raise HTTPException(409, "Regra estrutural: desative ou altere em vez de excluir")
    row = (
        await db.execute(
            text("SELECT id FROM commission_rules WHERE id=:id AND deleted_at IS NULL"),
            {"id": rule_id},
        )
    ).first()
    if not row:
        raise HTTPException(404, "Regra de comissão não encontrada")
    await db.execute(
        text("UPDATE commission_rules SET deleted_at=NOW(), ativo=FALSE, updated_at=NOW() WHERE id=:id"),
        {"id": rule_id},
    )
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db, cu.id, cu.role.value, "DELETE", "commission_rules", rule_id,
        detalhes="Regra de comissão removida por soft delete.",
    )
    await db.commit()
    return {"ok": True}


@router.get("/comissoes/opcoes")
async def opcoes_comissao(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    advogados = (
        await db.execute(
            text(
                """
                SELECT id, full_name, CAST(role AS text) AS role
                FROM users
                WHERE deleted_at IS NULL AND is_active=TRUE
                  AND CAST(role AS text) IN ('advogado','socio','admin','superadmin')
                ORDER BY full_name
                """
            )
        )
    ).mappings().all()
    casos = (
        await db.execute(
            text(
                """
                SELECT id, titulo, numero_interno, CAST(area AS text) AS area
                FROM cases
                WHERE deleted_at IS NULL AND CAST(status AS text) != 'arquivado'
                ORDER BY created_at DESC
                LIMIT 500
                """
            )
        )
    ).mappings().all()
    areas = (
        await db.execute(
            text(
                """
                SELECT DISTINCT CAST(area AS text) AS area
                FROM cases
                WHERE deleted_at IS NULL
                ORDER BY area
                """
            )
        )
    ).scalars().all()
    return {
        "advogados": [dict(r) for r in advogados],
        "casos": [dict(r) for r in casos],
        "areas": [a for a in areas if a],
    }


@router.get("/fechamento-inteligente", dependencies=[Depends(rate_limit("fin-fechamento-inteligente", 10))])
async def fechamento_inteligente(
    competencia: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Pré-fechamento gerencial read-only da competência."""
    _exigir_financeiro(cu)
    competencia = _competencia_atual(competencia)
    mes_ref = date.fromisoformat(f"{competencia}-01")

    fee_integridade = (
        await db.execute(
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                f"""
                WITH {LEDGER_COMPAT_CTES}
                SELECT
                    COUNT(*) FILTER (
                        WHERE f.valor IS NOT NULL
                          AND COALESCE(pe.total_pago, 0) > f.valor
                    ) AS overpayment,
                    COUNT(*) FILTER (
                        WHERE CAST(f.status AS text) = 'pago'
                          AND f.valor IS NOT NULL
                          AND COALESCE(pe.total_pago, 0) < f.valor
                    ) AS pago_com_saldo,
                    COUNT(*) FILTER (
                        WHERE f.valor IS NULL
                          AND f.percentual_exito IS NOT NULL
                          AND CAST(f.status AS text) IN ('pendente','atrasado')
                          AND date_trunc('month', f.data_vencimento)
                              = date_trunc('month', CAST(:mes AS date))
                    ) AS percentuais_sem_base,
                    COUNT(*) FILTER (
                        WHERE CAST(f.status AS text) IN ('pendente','atrasado')
                          AND f.valor IS NOT NULL
                          AND f.data_vencimento <=
                              (date_trunc('month', CAST(:mes AS date))
                               + INTERVAL '1 month - 1 day')::date
                          AND GREATEST(f.valor - COALESCE(pe.total_pago, 0), 0) > 0
                    ) AS recebiveis_pendentes,
                    COALESCE(SUM(
                        GREATEST(f.valor - COALESCE(pe.total_pago, 0), 0)
                    ) FILTER (
                        WHERE CAST(f.status AS text) IN ('pendente','atrasado')
                          AND f.valor IS NOT NULL
                          AND f.data_vencimento <=
                              (date_trunc('month', CAST(:mes AS date))
                               + INTERVAL '1 month - 1 day')::date
                    ), 0) AS recebiveis_pendentes_valor,
                    COUNT(*) FILTER (
                        WHERE pe.legado_sem_subledger = TRUE
                          AND date_trunc('month', f.data_pagamento)
                              = date_trunc('month', CAST(:mes AS date))
                    ) AS legados_sem_subledger
                FROM fees f
                LEFT JOIN pagamentos_efetivos pe ON pe.fee_id = f.id
                WHERE f.deleted_at IS NULL
                  AND CAST(f.status AS text) != 'cancelado'
                """
            ),
            {"mes": mes_ref},
        )
    ).mappings().first()

    desp_integridade = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE status = 'pago' AND pago_em IS NULL
                    ) AS pagas_sem_data,
                    COUNT(*) FILTER (
                        WHERE status = 'pendente'
                          AND vencimento IS NOT NULL
                          AND vencimento <=
                              (date_trunc('month', CAST(:mes AS date))
                               + INTERVAL '1 month - 1 day')::date
                    ) AS despesas_pendentes,
                    COALESCE(SUM(valor) FILTER (
                        WHERE status = 'pendente'
                          AND vencimento IS NOT NULL
                          AND vencimento <=
                              (date_trunc('month', CAST(:mes AS date))
                               + INTERVAL '1 month - 1 day')::date
                    ), 0) AS despesas_pendentes_valor
                FROM office_expenses
                WHERE deleted_at IS NULL
                  AND competencia = :comp
                  AND status != 'cancelado'
                """
            ),
            {"mes": mes_ref, "comp": competencia},
        )
    ).mappings().first()

    comprovantes = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) AS qtd, COALESCE(SUM(fp.valor), 0) AS total
                FROM fee_payments fp
                JOIN fees f ON f.id = fp.fee_id
                WHERE f.deleted_at IS NULL
                  AND fp.comprovante_doc_id IS NULL
                  AND date_trunc('month', fp.data_pagamento)
                      = date_trunc('month', CAST(:mes AS date))
                """
            ),
            {"mes": mes_ref},
        )
    ).mappings().first()

    itens: list[dict] = []

    def adicionar(codigo: str, severidade: str, titulo: str, qtd, *, valor=None, acao=None):
        quantidade = int(qtd or 0)
        if not quantidade:
            return
        itens.append({
            "codigo": codigo,
            "severidade": severidade,
            "titulo": titulo,
            "qtd": quantidade,
            "valor": _money(valor) if valor is not None else None,
            "acao": acao,
        })

    adicionar(
        "overpayment",
        "bloqueio",
        "Honorários com recebimento acima do valor contratado",
        fee_integridade["overpayment"],
        acao={"tab": "honorarios"},
    )
    adicionar(
        "pago_com_saldo",
        "bloqueio",
        "Honorários marcados como pagos ainda possuem saldo",
        fee_integridade["pago_com_saldo"],
        acao={"tab": "honorarios"},
    )
    adicionar(
        "despesa_paga_sem_data",
        "bloqueio",
        "Despesas pagas sem data efetiva de pagamento",
        desp_integridade["pagas_sem_data"],
        acao={"tab": "despesas"},
    )
    adicionar(
        "percentual_sem_base",
        "bloqueio",
        "Honorários percentuais da competência ainda sem base monetária",
        fee_integridade["percentuais_sem_base"],
        acao={"tab": "honorarios"},
    )
    adicionar(
        "recebiveis_pendentes",
        "revisao",
        "Contas a receber permanecem abertas até o fim da competência",
        fee_integridade["recebiveis_pendentes"],
        valor=fee_integridade["recebiveis_pendentes_valor"],
        acao={"tab": "honorarios"},
    )
    adicionar(
        "despesas_pendentes",
        "revisao",
        "Despesas da competência permanecem pendentes",
        desp_integridade["despesas_pendentes"],
        valor=desp_integridade["despesas_pendentes_valor"],
        acao={"tab": "despesas", "status": "pendente"},
    )
    adicionar(
        "pagamentos_sem_comprovante",
        "revisao",
        "Recebimentos do mês estão sem comprovante documental",
        comprovantes["qtd"],
        valor=comprovantes["total"],
        acao={"tab": "honorarios"},
    )
    adicionar(
        "legados_sem_subledger",
        "revisao",
        "Quitações históricas ainda não foram normalizadas no subledger",
        fee_integridade["legados_sem_subledger"],
        acao={"tab": "honorarios", "status": "pago"},
    )

    status, score = _classificar_fechamento(itens)
    snapshot = await demonstrativo_gerencial(competencia, db, cu)
    bloqueios = [item for item in itens if item["severidade"] == "bloqueio"]
    revisoes = [item for item in itens if item["severidade"] == "revisao"]

    return {
        "competencia": competencia,
        "modo": "pre_fechamento_read_only",
        "status": status,
        "score_integridade": score,
        "pode_fechar_persistente": len(bloqueios) == 0,
        "bloqueios": bloqueios,
        "revisoes": revisoes,
        "total_bloqueios": len(bloqueios),
        "total_revisoes": len(revisoes),
        "snapshot": snapshot,
        "dependencia_estrutural": None,
        "recomendacao": (
            "Corrija os bloqueios antes de fechar. Pendências de revisão podem "
            "permanecer abertas desde que sejam conscientemente conciliadas e "
            "documentadas no fechamento definitivo."
        ),
        "aviso": (
            "Pré-fechamento gerencial do EJC. Quando persistido pelo endpoint "
            "de fechamento, o mês fica bloqueado para mutações de caixa. "
            "Não substitui escrituração ou validação contábil."
        ),
    }
