"""Fonte única de atividades — lê a VIEW vw_atividades (prazos+tarefas+suspensões+agenda+intimações).
   Substitui a agregação no frontend por uma chamada só.

Tarefa 3 (performance): modo OPT-IN `pagination=cursor` com filtros server-side,
ordenação total (data NULLS LAST, tipo, id) e LIMIT n+1 — o legado (sem o
parâmetro) permanece byte a byte. Enriquecimento (confirmado/ciencia/hora/local)
passa a ser feito APENAS para os IDs da página já autorizada, eliminando o
fan-out do frontend (agenda page_size=500 + até 2.000 prazos).

`GET /atividades/resumo` devolve os contadores de urgência do CONJUNTO INTEIRO
visível (não da página) — replica a regra dos cards da Central
(CentralAtividades.tsx:1452-1478): pendentes do escopo/contexto, SEM aplicar os
filtros de tipo/urgência/situação do clique, para os cards não se auto-zerarem.
"""
from datetime import date as _date, datetime as _datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import hoje_operacional
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import is_gestao
from app.models.user import User
from app.schemas.activity_alert import ActivityAlertStateUpdate
from app.services.activity_alert_service import listar_alertas_inteligentes, marcar_estado_alerta

router = APIRouter(prefix="/atividades", tags=["Central de Atividades"])

_TIPOS_VIEW = ("prazo", "tarefa", "suspensao", "agenda", "intimacao")
_SITUACOES = ("nao_tratado", "em_execucao", "concluido")
_URGENCIAS = ("vencido", "critico", "atencao", "normal")

# Ordens canônicas e filtros ligados ao cursor (mesmo binding em make/parse)
_ATIV_ORDER_STR = "data:asc_nulls_last,tipo:asc,id:asc"


def _filtros_cursor(ap, case_id, tipo, situacao, urgencia, data_inicio, data_fim):
    return {
        "apenas_pendentes": ap,
        "case_id": case_id,
        "tipo": tipo,
        "situacao": situacao,
        "urgencia": urgencia,
        "data_inicio": data_inicio.isoformat() if data_inicio else None,
        "data_fim": data_fim.isoformat() if data_fim else None,
    }


def _validar_combinacoes(tipo, situacao, urgencia, data_inicio, data_fim):
    if tipo and tipo not in _TIPOS_VIEW:
        raise HTTPException(
            status_code=422,
            detail=f"tipo inválido; use um de {list(_TIPOS_VIEW)}",
        )
    if situacao and situacao not in _SITUACOES:
        raise HTTPException(
            status_code=422,
            detail=f"situacao inválida; use um de {list(_SITUACOES)}",
        )
    if urgencia and urgencia not in _URGENCIAS:
        raise HTTPException(
            status_code=422,
            detail=f"urgencia inválida; use um de {list(_URGENCIAS)}",
        )
    if data_inicio and data_fim and data_inicio > data_fim:
        raise HTTPException(
            status_code=422, detail="data_inicio não pode ser maior que data_fim"
        )


def _where_cursor(ap, case_id, tipo, situacao, urgencia, data_inicio, data_fim,
                  hoje):
    """Monta WHERE do modo cursor — visibilidade + filtros, todos com bind."""
    where = "WHERE 1=1"
    params: dict = {"hoje": hoje}
    if ap:
        where += (" AND COALESCE(v.status,'') NOT IN "
                  "('concluido','concluida','tratada','cancelado')")
    if case_id:
        where += " AND v.case_id = :case_id"
        params["case_id"] = case_id
    if tipo:
        where += " AND v.tipo = :tipo"
        params["tipo"] = tipo
    if situacao == "concluido":
        # coluna "concluído" do Kanban agrupa cancelado (situacaoColunaDe)
        where += (" AND COALESCE(v.status,'') IN "
                  "('concluido','concluida','tratada','cancelado')")
    elif situacao == "em_execucao":
        where += " AND v.status = 'fazendo'"
    elif situacao == "nao_tratado":
        where += (" AND COALESCE(v.status,'') NOT IN "
                  "('concluido','concluida','tratada','cancelado','fazendo')")
    if urgencia:
        # Expressão SQL equivalente à _urgencia() do Python (paridade testada):
        # vencido <0; critico <=3; atencao <=7; normal (inclui data NULL).
        # Fuso: data operacional de app/core/clock.py (fonte única), NÃO
        # CURRENT_DATE do servidor.
        where += """ AND (CASE WHEN v.data IS NULL THEN 'normal'
                     WHEN (v.data::date - :hoje) < 0 THEN 'vencido'
                     WHEN (v.data::date - :hoje) <= 3 THEN 'critico'
                     WHEN (v.data::date - :hoje) <= 7 THEN 'atencao'
                     ELSE 'normal' END) = :urgencia"""
        params["urgencia"] = urgencia
    if data_inicio:
        where += " AND v.data::date >= :data_inicio"
        params["data_inicio"] = data_inicio
    if data_fim:
        where += " AND v.data::date <= :data_fim"
        params["data_fim"] = data_fim
    return where, params


