# ── app/routers/dashboard.py ─────────────────────────────────────────────────
# Dashboard executivo — KPIs do escritório em uma chamada.
import logging
import time
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func as sqlfunc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles, ROLE_LEVEL
from app.core.status_caso import contar_ativos, filtrar_aguardando_revisao
from app.models.case import CaseStatus
from app.models.legal_doc import LegalDoc
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Cache TTL em processo (sem Redis). A chave inclui o escopo financeiro do
# usuário (admin vê 'escritorio'; demais veem 'meus_casos' por uid), evitando
# vazamento de dados financeiros entre perfis. TTL curto: KPIs toleram defasagem.
# Compatível com uvicorn --workers 1 (cache global e consistente).
_DASHBOARD_TTL_S = 30.0
_dashboard_cache: dict[str, tuple[float, dict]] = {}


def _cache_get(chave: str) -> dict | None:
    item = _dashboard_cache.get(chave)
    if item and (time.monotonic() - item[0]) < _DASHBOARD_TTL_S:
        return item[1]
    return None


def _cache_set(chave: str, valor: dict) -> None:
    _dashboard_cache[chave] = (time.monotonic(), valor)


@router.get("/")
async def dashboard(
    db: AsyncSession = Depends(get_db),
    # Piso de staff: agregações globais do escritório não devem ser expostas fora
    # da equipe. Piso em `secretaria` (nível 2 = todo o staff) — a recepção tem
    # `dashboard_atendimento` e usa o painel; cliente_externo já é barrado pelo
    # AuthMiddleware. O escopo financeiro por uid abaixo permanece.
    cu: User = Depends(require_roles(["secretaria"])),
):
    from app.core.security import ROLE_LEVEL as _RL

    ve_total = _RL.get(cu.role.value, 0) >= _RL["admin"]
    cache_key = "escritorio" if ve_total else f"meus_casos:{cu.id}"
    _cached = _cache_get(cache_key)
    if _cached is not None:
        return _cached

    hoje = date.today()
    d3, d7 = hoje + timedelta(days=3), hoje + timedelta(days=7)

    casos_status: dict[str, int] = {}
    casos_area: list[dict] = []
    pv = pc = p7 = 0
    fin_pend = fin_atras = fin_mes = 0
    fin_escopo = "escritorio" if ve_total else "meus_casos"
    amb_criticas = 0
    clientes_ativos = 0
    pecas_hitl = 0
    # Cada bloco abaixo degrada para zero se a query falhar. Sem sinalização,
    # "banco fora do ar" fica indistinguível de "escritório sem casos" — um
    # falso positivo silencioso. `degradado` nomeia os blocos que NÃO puderam
    # ser calculados, para que a UI possa mostrar "indisponível" em vez de 0.
    degradado: list[str] = []

    try:
        r = await db.execute(text("""
            SELECT status, COUNT(*) FROM cases
            WHERE deleted_at IS NULL GROUP BY status
        """))
        casos_status = {row[0]: row[1] for row in r}
    except Exception:
        degradado.append("casos")
        logger.warning("Dashboard: falha ao carregar casos por status", exc_info=True)

    try:
        r = await db.execute(text("""
            SELECT area, COUNT(*) FROM cases
            WHERE deleted_at IS NULL
            GROUP BY area ORDER BY COUNT(*) DESC
        """))
        casos_area = [{"area": row[0], "total": row[1]} for row in r]
    except Exception:
        degradado.append("casos_por_area")
        logger.warning("Dashboard: falha ao carregar casos por área", exc_info=True)

    try:
        r = await db.execute(text("""
            SELECT
              COUNT(*) FILTER (WHERE data_prazo < :hoje) AS vencidos,
              COUNT(*) FILTER (WHERE data_prazo BETWEEN :hoje AND :d3) AS criticos,
              COUNT(*) FILTER (WHERE data_prazo BETWEEN :hoje AND :d7) AS proximos7
            FROM deadlines
            -- `status='pendente'` zerava o contador de VENCIDOS: o job das 07:10
            -- (`scheduler._marcar_prazos_vencidos`) move exatamente essas linhas
            -- para status='vencido', e elas saíam deste filtro. O prazo estourado
            -- ficava correto até as 07:10 e virava 0 depois — o job que existe para
            -- dar visibilidade ao vencido era o que o escondia daqui.
            -- Critério alinhado ao de `routers/relatorio.py` e `services/case_health.py`:
            -- vencido é o que passou da data e NÃO foi cumprido nem cancelado.
            WHERE status NOT IN ('concluido','cancelado') AND deleted_at IS NULL
        """), {"hoje": hoje, "d3": d3, "d7": d7})
        pv, pc, p7 = r.one()
    except Exception:
        degradado.append("prazos")
        logger.warning("Dashboard: falha ao carregar prazos", exc_info=True)

    try:
        if ve_total:
            r = await db.execute(text("""
                SELECT
                  COALESCE(SUM(valor) FILTER (WHERE status='pendente'),0),
                  COALESCE(SUM(valor) FILTER (WHERE status='atrasado'),0),
                  COALESCE(SUM(valor) FILTER (WHERE status='pago'
                    AND EXTRACT(MONTH FROM data_pagamento)=EXTRACT(MONTH FROM CURRENT_DATE)
                    AND EXTRACT(YEAR FROM data_pagamento)=EXTRACT(YEAR FROM CURRENT_DATE)),0)
                FROM fees WHERE deleted_at IS NULL
            """))
            fin_escopo = "escritorio"
        else:
            r = await db.execute(text("""
                SELECT
                  COALESCE(SUM(f.valor) FILTER (WHERE f.status='pendente'),0),
                  COALESCE(SUM(f.valor) FILTER (WHERE f.status='atrasado'),0),
                  COALESCE(SUM(f.valor) FILTER (WHERE f.status='pago'
                    AND EXTRACT(MONTH FROM f.data_pagamento)=EXTRACT(MONTH FROM CURRENT_DATE)
                    AND EXTRACT(YEAR FROM f.data_pagamento)=EXTRACT(YEAR FROM CURRENT_DATE)),0)
                FROM fees f
                JOIN cases c ON c.id = f.case_id
                WHERE f.deleted_at IS NULL AND c.deleted_at IS NULL
                  AND (c.advogado_responsavel_id = :uid OR c.advogado_auxiliar_id = :uid)
            """), {"uid": cu.id})
            fin_escopo = "meus_casos"
        fin_pend, fin_atras, fin_mes = r.one()
    except Exception:
        degradado.append("financeiro")
        logger.warning("Dashboard: falha ao carregar financeiro", exc_info=True)

    try:
        r = await db.execute(text("""
            SELECT COUNT(*) FROM environmental_cases
            WHERE deleted_at IS NULL
              AND status_defesa IN ('prazo_correndo','elaborando')
              AND data_prazo_defesa <= :d7
        """), {"d7": d7})
        amb_criticas = r.scalar() or 0
    except Exception:
        degradado.append("ambiental_criticas")
        logger.warning("Dashboard: falha ao carregar ambiental crítico", exc_info=True)

    try:
        r = await db.execute(text("""
            SELECT COUNT(*) FROM clients
            WHERE deleted_at IS NULL AND status='ativo'
        """))
        clientes_ativos = r.scalar() or 0
    except Exception:
        degradado.append("clientes_ativos")
        logger.warning("Dashboard: falha ao carregar clientes ativos", exc_info=True)

    try:
        # Fila de revisão humana: definição ÚNICA em core/status_caso.py.
        # Antes: `status NOT IN ('rascunho')` — que excluía justamente o estado
        # em que a IA entrega a peça, zerando o indicador. E sem vínculo com
        # `cases`, contava peça de caso já excluído.
        pecas_hitl = (await db.execute(
            filtrar_aguardando_revisao(select(sqlfunc.count(LegalDoc.id)))
        )).scalar() or 0
    except Exception:
        degradado.append("pecas_aguardando_revisao")
        logger.warning("Dashboard: falha ao carregar peças HITL", exc_info=True)

    # Contagens derivadas da fonte única (core/status_caso.py) — as MESMAS
    # definições de `GET /cases/stats`. Antes, `ativos` era
    # `total - encerrado`, o que contava caso ARQUIVADO como ativo e fazia o
    # Dashboard divergir da listagem (9 vs 8).
    resposta = {
        "casos": {
            "por_status": casos_status,
            "por_area": casos_area,
            "total": sum(casos_status.values()),
            "encerrados": casos_status.get(CaseStatus.encerrado.value, 0),
            "arquivados": casos_status.get(CaseStatus.arquivado.value, 0),
            "ativos": contar_ativos(casos_status),
        },
        "prazos": {"vencidos": pv, "criticos_3d": pc, "proximos_7d": p7},
        "financeiro": {
            "pendente": float(fin_pend or 0),
            "atrasado": float(fin_atras or 0),
            "recebido_mes": float(fin_mes or 0),
            "escopo": fin_escopo,
        },
        "ambiental_criticas": amb_criticas,
        "clientes_ativos": clientes_ativos,
        "pecas_aguardando_revisao": pecas_hitl,
        # Vazio = todos os blocos calculados. Não vazio = os nomeados falharam
        # e seus números são zero por degradação, não por ausência de dados.
        "degradado": degradado,
    }
    _cache_set(cache_key, resposta)
    return resposta


