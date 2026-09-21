# ── app/routers/jurimetria.py ──────────────────────────────────────────────────
# Jurimetria — métricas de desempenho por área, magistrado, tribunal e tese.
# Dados baseados em tese_caso_links (resultados registrados) + cases.
# Acesso: staff (advogado+); overview de alto nível: sócio+.
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case as sa_case
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import EQUIPE_JURIDICA, ROLE_LEVEL, get_current_user
from app.models.case import Case
from app.models.tese import Tese, TeseCasoLink, TeseStatus
from app.models.user import User

# ── Prelúdio do módulo consolidado (jurimetria_extra) ───────────────────────
# Cobertura APENAS do bloco `CONSOLIDAÇÃO 12/08/2026` abaixo; não mexer sem
# checar o bloco.
from app.core.security import requer_equipe_juridica as _je_requer_equipe_juridica
from app.services.jurimetria import (
    MIN_AMOSTRA as _je_MIN_AMOSTRA,
    RESULTADOS_DESFAVORAVEIS as _RESULTADOS_DESFAVORAVEIS,
    RESULTADOS_FAVORAVEIS as _RESULTADOS_FAVORAVEIS,
    intervalo_wilson as _intervalo_wilson,
)


def _req_staff(cu: User = Depends(get_current_user)) -> User:
    # MESMO gate de papel de jurimetria.py (_is_staff = EQUIPE_JURIDICA).
    # Issue #694: allowlist EXATA — financeiro NÃO passa aqui mesmo com
    # ROLE_LEVEL acima de estagiario.
    _je_requer_equipe_juridica(cu, "Acesso restrito à equipe do escritório")
    return cu


def _req_socio(cu: User = Depends(get_current_user)) -> User:
    # Métricas de êxito consolidadas = mesmo nível do overview de jurimetria.py.
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(403, "Apenas sócios têm acesso a métricas de êxito")
    return cu


router = APIRouter(prefix="/jurimetria", tags=["Jurimetria"])


_RESULTADOS_DECIDIDOS = ("procedente", "improcedente")


def _is_staff(user: User) -> bool:
    # Issue #694: allowlist EXATA — financeiro não acessa métricas de
    # jurimetria, mesmo com ROLE_LEVEL acima de estagiario.
    return user.role.value in EQUIPE_JURIDICA


def _is_socio(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]


def _taxa_decidida(venceu: int, perdeu: int) -> float | None:
    """Taxa descritiva somente entre resultados decididos.

    `acordo` e `pendente` não entram no denominador: acordo não é vitória
    judicial e pendência não é desfecho. O total bruto continua exposto para
    transparência da amostra.
    """
    decididos = int(venceu or 0) + int(perdeu or 0)
    return round(int(venceu or 0) / decididos, 4) if decididos else None


def _ic_decidida(venceu: int, perdeu: int) -> dict | None:
    """IC95% de Wilson no mesmo domínio 0..1 de taxa_sucesso."""
    decididos = int(venceu or 0) + int(perdeu or 0)
    ic = _intervalo_wilson(int(venceu or 0), decididos)
    if not ic:
        return None
    return {
        "inferior": round(ic["inferior"] / 100.0, 4),
        "superior": round(ic["superior"] / 100.0, 4),
        "nivel": ic["nivel"],
        "metodo": ic["metodo"],
    }


