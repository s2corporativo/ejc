"""
services/precificacao_service.py
Motor de precificação de honorários — consulta pricing_rules com filtros e calcula
estimativas de honorários conforme tabela OAB/MG.
"""
from __future__ import annotations
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def listar_tabela(
    db: AsyncSession,
    area: Optional[str] = None,
    complexity: Optional[str] = None,
    is_active: bool = True,
) -> list[dict]:
    filters = ["is_active = :active"]
    params: dict = {"active": is_active}
    if area:
        filters.append("LOWER(area) = LOWER(:area)")
        params["area"] = area
    if complexity:
        filters.append("complexity = :complexity")
        params["complexity"] = complexity

    where = " AND ".join(filters)
    # SQL literal com bind params; a regra marca todo text(), sem olhar
    # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    r = await db.execute(text(f"""
        SELECT id, area, case_type, complexity, fee_type,
               base_amount, percentage_of_value, min_amount, max_amount,
               exit_percentage, oab_reference, notes
        FROM pricing_rules
        WHERE {where}
        ORDER BY area, complexity
    """), params)
    rows = r.fetchall()
    return [dict(row._mapping) for row in rows]


async def calcular_honorario(
    db: AsyncSession,
    rule_id: str,
    causa_valor: Optional[float] = None,
) -> dict:
    r = await db.execute(
        text("SELECT * FROM pricing_rules WHERE id = :id AND is_active = TRUE"),
        {"id": rule_id},
    )
    rule = r.fetchone()
    if not rule:
        return {"erro": "Regra não encontrada ou inativa"}

    row = dict(rule._mapping)
    base = float(row.get("base_amount") or 0)
    pct = float(row.get("percentage_of_value") or 0)
    min_amt = float(row.get("min_amount") or 0)
    max_amt = float(row.get("max_amount") or 0) if row.get("max_amount") else None
    exit_pct = float(row.get("exit_percentage") or 0)

    estimado = base
    componente_percentual = 0.0

    if pct and causa_valor:
        componente_percentual = causa_valor * (pct / 100)
        if row["fee_type"] in ("percentual", "misto"):
            estimado = componente_percentual if row["fee_type"] == "percentual" else base + componente_percentual

    if min_amt and estimado < min_amt:
        estimado = min_amt
    if max_amt and estimado > max_amt:
        estimado = max_amt

    honorario_exito = (causa_valor or 0) * (exit_pct / 100) if exit_pct else None

    return {
        "rule_id": rule_id,
        "area": row["area"],
        "case_type": row["case_type"],
        "complexity": row["complexity"],
        "fee_type": row["fee_type"],
        "estimado_honorarios": round(estimado, 2),
        "componente_percentual": round(componente_percentual, 2),
        "honorario_exito": round(honorario_exito, 2) if honorario_exito else None,
        "min_amount": min_amt,
        "max_amount": max_amt,
        "oab_reference": row.get("oab_reference"),
        "causa_valor_informado": causa_valor,
    }


async def criar_regra(db: AsyncSession, data: dict, user_id: str) -> dict:
    r = await db.execute(text("""
        INSERT INTO pricing_rules
            (id, area, case_type, complexity, fee_type, base_amount,
             percentage_of_value, min_amount, max_amount, exit_percentage,
             oab_reference, notes, created_by, is_active)
        VALUES
            (gen_random_uuid()::text, :area, :case_type, :complexity, :fee_type,
             :base_amount, :pct, :min_amt, :max_amt, :exit_pct,
             :oab_ref, :notes, :created_by, TRUE)
        RETURNING id
    """), {
        "area":        data["area"],
        "case_type":   data["case_type"],
        "complexity":  data.get("complexity", "media"),
        "fee_type":    data.get("fee_type", "fixo"),
        "base_amount": data.get("base_amount"),
        "pct":         data.get("percentage_of_value"),
        "min_amt":     data.get("min_amount"),
        "max_amt":     data.get("max_amount"),
        "exit_pct":    data.get("exit_percentage"),
        "oab_ref":     data.get("oab_reference"),
        "notes":       data.get("notes"),
        "created_by":  user_id,
    })
    await db.commit()
    return {"id": r.scalar(), "created": True}