# ═══ Relatório Gerencial Mensal (PDF) ═══
from fastapi import Query as _Q, HTTPException as _HTTPExc
from fastapi.responses import Response as _R
from datetime import date as _date
from app.services.pdf_service import relatorio_mensal_pdf_async
from app.core.security import require_roles as _rr


# Coleta movida para services/dashboard_service.py (correção de camada
# domain→api). Mantido como alias para compatibilidade de imports existentes.
from app.services.dashboard_service import coletar_dados_mes as _coletar_dados_mes


@router.get("/relatorio-mensal")
async def relatorio_mensal(
    mes: int = _Q(None, ge=1, le=12),
    ano: int = _Q(None, ge=2026, le=2100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_rr(["superadmin", "admin", "socio"])),
):
    """PDF gerencial do mês (default: mês corrente)."""
    hoje = _date.today()
    mes, ano = mes or hoje.month, ano or hoje.year
    dados = await _coletar_dados_mes(db, mes, ano)
    try:
        pdf = await relatorio_mensal_pdf_async(mes, ano, dados)
    except RuntimeError:
        logger.warning("Geração do relatório mensal em PDF indisponível", exc_info=True)
        raise _HTTPExc(status_code=503, detail="Geração de PDF indisponível no momento")
    return _R(content=pdf, media_type="application/pdf",
              headers={"Content-Disposition":
                       f'attachment; filename="relatorio_{ano}_{mes:02d}.pdf"'})


