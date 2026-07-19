# ── app/services/dossie_modulos.py ────────────────────────────────────────────
# Módulos DETERMINÍSTICOS do Dossiê Estratégico (sem IA — custo zero):
#   · linha do tempo (reuso do visual_law_core: fases + eventos + próximos passos)
#   · mapa probatório (Prova ↔ Tese: o que temos e o que cada prova prova)
#   · riscos (case_health: score + fatores classificados por severidade)
#   · teses estruturadas (principal/subsidiárias, pela ordem de vinculação)
#
# Padrão do visual_law_core: funções PURAS testáveis sem banco
# (tests/test_dossie_modulos.py) + agregador async fino usado pelo router.
# As seções aparecem no payload do dossiê MESMO sem análise IA gerada.
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case
from app.models.deadline import Deadline, DeadlineStatus
from app.models.prova import Prova
from app.models.tese import Tese, TeseCasoLink
from app.services import visual_law_core as vl
from app.services.case_health import FECHADOS, calcular_score_caso

# Eventos exibidos na linha do tempo do dossiê (a cronologia completa segue
# disponível em /cases/{id}/linha-do-tempo e /visual-law/casos/{id}/timeline).
EVENTOS_LIMITE = 60

# Severidade visual de um fator do case_health pelo impacto no score.
_SEVERIDADE_POR_IMPACTO = ((-15, "alta"), (-10, "media"))


# ══════════════════════════════════════════════════════════════════════════════
# Funções puras (testáveis sem banco)
# ══════════════════════════════════════════════════════════════════════════════

def serializar_eventos(eventos: list[dict], limite: int = EVENTOS_LIMITE) -> list[dict]:
    """Eventos do visual_law_core (datas datetime/date) → JSON-safe (ISO),
    limitados aos `limite` mais recentes (a lista já vem ordenada desc)."""
    out = []
    for e in eventos[:limite]:
        data = e.get("data")
        out.append({**e, "data": data.isoformat() if hasattr(data, "isoformat")
                    else (str(data) if data is not None else None)})
    return out


def montar_mapa_probatorio(provas: list[dict],
                           teses_titulos: dict[str, str]) -> dict:
    """Seção PROVAS EXISTENTES: cada prova com o fato que ela prova e a tese
    que sustenta (título resolvido via `teses_titulos`). Determinístico.

    `provas`: [{id, tipo, titulo, fato_probando, tese_id, ordem}] (ordem do
    Documento Único de Anexos). NÃO sugere provas faltantes — o campo
    `provas_faltantes` é slot de outro módulo e só aparece se preenchido."""
    itens: list[dict] = []
    por_tipo: dict[str, int] = {}
    sem_fato = 0
    for p in sorted(provas, key=lambda x: (x.get("ordem") or 0)):
        tipo = p.get("tipo") or "outro"
        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
        fato = (p.get("fato_probando") or "").strip()
        if not fato:
            sem_fato += 1
        tese_id = p.get("tese_id")
        itens.append({
            "id":            p.get("id"),
            "tipo":          tipo,
            "titulo":        p.get("titulo") or "",
            "fato_probando": fato or None,
            "tese_id":       tese_id,
            "tese_titulo":   teses_titulos.get(tese_id) if tese_id else None,
        })
    return {
        "total":             len(itens),
        "provas":            itens,
        "por_tipo":          por_tipo,
        "sem_fato_probando": sem_fato,   # lacuna de instrução: prova sem fato declarado
    }


def classificar_riscos(saude: dict) -> dict:
    """Seção RISCOS a partir do case_health: score/classificação + fatores
    ordenados do mais grave para o mais leve, com severidade visual
    (alta ≤ −15 · media ≤ −10 · baixa acima disso)."""
    fatores = []
    for f in sorted(saude.get("fatores") or [], key=lambda x: x.get("impacto") or 0):
        impacto = f.get("impacto") or 0
        severidade = "baixa"
        for teto, nivel in _SEVERIDADE_POR_IMPACTO:
            if impacto <= teto:
                severidade = nivel
                break
        fatores.append({**f, "severidade": severidade})
    return {
        "score":         saude.get("score"),
        "classificacao": saude.get("classificacao"),
        "dias_parado":   max(0, saude.get("dias_parado") or 0),
        "fatores":       fatores,
        "saudavel":      not fatores,
    }


def estruturar_teses(teses: list[dict]) -> dict:
    """Teses do caso estruturadas em principal/subsidiárias.

    Regra determinística (dados existentes, sem campo dedicado): a PRIMEIRA
    tese vinculada ao caso (link mais antigo) é a principal — é a espinha
    dorsal da estratégia; as demais, na ordem de vinculação, são subsidiárias.
    `teses` deve chegar ordenada por data de vinculação ASC."""
    if not teses:
        return {"principal": None, "subsidiarias": [], "total": 0}
    return {"principal": teses[0], "subsidiarias": teses[1:], "total": len(teses)}


# ══════════════════════════════════════════════════════════════════════════════
# Agregador (acesso a dados) — usado por routers/dossie_estrategico.py
# ══════════════════════════════════════════════════════════════════════════════

