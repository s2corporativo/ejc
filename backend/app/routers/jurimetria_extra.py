"""Jurimetria — métricas complementares usadas por Jurimetria.tsx.

Fonte atual: EXCLUSIVAMENTE a base interna de casos do escritório. Os caminhos
`/ext/*` são mantidos como aliases legados para não quebrar consumidores, mas
não representam DataJud/STJ. Novos consumidores devem usar `/interno/*`.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL, requer_equipe_juridica
from app.models.user import User
from app.services.jurimetria import MIN_AMOSTRA


def _req_staff(cu: User = Depends(get_current_user)) -> User:
    # MESMO gate de papel de jurimetria.py (_is_staff = EQUIPE_JURIDICA).
    # Issue #694: allowlist EXATA — financeiro NÃO passa aqui mesmo com
    # ROLE_LEVEL acima de estagiario.
    requer_equipe_juridica(cu, "Acesso restrito à equipe do escritório")
    return cu


def _req_socio(cu: User = Depends(get_current_user)) -> User:
    # Métricas de êxito consolidadas = mesmo nível do overview de jurimetria.py.
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(403, "Apenas sócios têm acesso a métricas de êxito")
    return cu


router = APIRouter(
    prefix="/jurimetria",
    tags=["Jurimetria"],
    dependencies=[Depends(_req_staff)],
)

_RESULTADO_LABEL = {
    "exito_total": "Êxito total",
    "exito_parcial": "Êxito parcial",
    "acordo": "Acordo",
    "improcedente": "Improcedente",
}


async def _por_resultado(db: AsyncSession, tribunal: Optional[str] = None):
    where = (
        "status IN ('encerrado','arquivado') "
        "AND resultado IS NOT NULL AND deleted_at IS NULL"
    )
    params = {}
    if tribunal:
        where += " AND tribunal = :trib"
        params["trib"] = tribunal
    rows = (
        await db.execute(
            text(
                f"""
                SELECT resultado, COUNT(*) AS total
                FROM cases
                WHERE {where}
                GROUP BY resultado
                ORDER BY total DESC
                """
            ),
            params,
        )
    ).mappings().all()
    total = sum(r["total"] for r in rows) or 0
    return total, [
        {
            "resultado": _RESULTADO_LABEL.get(r["resultado"], r["resultado"]),
            "resultado_raw": r["resultado"],
            "total": int(r["total"]),
            "pct": round(r["total"] / total * 100, 1) if total else 0,
        }
        for r in rows
    ]


@router.get("/desfechos")
async def desfechos(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_socio),
):
    total, por_resultado = await _por_resultado(db)
    licoes = (
        await db.execute(
            text(
                """
                SELECT id, titulo, licoes_aprendidas, resultado
                FROM cases
                WHERE licoes_aprendidas IS NOT NULL
                  AND licoes_aprendidas <> ''
                  AND deleted_at IS NULL
                ORDER BY data_encerramento DESC NULLS LAST
                LIMIT 8
                """
            )
        )
    ).mappings().all()
    return {
        "total_encerrados": total,
        "por_resultado": por_resultado,
        "licoes_aprendidas": [dict(l) for l in licoes],
        "fonte": "base interna",
    }


@router.get("/ext/stats", deprecated=True)
@router.get("/interno/stats")
async def stats_internos(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    trib = (
        await db.execute(
            text(
                """
                SELECT COALESCE(tribunal,'—') AS tribunal, COUNT(*) AS total
                FROM cases
                WHERE deleted_at IS NULL AND tribunal IS NOT NULL
                GROUP BY tribunal
                ORDER BY total DESC
                LIMIT 15
                """
            )
        )
    ).mappings().all()
    return {
        "por_tribunal": [
            {"tribunal": t["tribunal"], "total": int(t["total"])} for t in trib
        ],
        "fonte": "base interna",
        "escopo": "casos do escritório",
        "externo_habilitado": False,
    }


@router.get("/ext/benchmarks", deprecated=True)
@router.get("/interno/benchmarks")
async def benchmarks_internos(
    tribunal: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_socio),
):
    total, por_resultado = await _por_resultado(db, tribunal)
    tempo = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS total_processos,
                    ROUND(AVG(EXTRACT(EPOCH FROM (data_encerramento - created_at))/86400.0)) AS dias_medio,
                    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                        ORDER BY EXTRACT(EPOCH FROM (data_encerramento - created_at))/86400.0
                    )) AS dias_mediana
                FROM cases
                WHERE deleted_at IS NULL
                  AND data_encerramento IS NOT NULL
                  AND (CAST(:trib AS text) IS NULL OR tribunal = :trib)
                """
            ),
            {"trib": tribunal},
        )
    ).mappings().first()
    dias_medio = int(tempo["dias_medio"] or 0)
    dias_mediana = int(tempo["dias_mediana"] or 0)
    return {
        "tribunal": tribunal or "todos",
        "tempo_tramitacao": {
            "total_processos": int(tempo["total_processos"] or 0),
            # Campo canônico novo + alias legado para consumidores antigos.
            "media_dias": dias_medio,
            "mediana_dias": dias_mediana,
            "dias_medio": dias_medio,
        },
        "por_resultado": por_resultado,
        "total_encerrados_com_resultado": total,
        "fonte": "base interna",
        "escopo": "casos do escritório",
        "externo_habilitado": False,
    }