# ============ Hoje — cockpit operacional (Tarefa 4; baseline 4.2/8/10) ====
# Problema que resolve: o DashboardUltra calculava decisões e badges sobre
# AMOSTRAS do navegador (casos p1=20, pecas=30) — com carteira grande os
# numeros divergiam do real. Aqui os contadores sao agregacoes autorizadas
# sobre o CONJUNTO INTEIRO permitido pela visibilidade, e as decisoes (<=3)
# sao calculadas no servidor com as MESMAS prioridades da UI.
# `/api/dashboard/` (KPIs executivos + cache 30s) permanece inalterado.
import datetime as _dt

from app.core.clock import hoje_operacional
from app.core.status_caso import STATUS_ABERTOS, filtrar_aguardando_revisao

# LegalDoc já é importado no topo deste módulo (fonte da peça HITL do GET /);
# o cockpit Hoje reusa o MESMO model + filtrar_aguardando_revisao para não
# duplicar a definição da fila.
_LegalDoc = LegalDoc

_ATIVOS_SQL = "(" + ",".join(f"'{s.value}'" for s in STATUS_ABERTOS) + ")"


def _prioridade_tarefa(prioridade: str | None, data_limite, hoje: _dt.date) -> int:
    """scoreTarefaHoje do DashboardUltra (paridade de decisão, baseline 4.2)."""
    score = 0
    pr = (prioridade or "").lower()
    if pr == "urgente":
        score += 50
    elif pr == "alta":
        score += 30
    if not data_limite:
        score += 10
    elif data_limite < hoje:
        score += 80
    elif data_limite == hoje:
        score += 60
    return score


