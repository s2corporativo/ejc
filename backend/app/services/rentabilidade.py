# ── app/services/rentabilidade.py ────────────────────────────────────────────
# Rentabilidade por caso (Bloco D) — confronta receita RECEBIDA (honorários
# pagos) com o custo das horas lançadas (time_entries × custo_hora do advogado).
# Honestidade: horas de profissionais SEM custo_hora definido são contabilizadas
# à parte e sinalizam `custo_incompleto`, evitando margem enganosamente alta.
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ROLE_LEVEL
from app.models.user import User
from app.models.case import Case, CaseStatus
from app.models.fee import Fee, FeeStatus
from app.models.time_entry import TimeEntry


def pode_ver_todos(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["admin"]


def _filtro_acesso(user: User):
    if pode_ver_todos(user):
        return None
    return (Case.advogado_responsavel_id == user.id) | (Case.advogado_auxiliar_id == user.id)


async def ranking_rentabilidade(db: AsyncSession, user: User, limit: int = 50) -> dict:
    """Rentabilidade por caso (receita recebida − custo de horas). Escopo por perfil."""
    # casos no escopo
    q = select(Case).where(Case.deleted_at.is_(None))
    filtro = _filtro_acesso(user)
    if filtro is not None:
        q = q.where(filtro)
    casos = (await db.execute(q.limit(500))).scalars().all()
    if not casos:
        return {"total_casos": 0, "casos": [], "consolidado": None}
    case_ids = [c.id for c in casos]

    # receita recebida por caso (honorários pagos)
    receita: dict[str, Decimal] = {cid: Decimal("0") for cid in case_ids}
    rows = (await db.execute(
        select(Fee.case_id, func.coalesce(func.sum(Fee.valor), 0)).where(
            Fee.case_id.in_(case_ids), Fee.deleted_at.is_(None),
            Fee.status == FeeStatus.pago,
        ).group_by(Fee.case_id)
    )).all()
    for cid, total in rows:
        receita[cid] = Decimal(str(total or 0))

    # mapa custo_hora por usuário
    custo_hora: dict[str, Decimal | None] = {}
    for uid, ch in (await db.execute(select(User.id, User.custo_hora))).all():
        custo_hora[uid] = Decimal(str(ch)) if ch is not None else None

    # horas por caso (minutos), separando com/sem custo_hora definido
    custo: dict[str, Decimal] = {cid: Decimal("0") for cid in case_ids}
    min_total: dict[str, int] = {cid: 0 for cid in case_ids}
    min_sem_custo: dict[str, int] = {cid: 0 for cid in case_ids}
    te = (await db.execute(
        select(TimeEntry.case_id, TimeEntry.user_id, TimeEntry.minutos).where(
            TimeEntry.case_id.in_(case_ids), TimeEntry.deleted_at.is_(None)
        )
    )).all()
    for cid, uid, minutos in te:
        minutos = minutos or 0
        min_total[cid] += minutos
        ch = custo_hora.get(uid)
        if ch is None:
            min_sem_custo[cid] += minutos
        else:
            custo[cid] += (Decimal(minutos) / Decimal(60)) * ch

    resultado = []
    tot_receita = tot_custo = Decimal("0")
    for c in casos:
        rec = receita[c.id].quantize(Decimal("0.01"))
        cus = custo[c.id].quantize(Decimal("0.01"))
        lucro = (rec - cus).quantize(Decimal("0.01"))
        incompleto = min_sem_custo[c.id] > 0
        margem = float((lucro / rec * 100).quantize(Decimal("0.1"))) if rec > 0 else None
        tot_receita += rec
        tot_custo += cus
        resultado.append({
            "case_id": c.id,
            "numero_interno": c.numero_interno,
            "titulo": c.titulo,
            "status": c.status.value,
            "receita_recebida": float(rec),
            "custo_horas": float(cus),
            "lucro": float(lucro),
            "margem_pct": margem,
            "horas_lancadas": round(min_total[c.id] / 60, 1),
            "custo_incompleto": incompleto,
            "obs": ("Há horas de profissionais sem custo_hora definido — "
                    "custo subestimado." if incompleto else ""),
        })
    resultado.sort(key=lambda x: x["lucro"])

    tot_lucro = (tot_receita - tot_custo).quantize(Decimal("0.01"))
    return {
        "escopo": "todos os casos" if pode_ver_todos(user) else "casos do usuário",
        "criterio": "receita = honorários PAGOS; custo = horas lançadas × custo_hora",
        "total_casos": len(resultado),
        "consolidado": {
            "receita_recebida": float(tot_receita.quantize(Decimal("0.01"))),
            "custo_horas": float(tot_custo.quantize(Decimal("0.01"))),
            "lucro": float(tot_lucro),
            "margem_pct": float((tot_lucro / tot_receita * 100).quantize(Decimal("0.1")))
                          if tot_receita > 0 else None,
        },
        "casos": resultado[:limit],
        "nota": "Custo considera apenas horas lançadas no time_entry. "
                "Não inclui custos fixos/rateios do escritório.",
    }


async def ranking_por_area(db: AsyncSession, user: User) -> dict:
    """ROI por área jurídica — agrupa casos por ramo e calcula margem por área."""
    from app.models.caso_area import CasoArea
    from collections import defaultdict
    from decimal import Decimal

    # Pega ranking por caso primeiro
    data = await ranking_rentabilidade(db, user, limit=500)
    casos_map = {c["case_id"]: c for c in data.get("casos", [])}
    if not casos_map:
        return {"areas": [], "total_geral": data.get("consolidado")}

    # Busca mapeamento case_id → área (campo principal=True)
    case_ids = list(casos_map.keys())
    areas_rows = (await db.execute(
        select(CasoArea.case_id, CasoArea.area).where(
            CasoArea.case_id.in_(case_ids),
            CasoArea.principal.is_(True),
        )
    )).all()
    area_map: dict[str, str] = {cid: area for cid, area in areas_rows}

    # Casos sem área primária explícita → busca ramo do Case
    sem_area = [cid for cid in case_ids if cid not in area_map]
    if sem_area:
        ramos = (await db.execute(
            select(Case.id, Case.ramo).where(Case.id.in_(sem_area), Case.ramo.isnot(None))
        )).all()
        for cid, ramo in ramos:
            area_map[cid] = ramo

    # Agrupa por área
    grupos: dict[str, dict] = defaultdict(lambda: {
        "receita": Decimal("0"), "custo": Decimal("0"),
        "casos": 0, "casos_lucro": 0, "casos_prejuizo": 0,
    })
    for cid, c in casos_map.items():
        area = area_map.get(cid, "sem_área")
        g = grupos[area]
        g["receita"]  += Decimal(str(c["receita_recebida"]))
        g["custo"]    += Decimal(str(c["custo_horas"]))
        g["casos"]    += 1
        if c["lucro"] >= 0:
            g["casos_lucro"] += 1
        else:
            g["casos_prejuizo"] += 1

    resultado = []
    for area, g in sorted(grupos.items(), key=lambda x: float(x[1]["receita"]), reverse=True):
        lucro = g["receita"] - g["custo"]
        margem = float(lucro / g["receita"] * 100) if g["receita"] > 0 else None
        resultado.append({
            "area": area,
            "casos": g["casos"],
            "receita_recebida": float(g["receita"].quantize(Decimal("0.01"))),
            "custo_horas": float(g["custo"].quantize(Decimal("0.01"))),
            "lucro": float(lucro.quantize(Decimal("0.01"))),
            "margem_pct": round(margem, 1) if margem is not None else None,
            "casos_lucro": g["casos_lucro"],
            "casos_prejuizo": g["casos_prejuizo"],
        })

    tot_rec = sum(Decimal(str(r["receita_recebida"])) for r in resultado)
    tot_luc = sum(Decimal(str(r["lucro"])) for r in resultado)
    return {
        "areas": resultado,
        "total_areas": len(resultado),
        "total_geral": {
            "receita_recebida": float(tot_rec.quantize(Decimal("0.01"))),
            "lucro": float(tot_luc.quantize(Decimal("0.01"))),
            "margem_pct": round(float(tot_luc / tot_rec * 100), 1) if tot_rec > 0 else None,
        },
    }