@router.get("/overview")
async def overview(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Panorama dos vínculos de tese com denominador estatístico explícito."""
    if not _is_socio(cu):
        raise HTTPException(403, "Apenas sócios têm acesso ao painel de jurimetria")

    tot_row = (
        await db.execute(
            select(
                func.count(TeseCasoLink.id).label("total"),
                func.count(
                    sa_case((TeseCasoLink.resultado == "procedente", 1))
                ).label("venceu"),
                func.count(
                    sa_case((TeseCasoLink.resultado == "improcedente", 1))
                ).label("perdeu"),
                func.count(sa_case((TeseCasoLink.resultado == "acordo", 1))).label(
                    "acordo"
                ),
                func.count(sa_case((TeseCasoLink.resultado == "pendente", 1))).label(
                    "pendente"
                ),
            )
        )
    ).one()

    total = int(tot_row.total or 0)
    venceu = int(tot_row.venceu or 0)
    perdeu = int(tot_row.perdeu or 0)
    acordo = int(tot_row.acordo or 0)
    pendente = int(tot_row.pendente or 0)
    decididos = venceu + perdeu

    total_teses = (
        await db.execute(
            select(func.count(Tese.id)).where(
                Tese.deleted_at.is_(None), Tese.status == TeseStatus.ativa
            )
        )
    ).scalar() or 0

    total_casos = (
        await db.execute(select(func.count(Case.id)).where(Case.deleted_at.is_(None)))
    ).scalar() or 0

    return {
        "total_vinculos": total,
        "decididos": decididos,
        "venceu": venceu,
        "perdeu": perdeu,
        "acordo": acordo,
        "pendente": pendente,
        "taxa_sucesso_geral": _taxa_decidida(venceu, perdeu),
        "intervalo_confianca_95": _ic_decidida(venceu, perdeu),
        "taxa_sucesso_denominador": "procedente + improcedente",
        "acordo_excluido_da_taxa": True,
        "pendente_excluido_da_taxa": True,
        "total_teses_ativas": total_teses,
        "total_casos": total_casos,
        "fonte": "base interna — vínculos de teses",
    }


@router.get("/por-area")
async def por_area(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Taxa de sucesso por área, calculada somente entre decisões."""
    if not _is_staff(cu):
        raise HTTPException(403)

    rows = (
        await db.execute(
            select(
                Tese.area_juridica,
                func.count(TeseCasoLink.id).label("total"),
                func.count(
                    sa_case((TeseCasoLink.resultado == "procedente", 1))
                ).label("venceu"),
                func.count(
                    sa_case((TeseCasoLink.resultado == "improcedente", 1))
                ).label("perdeu"),
                func.count(sa_case((TeseCasoLink.resultado == "acordo", 1))).label(
                    "acordo"
                ),
                func.count(sa_case((TeseCasoLink.resultado == "pendente", 1))).label(
                    "pendente"
                ),
            )
            .join(Tese, Tese.id == TeseCasoLink.tese_id)
            .where(Tese.deleted_at.is_(None))
            .group_by(Tese.area_juridica)
            .order_by(func.count(TeseCasoLink.id).desc())
            .limit(30)
        )
    ).all()

    resultado = []
    for r in rows:
        venceu = int(r.venceu or 0)
        perdeu = int(r.perdeu or 0)
        resultado.append(
            {
                "area": r.area_juridica or "Não classificada",
                "total": int(r.total or 0),
                "decididos": venceu + perdeu,
                "venceu": venceu,
                "perdeu": perdeu,
                "acordo": int(r.acordo or 0),
                "pendente": int(r.pendente or 0),
                "taxa_sucesso": _taxa_decidida(venceu, perdeu),
                "intervalo_confianca_95": _ic_decidida(venceu, perdeu),
            }
        )
    return resultado


@router.get("/por-magistrado", deprecated=True)
async def por_magistrado(
    area: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Métrica desabilitada até existir magistrado real no processo/decisão.

    O campo legado Tese.magistrado descreve metadado da tese, não prova quem
    julgou cada caso. Publicar taxa comportamental com essa origem seria
    semanticamente incorreto. A rota permanece apenas para compatibilidade.
    """
    if not _is_staff(cu):
        raise HTTPException(403)
    raise HTTPException(
        status_code=409,
        detail=(
            "Métrica por magistrado desabilitada: a base atual não possui vínculo "
            "confiável processo/decisão→magistrado. Use tribunal/comarca/assunto."
        ),
    )

@router.get("/por-tribunal")
async def por_tribunal(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Desempenho agrupado por tribunal, com acordo fora da taxa judicial."""
    if not _is_staff(cu):
        raise HTTPException(403)

    rows = (
        await db.execute(
            select(
                Tese.tribunal,
                func.count(TeseCasoLink.id).label("total"),
                func.count(
                    sa_case((TeseCasoLink.resultado == "procedente", 1))
                ).label("venceu"),
                func.count(
                    sa_case((TeseCasoLink.resultado == "improcedente", 1))
                ).label("perdeu"),
                func.count(sa_case((TeseCasoLink.resultado == "acordo", 1))).label(
                    "acordo"
                ),
                func.count(sa_case((TeseCasoLink.resultado == "pendente", 1))).label(
                    "pendente"
                ),
            )
            .join(Tese, Tese.id == TeseCasoLink.tese_id)
            .where(Tese.deleted_at.is_(None), Tese.tribunal.isnot(None))
            .group_by(Tese.tribunal)
            .order_by(func.count(TeseCasoLink.id).desc())
            .limit(limit)
        )
    ).all()

    resultado = []
    for r in rows:
        venceu = int(r.venceu or 0)
        perdeu = int(r.perdeu or 0)
        resultado.append(
            {
                "tribunal": r.tribunal,
                "total": int(r.total or 0),
                "decididos": venceu + perdeu,
                "venceu": venceu,
                "perdeu": perdeu,
                "acordo": int(r.acordo or 0),
                "pendente": int(r.pendente or 0),
                "taxa_sucesso": _taxa_decidida(venceu, perdeu),
                "intervalo_confianca_95": _ic_decidida(venceu, perdeu),
            }
        )
    return resultado


@router.get("/por-tese")
async def por_tese(
    area: Optional[str] = Query(None),
    min_usos: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Métricas por tese derivadas da fonte canônica tese_caso_links."""
    if not _is_staff(cu):
        raise HTTPException(403)

    q = (
        select(
            Tese.id,
            Tese.titulo,
            Tese.area_juridica,
            Tese.tribunal,
            func.count(TeseCasoLink.id).label("total"),
            func.count(
                sa_case((TeseCasoLink.resultado == "procedente", 1))
            ).label("venceu"),
            func.count(
                sa_case((TeseCasoLink.resultado == "improcedente", 1))
            ).label("perdeu"),
            func.count(
                sa_case((TeseCasoLink.resultado == "acordo", 1))
            ).label("acordo"),
            func.count(
                sa_case((TeseCasoLink.resultado == "pendente", 1))
            ).label("pendente"),
        )
        .join(TeseCasoLink, TeseCasoLink.tese_id == Tese.id)
        .where(
            Tese.deleted_at.is_(None),
            Tese.status == TeseStatus.ativa,
        )
    )
    if area:
        q = q.where(Tese.area_juridica.ilike(f"%{area}%"))
    q = q.group_by(Tese.id, Tese.titulo, Tese.area_juridica, Tese.tribunal)
    rows = (await db.execute(q)).all()

    resultado = []
    for r in rows:
        total = int(r.total or 0)
        if total < min_usos:
            continue
        venceu = int(r.venceu or 0)
        perdeu = int(r.perdeu or 0)
        decididos = venceu + perdeu
        resultado.append(
            {
                "id": r.id,
                "titulo": r.titulo,
                "area_juridica": r.area_juridica,
                "tribunal": r.tribunal,
                "vezes_usada": total,
                "vezes_venceu": venceu,
                "vezes_perdeu": perdeu,
                "acordo": int(r.acordo or 0),
                "pendente": int(r.pendente or 0),
                "decididos": decididos,
                "taxa_sucesso": _taxa_decidida(venceu, perdeu),
                "intervalo_confianca_95": _ic_decidida(venceu, perdeu),
                "amostra_suficiente": decididos >= _je_MIN_AMOSTRA,
                "fonte_metrica": "tese_caso_links",
                "denominador": "procedente + improcedente",
            }
        )

    resultado.sort(
        key=lambda item: (
            item["taxa_sucesso"] is not None,
            item["taxa_sucesso"] or -1,
            item["decididos"],
        ),
        reverse=True,
    )
    return resultado[:limit]

@router.get("/tendencias")
async def tendencias(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Vínculos de tese registrados por mês — últimos 12 meses."""
    if not _is_socio(cu):
        raise HTTPException(403)

    rows = (
        await db.execute(
            text(
                """
                SELECT
                    TO_CHAR(DATE_TRUNC('month', created_at), 'YYYY-MM') AS mes,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE resultado = 'procedente') AS venceu,
                    COUNT(*) FILTER (WHERE resultado = 'improcedente') AS perdeu,
                    COUNT(*) FILTER (WHERE resultado = 'acordo') AS acordo,
                    COUNT(*) FILTER (WHERE resultado = 'pendente') AS pendente
                FROM tese_caso_links
                WHERE created_at >= NOW() - INTERVAL '12 months'
                GROUP BY DATE_TRUNC('month', created_at)
                ORDER BY DATE_TRUNC('month', created_at)
                """
            )
        )
    ).all()

    return [
        {
            "mes": r.mes,
            "total": int(r.total or 0),
            "decididos": int(r.venceu or 0) + int(r.perdeu or 0),
            "venceu": int(r.venceu or 0),
            "perdeu": int(r.perdeu or 0),
            "acordo": int(r.acordo or 0),
            "pendente": int(r.pendente or 0),
            "taxa": _taxa_decidida(r.venceu, r.perdeu),
            "intervalo_confianca_95": _ic_decidida(r.venceu, r.perdeu),
        }
        for r in rows
    ]


@router.post("/predicao-exito", deprecated=True)
@router.post("/analise-prospectiva")
async def analise_prospectiva_qualitativa(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Análise prospectiva qualitativa por IA — não é modelo de probabilidade.

    O endpoint legado `/predicao-exito` permanece como alias para compatibilidade.
    A IA deve discutir fatores favoráveis/desfavoráveis, lacunas e riscos sem
    converter o texto em uma probabilidade numérica não calibrada.
    """
    from app.services.ai.core.orchestrator import orchestrator

    texto_contexto = payload.get("contexto")
    if not (texto_contexto or "").strip():
        raise HTTPException(422, "Envie o campo 'contexto' com a descrição do caso.")

    prompt = (
        "Produza uma análise prospectiva qualitativa deste caso. Separe fatores "
        "favoráveis, desfavoráveis, lacunas probatórias, riscos processuais e "
        "pontos que exigem confirmação. Não atribua probabilidade numérica de "
        "êxito sem modelo estatisticamente calibrado e amostra explicitamente "
        f"informada. Contexto: {texto_contexto}"
    )
    res = await orchestrator.run(
        db=db,
        user=cu,
        task_type="jurimetria",
        domain="jurimetria",
        mensagem=prompt,
        case_id=payload.get("case_id"),
    )
    return {
        "resultado": res.get("conteudo"),
        "tipo": "analise_prospectiva_qualitativa",
        "aviso": (
            "Análise qualitativa e preliminar; não representa probabilidade "
            "calibrada nem garantia de resultado. Requer validação do advogado."
        ),
        "is_estimativa": True,
        "modelo": res.get("modelo"),
        "provider": res.get("provider"),
        "log_id": res.get("log_id"),
        "is_rascunho": res.get("is_rascunho", True),
        "aviso_hitl": res.get("aviso_hitl"),
    }



# ══ CONSOLIDAÇÃO 12/08/2026: conteúdo migrado de jurimetria_extra.py ══
# Origem: app/routers/jurimetria_extra.py. Prefixo /jurimetria idêntico
# ao canônico — divisão puramente física. Rotas e regras preservadas.
# Imports abaixo cobertos: from sqlalchemy import text, from app.core.security import get_current_user, , from app.services.jurimetria import _je_MIN_AMOSTRA,     from app.services.rag_coverage import medir_,     from app.services.rag_coverage import medir_

router.dependencies.append(Depends(_req_staff))

RESULTADO_LABEL = {
    "exito": "Êxito",
    "exito_total": "Êxito total",
    "exito_parcial": "Êxito parcial",
    "acordo": "Acordo",
    "derrota": "Derrota",
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
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
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
            "resultado": RESULTADO_LABEL.get(r["resultado"], r["resultado"]),
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
    total_com_tribunal = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM cases
                WHERE deleted_at IS NULL AND tribunal IS NOT NULL
                """
            )
        )
    ).scalar() or 0
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
        "total_com_tribunal": int(total_com_tribunal),
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
        "tempo_no_ejc": {
            "total_casos": int(tempo["total_processos"] or 0),
            "media_dias": dias_medio,
            "mediana_dias": dias_mediana,
            "inicio": "cases.created_at",
            "fim": "cases.data_encerramento",
            "nao_e_tempo_processual": True,
        },
        # Alias legado preservado; o metadado explicita que NÃO é tramitação judicial.
        "tempo_tramitacao": {
            "total_processos": int(tempo["total_processos"] or 0),
            "media_dias": dias_medio,
            "mediana_dias": dias_mediana,
            "dias_medio": dias_medio,
            "nao_e_tempo_processual": True,
            "rotulo_recomendado": "Tempo no EJC até encerramento",
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

    A taxa usa apenas desfechos DECIDIDOS e reconhece a taxonomia histórica da
    base: `exito`, `exito_total` e `exito_parcial` são favoráveis; `derrota` e
    `improcedente` são desfavoráveis. Acordos ficam separados e não são tratados
    como vitória judicial. Outros resultados não classificáveis também ficam
    fora do denominador.
    """
    total_encerrados, por_resultado = await _por_resultado(db, tribunal or None)
    contagens = {r["resultado_raw"]: int(r["total"]) for r in por_resultado}
    favoraveis = sum(contagens.get(chave, 0) for chave in _RESULTADOS_FAVORAVEIS)
    desfavoraveis = sum(
        contagens.get(chave, 0) for chave in _RESULTADOS_DESFAVORAVEIS
    )
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

    if decididos < _je_MIN_AMOSTRA:
        return {
            **base,
            "taxa_historica_favoravel": None,
            # Alias legado; preservado para não quebrar consumidor antigo.
            "probabilidade_provimento": None,
            "metodo": "amostra decidida insuficiente",
            "confianca": "insuficiente",
            "aviso": (
                f"Há {decididos} caso(s) com desfecho decidido no escopo — abaixo "
                f"do piso de {_je_MIN_AMOSTRA}. Nenhuma taxa é informada. "
                "Acordos são exibidos separadamente e não contam como êxito judicial."
            ),
        }

    taxa = round(favoraveis / decididos * 100, 1)
    ic95 = _intervalo_wilson(favoraveis, decididos)
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
        "intervalo_confianca_95": ic95,
        "confianca": "descritiva_com_ic95",
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


# ── Jurimetria dos TRIBUNAIS (Issue #1527) — DataJud/TJMG ───────────────────
# Preenche o slot do "benchmark externo" que os endpoints /interno/* declaram
# como `externo_habilitado: False`. Mede o comportamento do tribunal (Betim,
# Contagem, BH), não os casos do escritório; as duas jurimetrias coexistem.
# Mesmo gate de papel do resto do módulo (equipe jurídica, allowlist exata).
@router.get("/tribunais/status")
async def tribunais_status(cu: User = Depends(_req_staff)):
    """Configuração e limites da jurimetria dos tribunais — sem I/O externo."""
    from app.services.jurimetria_tribunais.servico import status as _status

    return _status()


@router.get("/tribunais/desfechos")
async def tribunais_desfechos(
    municipios: str = Query(
        "betim,contagem,belo_horizonte",
        description="Chaves separadas por vírgula: betim, contagem, belo_horizonte",
    ),
    classe: Optional[int] = Query(None, ge=1, description="Código TPU da classe"),
    assunto: Optional[int] = Query(None, ge=1, description="Código TPU do assunto"),
    desde: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    ate: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    cu: User = Depends(_req_staff),
):
    """Desfechos agregados do TJMG por município e assunto (só contagens/taxas).

    Falhas viram resposta controlada: funcionalidade desligada → 503 (via
    `require_enabled`); integração DataJud desligada → 503; CNJ fora do ar →
    502 sem stack trace. Nunca 500.
    """
    import logging

    import httpx

    from app.services import datajud_service as _djs
    from app.services.jurimetria_tribunais.servico import desfechos as _desfechos

    chaves = [m for m in (municipios or "").split(",") if m.strip()]
    try:
        return await _desfechos(chaves, classe=classe, assunto=assunto, desde=desde, ate=ate)
    except _djs.DataJudDesabilitadoError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except httpx.HTTPError as exc:
        logging.getLogger("ejc.jurimetria").warning(
            "jurimetria dos tribunais: DataJud indisponível (%s)", type(exc).__name__
        )
        raise HTTPException(
            status_code=502,
            detail="Falha ao consultar o DataJud. Tente novamente mais tarde.",
        ) from None


@router.get("/cobertura-rag")
async def cobertura_rag(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_staff),
):
    """Mapa agregado do RAG para a equipe jurídica; não retorna conteúdo/PII."""
    from app.services.rag_coverage import medir_cobertura_rag

    return await medir_cobertura_rag(db, mg_jec_only=False)


@router.get("/cobertura-mg-jec")
async def cobertura_mg_jec(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_staff),
):
    """Cobertura agregada MG/JEC para equipe jurídica, sem conteúdo documental."""
    from app.services.rag_coverage import medir_cobertura_rag

    return await medir_cobertura_rag(db, mg_jec_only=True)