# (v.data::date - CURRENT_DATE) força diferença em DIAS inteiros mesmo se a
# coluna for TIMESTAMP (senão vem interval → int() estoura 500).
# SQL literal com bind params; a regra marca todo text(), sem olhar
# interpolacao. Ver docs/seguranca/SAST_BASELINE.md
# nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text


def _urgencia(d):
    if d is None:
        return "normal"
    if d < 0:
        return "vencido"
    if d <= 3:
        return "critico"
    if d <= 7:
        return "atencao"
    return "normal"


@router.get("")
async def listar_atividades(
    apenas_pendentes: bool = Query(True),
    # ── Tarefa 3: modo opt-in cursor ────────────────────────────────────────
    pagination: str | None = Query(None, pattern="^(cursor)$"),
    page_size: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    case_id: str | None = None,
    tipo: str | None = None,
    situacao: str | None = None,
    urgencia: str | None = None,
    data_inicio: _date | None = None,
    data_fim: _date | None = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    hoje = hoje_operacional()

    # validação sempre (422 explícito mesmo no legado, valores novos não
    # existiam antes) — aplicação só no modo cursor
    _validar_combinacoes(tipo, situacao, urgencia, data_inicio, data_fim)
    if pagination != "cursor" and any(
        (case_id, tipo, situacao, urgencia, data_inicio, data_fim)
    ):
        raise HTTPException(
            status_code=422,
            detail="filtros de listagem exigem pagination=cursor",
        )

    # Visibilidade: gestão vê tudo. Equipe vê atividade vinculada a caso apenas
    # quando atua naquele caso; atividades avulsas seguem o responsável direto.
    # Assim, responsavel_id nunca funciona como bypass da carteira de um caso.
    # (escopo original de atividades.py:23-39 — IMUTÁVEL nesta fase)
    visibilidade = ""
    vis_params: dict = {}
    if not is_gestao(cu):
        visibilidade = """ AND (
            (v.case_id IS NULL AND v.responsavel_id = :uid)
            OR EXISTS (
                SELECT 1 FROM cases cc WHERE cc.id = v.case_id
                  AND cc.deleted_at IS NULL
                  AND (cc.advogado_responsavel_id = :uid OR cc.advogado_auxiliar_id = :uid)
            )
        )"""
        vis_params["uid"] = cu.id

    # ── modo LEGADO: shape e campos byte a byte como antes ──────────────────
    if pagination != "cursor":
        where = "WHERE 1=1"
        params: dict = dict(vis_params)
        if apenas_pendentes:
            where += (" AND COALESCE(v.status,'') NOT IN "
                      "('concluido','concluida','tratada','cancelado')")
        # SQL literal só com bind params (:nome) e WHERE montado no servidor
        # a partir de enums validados — nenhum input interpolado. Ver
        # docs/seguranca/SAST_BASELINE.md
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        rows = (await db.execute(text(f"""
            SELECT v.id, v.tipo, v.titulo, v.descricao, v.data, v.status,
                   v.case_id, v.responsavel_id, v.prioridade, v.subtipo,
                   c.titulo AS caso_titulo,
                   (v.data::date - CURRENT_DATE) AS dias_restantes
            FROM vw_atividades v
            LEFT JOIN cases c ON c.id = v.case_id
            {where}
            {visibilidade}
            ORDER BY v.data ASC NULLS LAST
        """), params)).mappings().all()


        def _dias(d):
            # Robusto: aceita int (date - date) ou timedelta (fallback de driver).
            if d is None:
                return None
            if hasattr(d, "days"):
                return d.days
            return int(d)

        data = []
        for r in rows:
            di = _dias(r["dias_restantes"])
            data.append({
                "id": r["id"], "tipo": r["tipo"], "titulo": r["titulo"],
                "descricao": r["descricao"], "date": str(r["data"]) if r["data"] else None,
                "status": r["status"], "case_id": r["case_id"], "caso_titulo": r["caso_titulo"],
                "responsavel_id": r["responsavel_id"], "prioridade": r["prioridade"],
                "subtipo": r["subtipo"],
                "dias_restantes": di, "urgencia": _urgencia(di),
            })
        return {"data": data}

    # ── modo CURSOR (opt-in): filtros server-side, ordenação total, LIMIT n+1
    from app.core.pagination_cursor import (
        deserializar_key, make_cursor, parse_cursor,
    )
    from datetime import date as _date_conv

    filtros_bind = _filtros_cursor(apenas_pendentes, case_id, tipo, situacao,
                                   urgencia, data_inicio, data_fim)
    where, params = _where_cursor(apenas_pendentes, case_id, tipo, situacao,
                                  urgencia, data_inicio, data_fim, hoje)
    params.update(vis_params)

    sql_base = f"""
        SELECT v.id, v.tipo, v.titulo, v.descricao, v.data, v.status,
               v.case_id, v.responsavel_id, v.prioridade, v.subtipo,
               c.titulo AS caso_titulo
        FROM vw_atividades v
        LEFT JOIN cases c ON c.id = v.case_id
        {where}
        {visibilidade}
        {{extra}}
        ORDER BY v.data ASC NULLS LAST, v.tipo, v.id
        LIMIT {{limite}}
    """

    if cursor:
        bruto = parse_cursor(cursor, "/atividades", cu, filtros_bind,
                             _ATIV_ORDER_STR)
        chave = deserializar_key(bruto, _date_conv.fromisoformat, None, None)
        # Condição keyset para a view (SQL com binds nomeados — mesma
        # semântica de condicao_lexicografica do core; paridade coberta por
        # testes DB-level).
        sql_cond, params_cond = _condicao_sql(chave)
        params.update(params_cond)
        extra_sql = f"AND {sql_cond}"
    else:
        extra_sql = ""

    # SQL literal só com bind params (:nome) e WHERE montado no servidor
    # a partir de enums validados — nenhum input interpolado. Ver
    # docs/seguranca/SAST_BASELINE.md
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    rows = (await db.execute(text(sql_base.format(extra=extra_sql, limite=page_size + 1)),
                             params)).mappings().all()
    has_more = len(rows) > page_size
    pagina = rows[:page_size]

    # ── enriquecimento SOMENTE da página (batch lookup por IDs) ─────────────
    ids_prazo = [r["id"] for r in pagina if r["tipo"] == "prazo"]
    ids_agenda = [r["id"] for r in pagina if r["tipo"] == "agenda"]
    prazo_map: dict = {}
    agenda_map: dict = {}
    if ids_prazo:
        rr = await db.execute(
            text("SELECT id, confirmado, ciencia_confirmada FROM deadlines "
                 "WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
            {"ids": ids_prazo})
        prazo_map = {r[0]: r for r in rr}
    if ids_agenda:
        rr = await db.execute(
            text("SELECT id, hora, local FROM agenda_eventos "
                 "WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
            {"ids": ids_agenda})
        agenda_map = {r[0]: r for r in rr}


    data = []
    for r in pagina:
        d_val = r["data"]
        if d_val is None:
            di = None
        else:
            if hasattr(d_val, "date"):  # timestamp → date (view devolve date)
                d_val = d_val.date()
            di = (d_val - hoje).days
        item = {
            "id": r["id"], "tipo": r["tipo"], "titulo": r["titulo"],
            "descricao": r["descricao"],
            "date": str(r["data"]) if r["data"] else None,
            "status": r["status"], "case_id": r["case_id"],
            "caso_titulo": r["caso_titulo"],
            "responsavel_id": r["responsavel_id"], "prioridade": r["prioridade"],
            "subtipo": r["subtipo"],
            "dias_restantes": di, "urgencia": _urgencia(di),
        }
        if r["tipo"] == "prazo" and r["id"] in prazo_map:
            p = prazo_map[r["id"]]
            item["confirmado"] = p[1]
            item["ciencia_confirmada"] = p[2]
        if r["tipo"] == "agenda" and r["id"] in agenda_map:
            a = agenda_map[r["id"]]
            item["hora"] = a[1]
            item["local"] = a[2]
        data.append(item)

    next_cursor = None
    if has_more and pagina:
        ultimo = pagina[-1]
        u_data = ultimo["data"]
        if u_data is not None and hasattr(u_data, "date"):
            u_data = u_data.date()
        next_cursor = make_cursor(
            "/atividades", cu, filtros_bind, _ATIV_ORDER_STR,
            [u_data, ultimo["tipo"], ultimo["id"]],
        )
    return {"data": data, "page_size": page_size, "has_more": has_more,
            "next_cursor": next_cursor}


def _condicao_sql(chave):
    """Traduz a condição lexicográfica (data NULLS LAST, tipo, id) para SQL
    com binds nomeados — mesma semântica de condicao_lexicografica.

    chave = [data_date|None, tipo_str, id_str]
    """
    d, t, i = chave
    p = {"k_d": d, "k_t": t, "k_i": i}
    if d is None:
        # último valor é o máximo (NULL): só NULL-data vem depois
        sql = "(v.data IS NULL AND ((v.tipo > :k_t) OR (v.tipo = :k_t AND v.id > :k_i)))"
    else:
        sql = """(v.data IS NULL OR (v.data::date > :k_d)
                  OR (v.data::date = :k_d AND (
                        v.tipo > :k_t OR (v.tipo = :k_t AND v.id > :k_i))))"""
    return sql, p


@router.get("/resumo")
async def resumo_atividades(
    case_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Cards de urgência sobre o CONJUNTO INTEIRO visível (não a página).

    Regra dos cards da Central: pendentes do escopo/contexto de caso, SEM
    aplicar filtros de tipo/urgência/situação do clique — os cards são os
    próprios botões de filtro e não podem se auto-zerar. Fuso pela fonte
    única (clock.hoje_operacional). Cliente externo não acessa (403).
    """
    if getattr(cu.role, "value", str(cu.role)) == "cliente_externo":
        raise HTTPException(status_code=403, detail="Sem permissão")
    hoje = hoje_operacional()
    # Base comum: contexto de caso + visibilidade.
    filtro_escopo = ""
    params: dict = {"hoje": hoje}
    if case_id:
        filtro_escopo += " AND v.case_id = :case_id"
        params["case_id"] = case_id
    if not is_gestao(cu):
        filtro_escopo += """ AND (
            (v.case_id IS NULL AND v.responsavel_id = :uid)
            OR EXISTS (
                SELECT 1 FROM cases cc WHERE cc.id = v.case_id
                  AND cc.deleted_at IS NULL
                  AND (cc.advogado_responsavel_id = :uid OR cc.advogado_auxiliar_id = :uid)
            )
        )"""
        params["uid"] = cu.id
    # Cards de urgência: SÓ pendentes. Kanban: TODOS os status (colunas).
    where_pendentes = ("WHERE COALESCE(v.status,'') NOT IN "
                       "('concluido','concluida','tratada','cancelado')"
                       + filtro_escopo)
    where_todos = "WHERE 1=1" + filtro_escopo
    # SQL literal só com bind params (:nome) e WHERE montado no servidor
    # a partir de enums validados — nenhum input interpolado. Ver
    # docs/seguranca/SAST_BASELINE.md
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    rows = (await db.execute(text(f"""
        SELECT CASE WHEN v.data IS NULL THEN 'normal'
                    WHEN (v.data::date - :hoje) < 0 THEN 'vencido'
                    WHEN (v.data::date - :hoje) <= 3 THEN 'critico'
                    WHEN (v.data::date - :hoje) <= 7 THEN 'atencao'
                    ELSE 'normal' END AS faixa,
               count(*)
        FROM vw_atividades v
        {where_pendentes}
        GROUP BY 1
    """), params)).all()
    contagens = {faixa: n for faixa, n in rows}
    # Resumo por coluna do Kanban (situacaoColunaDe: cancelado agrupa com
    # concluído) sobre o MESMO conjunto inteiro visível — TODOS os status
    # (não só pendentes), pois o Kanban também mostra concluídos.
    # SQL literal só com bind params (:nome) e WHERE montado no servidor
    # a partir de enums validados — nenhum input interpolado. Ver
    # docs/seguranca/SAST_BASELINE.md
    # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
    colunas_rows = (await db.execute(text(f"""
        SELECT CASE
                 WHEN v.status = 'fazendo' THEN 'em_execucao'
                 WHEN COALESCE(v.status,'') IN
                      ('concluido','concluida','tratada','cancelado')
                   THEN 'concluido'
                 ELSE 'nao_tratado' END AS coluna,
                count(*)
        FROM vw_atividades v
        {where_todos}
        GROUP BY 1
    """), params)).all()
    colunas = {c: n for c, n in colunas_rows}
    return {
        "vencido": contagens.get("vencido", 0),
        "critico": contagens.get("critico", 0),
        "atencao": contagens.get("atencao", 0),
        "normal": contagens.get("normal", 0),
        "total_pendentes": sum(contagens.values()),
        "colunas": {
            "nao_tratado": colunas.get("nao_tratado", 0),
            "em_execucao": colunas.get("em_execucao", 0),
            "concluido": colunas.get("concluido", 0),
        },
        "data_operacional": hoje.isoformat(),
        "gerado_em": _datetime.now().isoformat(timespec="seconds"),
    }


@router.get("/alertas-inteligentes")
async def alertas_inteligentes(
    limit_per_type: int = Query(5, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return await listar_alertas_inteligentes(
        db, cu, limit_per_type=limit_per_type
    )


@router.patch("/alertas/{source_type}/{source_id}")
async def atualizar_estado_alerta(
    source_type: str,
    source_id: str,
    payload: ActivityAlertStateUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    return await marcar_estado_alerta(
        db, cu, source_type, source_id, payload.estado
    )