@router.get("/ext/predicao/provimento", deprecated=True)
@router.get("/interno/analise-prospectiva")
async def analise_prospectiva(
    classe: str = Query(""),
    tribunal: str = Query(""),
    dias_estimados: int = Query(0),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_socio),
):
    """Taxa histórica interna para apoio prospectivo — não é predição de ML.

    A tabela `cases` não possui classe TPU; a classe recebida é somente contexto
    exibido ao usuário (`classe_filtrada=False`) e NÃO entra no cálculo.

    A taxa favorável usa apenas desfechos DECIDIDOS:
    `exito_total + exito_parcial` / (`exito_total + exito_parcial + improcedente`).
    Acordos são mostrados separadamente e não são tratados como vitória judicial.
    Outros resultados não classificáveis também ficam fora do denominador.
    """
    total_encerrados, por_resultado = await _por_resultado(db, tribunal or None)
    contagens = {r["resultado_raw"]: int(r["total"]) for r in por_resultado}
    favoraveis = contagens.get("exito_total", 0) + contagens.get("exito_parcial", 0)
    desfavoraveis = contagens.get("improcedente", 0)
    acordos = contagens.get("acordo", 0)
    decididos = favoraveis + desfavoraveis

    escopo = (
        "histórico interno do tribunal (classe não filtrada)"
        if tribunal
        else "histórico interno geral (tribunal e classe não filtrados)"
    )

    base = {
        "classe": classe,
        "tribunal": tribunal,
        "classe_filtrada": False,
        "amostra": decididos,
        "amostra_decidida": decididos,
        "total_encerrados": total_encerrados,
        "favoraveis": favoraveis,
        "desfavoraveis": desfavoraveis,
        "acordos": acordos,
        "dias_estimados": dias_estimados or None,
        "fonte": "base interna",
        "escopo": escopo,
        "is_estimativa": True,
        "nao_e_previsao_judicial": True,
    }

    if decididos < MIN_AMOSTRA:
        return {
            **base,
            "taxa_historica_favoravel": None,
            # Alias legado; preservado para não quebrar consumidor antigo.
            "probabilidade_provimento": None,
            "metodo": "amostra decidida insuficiente",
            "confianca": "insuficiente",
            "aviso": (
                f"Há {decididos} caso(s) com desfecho decidido no escopo — abaixo "
                f"do piso de {MIN_AMOSTRA}. Nenhuma taxa é informada. "
                "Acordos são exibidos separadamente e não contam como êxito judicial."
            ),
        }

    taxa = round(favoraveis / decididos * 100, 1)
    aviso_classe = (
        f" A classe TPU informada ('{classe}') é apenas referência e não entrou "
        "no cálculo, pois a base interna não possui esse filtro."
        if classe
        else " A base interna não possui filtro por classe TPU."
    )
    return {
        **base,
        "taxa_historica_favoravel": taxa,
        # Alias legado, semanticamente documentado como taxa histórica.
        "probabilidade_provimento": taxa,
        "metodo": f"taxa histórica interna — {escopo}",
        "confianca": "baixa" if decididos < 10 else "média" if decididos < 50 else "alta",
        "aviso": (
            "Indicador descritivo do histórico do escritório; não representa "
            "probabilidade estatisticamente calibrada de decisão futura."
            + aviso_classe
        ),
    }


@router.post("/ext/predicao/treinar", deprecated=True)
async def predicao_treinar(
    tribunal: str = Query(""),
    cu: User = Depends(get_current_user),
):
    return {
        "ok": True,
        "detail": (
            "A análise usa taxa histórica interna em tempo real; não há modelo "
            "preditivo a treinar."
        ),
        "tribunal": tribunal or None,
        "fonte": "base interna",
    }


@router.post("/ext/ingerir/datajud")
async def ingerir_datajud(
    tribunal: str = Query(""),
    data_inicio: str = Query(""),
    limite: int = Query(500),
    cu: User = Depends(get_current_user),
):
    return {
        "ok": False,
        "detail": (
            "Ingestão DataJud externa não habilitada neste ambiente. "
            "As métricas disponíveis nesta página usam somente a base interna."
        ),
        "tribunal": tribunal or None,
        "data_inicio": data_inicio or None,
        "limite": limite,
        "fonte": "base interna",
    }


@router.get("/cobertura-rag")
async def cobertura_rag(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_socio),
):
    """Mapa agregado do que está efetivamente armazenado no RAG atual."""
    from app.services.rag_coverage import medir_cobertura_rag

    return await medir_cobertura_rag(db, mg_jec_only=False)


@router.get("/cobertura-mg-jec")
async def cobertura_mg_jec(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_socio),
):
    """Cobertura mensurável MG/JEC, incluindo TJMG automático sem duplicação."""
    from app.services.rag_coverage import medir_cobertura_rag

    return await medir_cobertura_rag(db, mg_jec_only=True)