def _tese_resumo(t: Tese, link: TeseCasoLink) -> dict:
    return {
        "id":               t.id,
        "titulo":           t.titulo,
        "descricao":        (t.descricao or "")[:600],
        "fundamentacao":    (t.fundamentacao or "")[:600] or None,
        "contra_argumento": (t.contra_argumento or "")[:600] or None,
        "area_juridica":    t.area_juridica,
        "taxa_sucesso":     t.taxa_sucesso,
        "resultado":        link.resultado,
        "vinculada_em":     link.created_at.isoformat() if link.created_at else None,
    }


async def consolidar_modulos(db: AsyncSession, case: Case) -> dict:
    """Consolida os módulos determinísticos do caso para o payload do dossiê.
    `case` já deve ter passado pelo gate de ownership (verificar_acesso_caso).
    Zero IA: apenas dados reais do banco + regras estáticas do visual_law_core."""
    case_id = case.id
    fase = case.fase.value if getattr(case, "fase", None) else "pre_processual"
    fechado = case.status in FECHADOS

    # 1) Linha do tempo — mesma montagem do /visual-law/casos/{id}/timeline
    eventos = await vl.montar_eventos_caso(db, case_id)
    saude = await calcular_score_caso(db, case)
    dias_parado = max(0, saude["dias_parado"] or 0)
    prazos_rows = (await db.execute(
        select(Deadline).where(
            Deadline.case_id == case_id,
            Deadline.deleted_at.is_(None),
            Deadline.status == DeadlineStatus.pendente,
            Deadline.data_prazo >= date.today(),
        ).order_by(Deadline.data_prazo).limit(20)
    )).scalars().all()
    prazos = [{"titulo": p.titulo,
               "data": p.data_prazo.isoformat() if p.data_prazo else None}
              for p in prazos_rows]
    linha_do_tempo = {
        "fase_atual":      fase,
        "fases":           vl.montar_fases(fase),
        "eventos":         serializar_eventos(eventos),
        "total_eventos":   len(eventos),
        "proximos_passos": vl.montar_proximos_passos(fase, prazos),
        "estagnacao":      vl.montar_estagnacao(dias_parado, fechado=fechado),
    }

    # 2) Teses do caso (ASC: 1ª vinculada = principal)
    tese_rows = (await db.execute(
        select(Tese, TeseCasoLink)
        .join(TeseCasoLink, TeseCasoLink.tese_id == Tese.id)
        .where(TeseCasoLink.case_id == case_id, Tese.deleted_at.is_(None))
        .order_by(TeseCasoLink.created_at.asc())
    )).all()
    teses = estruturar_teses([_tese_resumo(t, link) for t, link in tese_rows])

    # 3) Mapa probatório (títulos de tese: vinculadas ao caso + referenciadas
    #    diretamente por provas, ainda que sem TeseCasoLink)
    provas_rows = (await db.execute(
        select(Prova).where(Prova.case_id == case_id, Prova.deleted_at.is_(None))
        .order_by(Prova.ordem.asc(), Prova.created_at.asc())
    )).scalars().all()
    titulos = {t.id: t.titulo for t, _ in tese_rows}
    faltantes = [p.tese_id for p in provas_rows
                 if p.tese_id and p.tese_id not in titulos]
    if faltantes:
        extras = (await db.execute(
            select(Tese.id, Tese.titulo).where(Tese.id.in_(faltantes))
        )).all()
        titulos.update({tid: tit for tid, tit in extras})
    mapa = montar_mapa_probatorio(
        [{"id": p.id, "tipo": p.tipo, "titulo": p.titulo,
          "fato_probando": p.fato_probando, "tese_id": p.tese_id,
          "ordem": p.ordem} for p in provas_rows],
        titulos,
    )

    return {
        "linha_do_tempo":  linha_do_tempo,
        "mapa_probatorio": mapa,
        "riscos":          classificar_riscos(saude),
        "teses":           teses,
        "gerado_em":       datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# HTML para o PDF (tema Visual Law) — puro, testável
# ══════════════════════════════════════════════════════════════════════════════

def modulos_para_html(modulos: dict) -> str:
    """Renderiza os módulos determinísticos como HTML do PDF (visual_law_theme).
    Usa apenas inline-styles simples compatíveis com WeasyPrint."""
    from app.services import visual_law_theme as vlt

    def h2(txt: str) -> str:
        return (f"<h2 style='color:{vlt.OURO};border-bottom:2px solid "
                f"{vlt.OURO_CLARO};padding-bottom:4px;margin-top:22px;'>"
                f"{vlt.esc(txt)}</h2>")

    partes: list[str] = []

    # Linha do tempo
    lt = modulos.get("linha_do_tempo") or {}
    partes.append(h2("LINHA DO TEMPO"))
    fases = " → ".join(
        f"<strong>{vlt.esc(f['label'])}</strong>" if f["status"] == "atual"
        else vlt.esc(f["label"])
        for f in lt.get("fases") or []
    )
    if fases:
        partes.append(f"<p>Jornada: {fases}</p>")
    est = lt.get("estagnacao") or {}
    if est:
        partes.append(f"<p>Sem movimentação há {est.get('dias_parado', 0)} dia(s) "
                      f"(nível: {vlt.esc(est.get('nivel', 'ok'))}).</p>")
    eventos = (lt.get("eventos") or [])[:15]
    if eventos:
        linhas = "".join(
            f"<tr><td>{vlt.esc((e.get('data') or '')[:10])}</td>"
            f"<td>{vlt.esc(e.get('categoria') or '')}</td>"
            f"<td>{vlt.esc(e.get('descricao') or '')}</td></tr>"
            for e in eventos
        )
        partes.append(
            "<table style='width:100%;border-collapse:collapse;font-size:9.5pt;'>"
            f"<thead><tr style='background:{vlt.OURO_PALHA};'>"
            "<th style='text-align:left;padding:4px;'>Data</th>"
            "<th style='text-align:left;padding:4px;'>Tipo</th>"
            "<th style='text-align:left;padding:4px;'>Evento</th></tr></thead>"
            f"<tbody>{linhas}</tbody></table>"
        )
    passos = lt.get("proximos_passos") or []
    if passos:
        partes.append("<p><strong>Próximos passos:</strong></p><ul>" + "".join(
            f"<li>{vlt.esc(p.get('titulo') or '')}"
            + (f" ({vlt.esc(p['data_estimada'])})" if p.get("data_estimada") else "")
            + (" <em>[estimativa]</em>" if p.get("origem") == "estimativa" else "")
            + "</li>" for p in passos[:10]) + "</ul>")

    # Provas existentes
    mapa = modulos.get("mapa_probatorio") or {}
    partes.append(h2("PROVAS EXISTENTES"))
    provas = mapa.get("provas") or []
    if provas:
        linhas = "".join(
            f"<tr><td>{vlt.esc(p.get('tipo') or '')}</td>"
            f"<td>{vlt.esc(p.get('titulo') or '')}</td>"
            f"<td>{vlt.esc(p.get('fato_probando') or '—')}</td>"
            f"<td>{vlt.esc(p.get('tese_titulo') or '—')}</td></tr>"
            for p in provas
        )
        partes.append(
            "<table style='width:100%;border-collapse:collapse;font-size:9.5pt;'>"
            f"<thead><tr style='background:{vlt.OURO_PALHA};'>"
            "<th style='text-align:left;padding:4px;'>Tipo</th>"
            "<th style='text-align:left;padding:4px;'>Prova</th>"
            "<th style='text-align:left;padding:4px;'>Fato probando</th>"
            "<th style='text-align:left;padding:4px;'>Tese sustentada</th></tr></thead>"
            f"<tbody>{linhas}</tbody></table>"
        )
        if mapa.get("sem_fato_probando"):
            partes.append(f"<p><em>{mapa['sem_fato_probando']} prova(s) sem fato "
                          "probando declarado — lacuna de instrução.</em></p>")
    else:
        partes.append("<p>Nenhuma prova cadastrada no acervo do caso.</p>")
    if modulos.get("provas_faltantes"):
        partes.append(h2("PROVAS FALTANTES"))
        partes.append("<ul>" + "".join(
            f"<li>{vlt.esc(str(p.get('titulo') or p) if isinstance(p, dict) else str(p))}</li>"
            for p in modulos["provas_faltantes"]) + "</ul>")

    # Riscos
    riscos = modulos.get("riscos") or {}
    partes.append(h2("RISCOS"))
    partes.append(f"<p>Saúde do caso: <strong>{riscos.get('score', '—')}/100</strong> "
                  f"({vlt.esc(riscos.get('classificacao') or '—')}).</p>")
    if riscos.get("fatores"):
        partes.append("<ul>" + "".join(
            f"<li><strong>[{vlt.esc(f.get('severidade') or '')}]</strong> "
            f"{vlt.esc(f.get('detalhe') or f.get('fator') or '')} "
            f"(impacto {f.get('impacto')})</li>"
            for f in riscos["fatores"]) + "</ul>")
    else:
        partes.append("<p>Nenhum fator de risco operacional detectado.</p>")

    # Teses
    teses = modulos.get("teses") or {}
    partes.append(h2("TESES"))
    principal = teses.get("principal")
    if principal:
        partes.append(f"<p><strong>Tese principal:</strong> "
                      f"{vlt.esc(principal.get('titulo') or '')}</p>")
        if principal.get("descricao"):
            partes.append(f"<p style='font-size:9.5pt;'>{vlt.esc(principal['descricao'])}</p>")
        subs = teses.get("subsidiarias") or []
        if subs:
            partes.append("<p><strong>Teses subsidiárias:</strong></p><ul>" + "".join(
                f"<li>{vlt.esc(t.get('titulo') or '')}</li>" for t in subs) + "</ul>")
    else:
        partes.append("<p>Nenhuma tese vinculada ao caso.</p>")

    return "".join(partes)
