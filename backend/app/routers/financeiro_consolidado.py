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
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.rate_limit import rate_limit
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.fee import FeeTipo
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


def _exigir_gestor_regras(cu: User) -> None:
    if cu.role.value not in _GESTOR_REGRAS:
        raise HTTPException(403, "Alteração de regras exige sócio ou administração")


def _competencia_atual(competencia: Optional[str]) -> str:
    if competencia:
        return competencia
    t = date.today()
    return f"{t.year}-{t.month:02d}"


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


@router.get("/comissoes", dependencies=[Depends(rate_limit("fin-comissoes", 60))])
async def listar_comissoes(
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    _exigir_financeiro(cu)
    rows = (
        await db.execute(
            text(
                """
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
                    cr.nome AS regra_nome,
                    a.withdrawal_id,
                    pw.status AS withdrawal_status,
                    pw.approved_at,
                    pw.paid_at,
                    CASE
                        WHEN a.valor_advogado <= 0 THEN 'sem_comissao'
                        WHEN a.withdrawal_id IS NULL THEN 'calculada'
                        WHEN pw.status = 'pendente' THEN 'a_aprovar'
                        WHEN pw.status = 'aprovado' THEN 'a_pagar'
                        WHEN pw.status = 'pago' THEN 'paga'
                        WHEN pw.status = 'rejeitado' THEN 'rejeitada'
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
                WHERE f.deleted_at IS NULL
                  AND a.valor_advogado > 0
                ORDER BY fp.data_pagamento DESC, a.created_at DESC
                LIMIT 500
                """
            )
        )
    ).mappings().all()
    data = [dict(r) for r in rows]
    termo = (search or "").strip().casefold()
    if termo:
        data = [
            r for r in data
            if termo in " ".join(
                str(r.get(k) or "")
                for k in ("advogado", "cliente", "caso", "numero_interno", "bruto_recebido", "valor_advogado")
            ).casefold()
        ]
    if status:
        data = [r for r in data if r.get("status") == status]

    all_rows = [dict(r) for r in rows]
    def total_por(st):
        return _money(sum((Decimal(str(r["valor_advogado"] or 0)) for r in all_rows if r["status"] == st), Decimal("0")))
    hoje = date.today()
    pago_mes = _money(sum((
        Decimal(str(r["valor_advogado"] or 0))
        for r in all_rows
        if r["status"] == "paga"
        and r["paid_at"] is not None
        and r["paid_at"].year == hoje.year
        and r["paid_at"].month == hoje.month
    ), Decimal("0")))
    escritorio = _money(sum((Decimal(str(r["valor_escritorio"] or 0)) for r in all_rows), Decimal("0")))
    return {
        "data": data,
        "resumo": {
            "calculada": total_por("calculada"),
            "a_aprovar": total_por("a_aprovar"),
            "a_pagar": total_por("a_pagar"),
            "paga_mes": pago_mes,
            "escritorio_total": escritorio,
        },
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
            "ref": f"commission:{row['fee_payment_id']}",
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
    sets, params = [], {"id": rule_id}
    for key, value in changes.items():
        sets.append(f"{campos[key]}=:{key}")
        params[key] = value
    sets.append("updated_at=NOW()")
    await db.execute(
        text(f"UPDATE commission_rules SET {', '.join(sets)} WHERE id=:id AND deleted_at IS NULL"),
        params,
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
        "pode_fechar_persistente": False,
        "bloqueios": bloqueios,
        "revisoes": revisoes,
        "total_bloqueios": len(bloqueios),
        "total_revisoes": len(revisoes),
        "snapshot": snapshot,
        "dependencia_estrutural": (
            "O fechamento imutável depende de migration própria após a revisão "
            "Alembic 156 atualmente reservada por outra frente."
        ),
        "recomendacao": (
            "Corrija os bloqueios antes de fechar. Pendências de revisão podem "
            "permanecer abertas desde que sejam conscientemente conciliadas e "
            "documentadas no fechamento definitivo."
        ),
        "aviso": (
            "Pré-fechamento gerencial do EJC. Não congela lançamentos e não "
            "substitui conciliação bancária, escrituração ou validação contábil."
        ),
    }