@router.get("/hoje")
async def dashboard_hoje(
    db: AsyncSession = Depends(get_db),
    # Mesmo piso de staff do GET /: agregações de escritório não saem da
    # equipe. cliente_externo já é barrado pelo AuthMiddleware.
    cu: User = Depends(require_roles(["secretaria"])),
):
    hoje = hoje_operacional()
    d7 = hoje - _dt.timedelta(days=7)
    role = cu.role.value if hasattr(cu.role, "value") else str(cu.role)
    gestao = ROLE_LEVEL.get(role, 0) >= ROLE_LEVEL["socio"]

    # Filtro de carteira (MESMO limiar do cases._filtro_visibilidade: socio+).
    carteira = ""
    params: dict = {"uid": cu.id, "hoje": hoje, "d7": d7}
    if not gestao:
        carteira = (" AND (c.advogado_responsavel_id = :uid"
                    " OR c.advogado_auxiliar_id = :uid)")

    degradado: list[str] = []

    # -- Q1: casos visiveis por status (fonte unica STATUS_ABERTOS) --------
    casos_status: dict[str, int] = {}
    try:
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        r = await db.execute(text(f"""
            SELECT c.status, COUNT(*) FROM cases c
            WHERE c.deleted_at IS NULL{carteira}
            GROUP BY c.status
        """), params)
        casos_status = {row[0]: row[1] for row in r}
    except Exception:
        degradado.append("casos")
        logger.warning("Hoje: falha ao contar casos", exc_info=True)
    ativos = sum(n for s, n in casos_status.items() if s in STATUS_ABERTOS)

    # -- Q2: prazos da Central (vw_atividades, mesmo predicado do feed) ----
    prazos_vencidos = prazos_hoje = prazos_3d = 0
    candidatos_prazo: list[dict] = []
    try:
        vis_ativ = ""
        if not gestao:
            vis_ativ = (" AND ((v.case_id IS NOT NULL AND v.case_id IN (SELECT cc.id"
                        " FROM cases cc WHERE cc.deleted_at IS NULL AND"
                        " (cc.advogado_responsavel_id = :uid OR"
                        "  cc.advogado_auxiliar_id = :uid)))"
                        " OR (v.case_id IS NULL AND v.responsavel_id = :uid))")
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        r = await db.execute(text(f"""
            SELECT
              COUNT(*) FILTER (WHERE dr < 0)             AS vencidos,
              COUNT(*) FILTER (WHERE dr = 0)             AS hoje_n,
              COUNT(*) FILTER (WHERE dr BETWEEN 1 AND 3) AS proximos3
            FROM (
              SELECT (v.data::date - CURRENT_DATE) AS dr
              FROM vw_atividades v
              WHERE v.tipo = 'prazo'
                AND COALESCE(v.status,'') NOT IN
                    ('concluido','concluida','tratada','cancelado')
                AND v.data IS NOT NULL{vis_ativ}
            ) t
        """), params)
        row = r.one()
        prazos_vencidos, prazos_hoje, prazos_3d = row[0], row[1], row[2]
        # Candidatos a decisão: vencidos/hoje/<=3d — teto 10 (top-3 sobra).
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        rows = (await db.execute(text(f"""
            SELECT v.id, v.titulo, v.case_id, c.titulo AS caso_titulo,
                   (v.data::date - CURRENT_DATE) AS dr
            FROM vw_atividades v
            LEFT JOIN cases c ON c.id = v.case_id
            WHERE v.tipo = 'prazo'
              AND COALESCE(v.status,'') NOT IN
                  ('concluido','concluida','tratada','cancelado')
              AND v.data IS NOT NULL
              AND (v.data::date - CURRENT_DATE) <= 3{vis_ativ}
            ORDER BY (v.data::date - CURRENT_DATE) ASC, v.id ASC
            LIMIT 10
        """), params)).mappings().all()
        candidatos_prazo = [dict(m) for m in rows]
    except Exception:
        degradado.append("prazos")
        logger.warning("Hoje: falha ao carregar prazos", exc_info=True)

    # -- Q3: tarefas rotina "minhas" (mesmo predicado + minhas do /tasks) --
    tarefas_hoje = 0
    candidatos_tarefa: list[dict] = []
    try:
        vis_task = ""
        if not gestao:
            vis_task = (" AND (t.case_id IS NULL OR t.case_id IN (SELECT cc.id"
                        " FROM cases cc WHERE cc.deleted_at IS NULL AND"
                        " (cc.advogado_responsavel_id = :uid OR"
                        "  cc.advogado_auxiliar_id = :uid)))")
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        rows = (await db.execute(text(f"""
            SELECT t.id, t.titulo, t.prioridade, t.data_limite
            FROM tasks t
            WHERE t.deleted_at IS NULL
              AND t.responsavel_id = :uid
              AND t.status <> 'concluida'
              AND (t.data_limite IS NULL OR t.data_limite <= :hoje){vis_task}
            ORDER BY t.data_limite ASC NULLS LAST, t.created_at ASC
            LIMIT 10
        """), params)).mappings().all()
        candidatos_tarefa = [dict(m) for m in rows]
        # Contagem EXATA do mesmo conjunto (não depende do LIMIT).
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        tarefas_hoje = (await db.execute(text(f"""
            SELECT COUNT(*) FROM tasks t
            WHERE t.deleted_at IS NULL
              AND t.responsavel_id = :uid
              AND t.status <> 'concluida'
              AND (t.data_limite IS NULL OR t.data_limite <= :hoje){vis_task}
        """), params)).scalar() or 0
    except Exception:
        degradado.append("tarefas")
        logger.warning("Hoje: falha ao carregar tarefas", exc_info=True)

    # -- Q4: fila HITL (fonte unica filtrar_aguardando_revisao) ------------
    pecas_revisao = 0
    candidatos_peca: list[dict] = []
    try:
        base = filtrar_aguardando_revisao(select(_LegalDoc.id))
        pecas_revisao = (await db.execute(
            select(sqlfunc.count()).select_from(base.subquery())
        )).scalar() or 0
        q_cand = filtrar_aguardando_revisao(
            select(
                _LegalDoc.id, _LegalDoc.titulo, _LegalDoc.status,
                _LegalDoc.case_id,
            ).where(
                _LegalDoc.status.in_(["em_revisao", "corrigida"])
            ).order_by(_LegalDoc.created_at.asc()).limit(10)
        )
        rows = (await db.execute(q_cand)).mappings().all()
        candidatos_peca = [dict(m) for m in rows]
    except Exception:
        degradado.append("pecas_aguardando_revisao")
        logger.warning("Hoje: falha ao carregar peças HITL", exc_info=True)

    # -- Q5: documentos dos ultimos 7d (visibilidade do documents.py) ------
    documentos_7d = 0
    try:
        conf = "" if gestao else \
            " AND d.confidencialidade IN ('normal','interno')"
        escopo_doc = ""
        if not gestao:
            escopo_doc = (" AND (d.case_id IN (SELECT cc.id FROM cases cc WHERE"
                          " cc.deleted_at IS NULL AND (cc.advogado_responsavel_id"
                          " = :uid OR cc.advogado_auxiliar_id = :uid))"
                          " OR (d.case_id IS NULL AND d.client_id IN (SELECT"
                          " cc.client_id FROM cases cc WHERE cc.deleted_at IS NULL"
                          " AND cc.client_id IS NOT NULL AND"
                          " (cc.advogado_responsavel_id = :uid OR"
                          "  cc.advogado_auxiliar_id = :uid)))"
                          " OR (d.case_id IS NULL AND d.client_id IS NULL AND"
                          " d.uploaded_by = :uid))")
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        documentos_7d = (await db.execute(text(f"""
            SELECT COUNT(*) FROM documents d
            WHERE d.deleted_at IS NULL
              AND d.created_at >= :d7{conf}{escopo_doc}
        """), params)).scalar() or 0
    except Exception:
        degradado.append("documentos_7d")
        logger.warning("Hoje: falha ao contar documentos", exc_info=True)

    # -- Q6: casos de risco (mesma visibilidade de Q1) ---------------------
    candidatos_risco: list[dict] = []
    try:
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        rows = (await db.execute(text(f"""
            SELECT c.id, c.titulo, c.risco, c.prioridade, c.proxima_acao
            FROM cases c
            WHERE c.deleted_at IS NULL
              AND c.risco IN ('alto','critico','crítico')
              AND c.status IN {_ATIVOS_SQL}{carteira}
            ORDER BY CASE c.risco WHEN 'critico' THEN 0 WHEN 'crítico' THEN 0
                     ELSE 1 END, c.prioridade DESC, c.id ASC
            LIMIT 10
        """), params)).mappings().all()
        candidatos_risco = [dict(m) for m in rows]
    except Exception:
        degradado.append("casos_risco")
        logger.warning("Hoje: falha ao carregar casos de risco", exc_info=True)

    # -- Decisoes (<=3) — MESMAS prioridades do DashboardUltra -------------
    decisoes: list[dict] = []

    def _add(id_: str, prioridade: int, titulo: str, detalhe: list,
             acao: str, to: str, tom: str):
        decisoes.append({
            "id": id_, "prioridade": prioridade, "titulo": titulo,
            "detalhe": " · ".join([d for d in detalhe if d]),
            "acao": acao, "to": to, "tom": tom,
        })

    for p in candidatos_peca:
        em_revisao = p["status"] == "em_revisao"
        _add(
            f"peca-{p['id']}", 120 if em_revisao else 112,
            "Peça aguardando sua revisão" if em_revisao
            else "Peça corrigida aguardando aprovação",
            [p["titulo"] or "Peça jurídica"],
            "Revisar peça" if em_revisao else "Conferir e aprovar",
            f"/casos/{p['case_id']}?tab=pecas#revisao" if p["case_id"] else "/pecas",
            "danger",
        )
    for pr in candidatos_prazo:
        dias = pr["dr"]
        if dias is None or dias > 3:
            continue
        _add(
            f"prazo-{pr['id']}",
            118 if dias < 0 else 110 if dias == 0 else 94 - dias,
            "Prazo vencido exige decisão" if dias < 0
            else "Prazo vence hoje" if dias == 0
            else f"Prazo em {dias} dia(s)",
            [pr["titulo"] or "Prazo", pr["caso_titulo"]],
            "Abrir caso e resolver" if pr["case_id"] else "Resolver prazo",
            f"/casos/{pr['case_id']}" if pr["case_id"] else "/atividades?tipo=prazo",
            "danger" if dias <= 0 else "warning",
        )
    for t in candidatos_tarefa:
        _add(
            f"tarefa-{t['id']}",
            _prioridade_tarefa(t["prioridade"], t["data_limite"], hoje),
            "Tarefa requer ação hoje",
            [t["titulo"] or "Tarefa pendente"],
            "Abrir tarefa",
            "/atividades?tipo=tarefa",
            "info",
        )
    for c in candidatos_risco:
        critico = str(c["risco"] or "").lower().startswith("crit")
        _add(
            f"risco-{c['id']}", 88 if critico else 76,
            "Caso com risco crítico" if critico else "Caso com risco alto",
            [c["titulo"] or "Caso", c["proxima_acao"]],
            "Revisar estratégia",
            f"/casos/{c['id']}?tab=dossie",
            "warning",
        )

    # Dedup por to|titulo + ordem estável por prioridade (paridade UI).
    unicas: dict[str, dict] = {}
    for d in sorted(decisoes, key=lambda x: -x["prioridade"]):
        chave = d["to"] + "|" + d["titulo"]
        if chave not in unicas:
            unicas[chave] = d

    return {
        "data_operacional": hoje.isoformat(),
        "contadores": {
            "casos_ativos": ativos,
            "casos_total": sum(casos_status.values()),
            "prazos_vencidos": prazos_vencidos,
            "prazos_hoje": prazos_hoje,
            "prazos_proximos_3d": prazos_3d,
            "tarefas_hoje_minhas": tarefas_hoje,
            "pecas_aguardando_revisao": pecas_revisao,
            "documentos_7d": documentos_7d,
        },
        # Escopos declarados para a UI não inventar legenda errada.
        "escopos": {
            "casos": "escritorio" if gestao else "carteira",
            "prazos": "escritorio" if gestao else "carteira",
            "tarefas": "minhas",
            "pecas_aguardando_revisao": "escritorio",
            "documentos_7d": "escritorio" if gestao else "escopo_usuario",
        },
        "decisoes": list(unicas.values())[:3],
        # Vazio = tudo calculado; não vazio = blocos que falharam (zeros por
        # degradação, não por ausência) — mesmo contrato do GET /.
        "degradado": degradado,
    }
