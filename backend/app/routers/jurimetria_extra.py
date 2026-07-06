"""Jurimetria — endpoints complementares usados por Jurimetria.tsx.
   Implementação interna (sem ML externo): desfechos reais, distribuição por tribunal,
   benchmarks internos e predição por taxa histórica de êxito.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User


def _req_staff(cu: User = Depends(get_current_user)) -> User:
    # MESMO gate de papel de jurimetria.py (_is_staff = estagiario+): barra
    # cliente_externo/secretaria. Sem isso, qualquer usuário via métricas de êxito.
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Acesso restrito à equipe do escritório")
    return cu


def _req_socio(cu: User = Depends(get_current_user)) -> User:
    # Métricas de êxito consolidadas = mesmo nível do overview de jurimetria.py.
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(403, "Apenas sócios têm acesso a métricas de êxito")
    return cu


# Router inteiro exige, no mínimo, equipe (nunca cliente_externo).
router = APIRouter(prefix="/jurimetria", tags=["Jurimetria"],
                   dependencies=[Depends(_req_staff)])

_RESULTADO_LABEL = {
    "exito_total": "Êxito total", "exito_parcial": "Êxito parcial",
    "acordo": "Acordo", "improcedente": "Improcedente",
}


async def _por_resultado(db: AsyncSession, tribunal: Optional[str] = None):
    where = "status IN ('encerrado','arquivado') AND resultado IS NOT NULL AND deleted_at IS NULL"
    params = {}
    if tribunal:
        where += " AND tribunal = :trib"; params["trib"] = tribunal
    rows = (await db.execute(text(f"""
        SELECT resultado, COUNT(*) AS total FROM cases WHERE {where}
        GROUP BY resultado ORDER BY total DESC
    """), params)).mappings().all()
    total = sum(r["total"] for r in rows) or 0
    return total, [{
        "resultado": _RESULTADO_LABEL.get(r["resultado"], r["resultado"]),
        "resultado_raw": r["resultado"],
        "total": int(r["total"]),
        "pct": round(r["total"] / total * 100, 1) if total else 0,
    } for r in rows]


@router.get("/desfechos")
async def desfechos(db: AsyncSession = Depends(get_db), cu: User = Depends(_req_socio)):
    total, por_resultado = await _por_resultado(db)
    licoes = (await db.execute(text("""
        SELECT id, titulo, licoes_aprendidas, resultado FROM cases
        WHERE licoes_aprendidas IS NOT NULL AND licoes_aprendidas <> '' AND deleted_at IS NULL
        ORDER BY data_encerramento DESC NULLS LAST LIMIT 8
    """))).mappings().all()
    return {
        "total_encerrados": total,
        "por_resultado": por_resultado,
        "licoes_aprendidas": [dict(l) for l in licoes],
    }


@router.get("/ext/stats")
async def ext_stats(db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    trib = (await db.execute(text("""
        SELECT COALESCE(tribunal,'—') AS tribunal, COUNT(*) AS total
        FROM cases WHERE deleted_at IS NULL AND tribunal IS NOT NULL
        GROUP BY tribunal ORDER BY total DESC LIMIT 15
    """))).mappings().all()
    return {"por_tribunal": [{"tribunal": t["tribunal"], "total": int(t["total"])} for t in trib],
            "fonte": "base interna"}


@router.get("/ext/benchmarks")
async def ext_benchmarks(tribunal: Optional[str] = None,
                         db: AsyncSession = Depends(get_db), cu: User = Depends(_req_socio)):
    total, por_resultado = await _por_resultado(db, tribunal)
    tempo = (await db.execute(text("""
        SELECT COUNT(*) AS total_processos,
               ROUND(AVG(EXTRACT(EPOCH FROM (data_encerramento - created_at))/86400.0)) AS dias_medio
        FROM cases WHERE deleted_at IS NULL AND data_encerramento IS NOT NULL
          AND (CAST(:trib AS text) IS NULL OR tribunal = :trib)
    """), {"trib": tribunal})).mappings().first()
    return {
        "tribunal": tribunal or "todos",
        "tempo_tramitacao": {
            "total_processos": int(tempo["total_processos"] or 0),
            "dias_medio": int(tempo["dias_medio"] or 0),
        },
        "por_resultado": por_resultado,
        "fonte": "base interna",
    }


@router.get("/ext/predicao/provimento")
async def predicao_provimento(classe: str = Query(""), tribunal: str = Query(""),
                              dias_estimados: int = Query(0),
                              db: AsyncSession = Depends(get_db), cu: User = Depends(_req_socio)):
    """Predição por taxa histórica de êxito (heurística interna, não ML)."""
    total, por_resultado = await _por_resultado(db, tribunal or None)
    favoraveis = sum(r["total"] for r in por_resultado if r["resultado_raw"] in ("exito_total", "exito_parcial", "acordo"))
    prob = round(favoraveis / total * 100, 1) if total else None
    return {
        "classe": classe, "tribunal": tribunal,
        "amostra": total,
        "probabilidade_provimento": prob,
        "metodo": "taxa histórica interna" if total else "amostra insuficiente",
        "confianca": "baixa" if total < 10 else "média" if total < 50 else "alta",
        "dias_estimados": dias_estimados or None,
    }


@router.post("/ext/predicao/treinar")
async def predicao_treinar(tribunal: str = Query(""), cu: User = Depends(get_current_user)):
    return {"ok": True, "detail": "Predição usa taxa histórica interna em tempo real — não requer treinamento de modelo."}


@router.post("/ext/ingerir/datajud")
async def ingerir_datajud(tribunal: str = Query(""), data_inicio: str = Query(""), limite: int = Query(500),
                          cu: User = Depends(get_current_user)):
    return {"ok": False, "detail": "Ingestão DataJud externa não habilitada neste ambiente. Estatísticas usam a base interna."}
