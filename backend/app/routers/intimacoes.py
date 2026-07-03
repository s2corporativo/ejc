# ── app/routers/intimacoes.py ────────────────────────────────────────────────
# Intimações capturadas do DJEN — tratamento humano obrigatório.
# O job do scheduler captura; aqui o advogado processa.
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import is_gestao
from app.models.user import User
from app.models.djen import DjenComunicacao
from app.services.djen_service import capturar_para_advogado

router = APIRouter(prefix="/intimacoes", tags=["Intimações DJEN"])

# ── Heurística de sugestão de prazo (Seção 12 do redesign) ────────────────────
# Ordem IMPORTA: termos mais específicos primeiro ("embargos de declaração"
# antes de "recurso"; "contestação" antes de "manifestação"). O artigo só é
# citado quando a heurística casou EXPLICITAMENTE — nunca inventado.
_HEURISTICAS_PRAZO: list[tuple[tuple[str, ...], int, str, str]] = [
    (("embargos de declaração", "embargos de declaracao"), 5,
     "embargos de declaração",
     "CPC, art. 1.023 — 5 dias úteis"),
    (("contestação", "contestacao", "contestar"), 15,
     "contestação",
     "CPC, art. 335 — 15 dias úteis"),
    (("apelação", "apelacao", "recurso"), 15,
     "apelação/recurso",
     "CPC, art. 1.003, §5º — 15 dias úteis"),
    (("manifestação", "manifestacao", "despacho"), 5,
     "manifestação/despacho",
     "CPC, art. 218, §3º — 5 dias úteis (prazo supletivo, na ausência de "
     "prazo legal ou judicial específico)"),
]


@router.get("/")
async def listar(
    apenas_pendentes: bool = True,
    page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(DjenComunicacao)
    # Escopo: cada advogado vê só as SUAS intimações; gestão (sócio+) vê todas
    # (sigilo EOAB art. 25 — intimação de um advogado não vaza para outro).
    if not is_gestao(cu):
        q = q.where(DjenComunicacao.advogado_id == cu.id)
    if apenas_pendentes:
        q = q.where(DjenComunicacao.processada == False)
    q = q.order_by(DjenComunicacao.data_disponibilizacao.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery()))).scalar()
    rows = (await db.execute(
        q.offset((page-1)*page_size).limit(page_size))).scalars().all()
    return {
        "data": [
            {"id": c.id, "numero_processo": c.numero_processo,
             "tribunal": c.tribunal, "tipo": c.tipo_comunicacao,
             "data": c.data_disponibilizacao,
             "texto": (c.texto_resumo or "")[:500],
             "case_id": c.case_id, "processada": c.processada}
            for c in rows
        ],
        "total": total,
    }


@router.get("/status-captura")
async def status_captura(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """BUG-17: estado da última captura de intimações (job DJEN).

    Derivado de `djen_comunicacoes` (sem tabela nova): a última execução é a
    maior `created_at`; `intimacoes_encontradas` = comunicações gravadas nessa
    janela de execução; `sucesso` = houve captura recente.
    """
    from sqlalchemy import text as _t
    ultimo = (await db.execute(_t(
        "SELECT max(created_at) FROM djen_comunicacoes"
    ))).scalar()
    if ultimo is None:
        return {
            "executado_em": None,
            "sucesso": False,
            "intimacoes_encontradas": 0,
            "erro": "Nenhuma captura de intimações registrada até o momento.",
        }
    # Comunicações gravadas na mesma execução (janela de 5 min a partir do topo).
    encontradas = (await db.execute(_t(
        "SELECT count(*) FROM djen_comunicacoes "
        "WHERE created_at >= :inicio"
    ), {"inicio": ultimo - timedelta(minutes=5)})).scalar() or 0
    return {
        "executado_em": ultimo,
        "sucesso": True,
        "intimacoes_encontradas": encontradas,
        "erro": None,
    }


@router.post("/{com_id}/processar")
async def processar(
    com_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Marca como tratada (após o advogado criar o prazo manualmente)."""
    c = (await db.execute(select(DjenComunicacao).where(
        DjenComunicacao.id == com_id
    ))).scalar_one_or_none()
    if not c or (not is_gestao(cu) and c.advogado_id != cu.id):
        # 404 (não 403) para não revelar a existência de intimação alheia.
        raise HTTPException(status_code=404, detail="Comunicação não encontrada")
    c.processada = True
    c.processada_por = cu.id
    c.processada_em = datetime.now(timezone.utc)
    await db.commit()
    return {"detail": "Intimação marcada como tratada"}


@router.post("/{com_id}/sugerir-prazo")
async def sugerir_prazo(
    com_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Sugere um prazo a partir do texto da intimação (heurística por tipo).

    NÃO cria o Deadline — apenas devolve a sugestão para o advogado revisar e
    confirmar no fluxo de criação. O artigo/fundamentação só é citado quando a
    heurística casou EXPLICITAMENTE (nunca inventado). Prazo em dias úteis
    forenses, descontando feriados/suspensões via deadline_calculator.
    """
    from app.services.deadline_calculator import prazo_dias_uteis

    c = (await db.execute(select(DjenComunicacao).where(
        DjenComunicacao.id == com_id
    ))).scalar_one_or_none()
    if not c or (not is_gestao(cu) and c.advogado_id != cu.id):
        # 404 (não 403) para não revelar a existência de intimação alheia.
        raise HTTPException(status_code=404, detail="Comunicação não encontrada")

    texto = f"{c.tipo_comunicacao or ''} {c.texto_resumo or ''}".lower()

    tipo_detectado = None
    dias = 15
    fundamentacao = None
    casou = False
    for termos, prazo, rotulo, artigo in _HEURISTICAS_PRAZO:
        if any(t in texto for t in termos):
            tipo_detectado = rotulo
            dias = prazo
            fundamentacao = artigo
            casou = True
            break

    if not casou:
        tipo_detectado = "não identificado"
        dias = 15
        fundamentacao = None  # sem casamento explícito → NÃO citar artigo

    # Início da contagem: dia útil seguinte à disponibilização (referência;
    # o advogado confirma a data real de intimação na publicação original).
    base = c.data_disponibilizacao or date.today()
    if isinstance(base, datetime):
        base = base.date()
    data_sugerida = prazo_dias_uteis(base, dias, tribunal=c.tribunal)

    aviso = (
        "Sugestão automática — confirme o tipo, o termo inicial e o prazo na "
        "publicação original antes de cadastrar. Não substitui a conferência "
        "do advogado responsável."
    )
    if not casou:
        aviso = (
            "Tipo de intimação não identificado automaticamente. Prazo padrão "
            "de 15 dias úteis apresentado apenas como referência — defina o "
            "prazo correto conforme a publicação. " + aviso
        )

    return {
        "com_id": c.id,
        "numero_processo": c.numero_processo,
        "case_id": c.case_id,
        "tipo_detectado": tipo_detectado,
        "dias": dias,
        "data_base": base,
        "data_sugerida": data_sugerida,
        "fundamentacao": fundamentacao,
        "aviso": aviso,
    }


@router.post("/capturar-agora")
async def capturar_agora(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Captura manual imediata para a OAB do usuário logado."""
    if not cu.djen_oab_numero or not cu.djen_oab_uf:
        raise HTTPException(
            status_code=422,
            detail="Configure sua OAB (número e UF) no seu perfil de usuário",
        )
    novas = await capturar_para_advogado(db, cu)
    await db.commit()
    return {"novas": novas, "detail": f"{novas} intimação(ões) nova(s)"}
