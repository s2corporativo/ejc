# ── app/routers/intimacoes.py ────────────────────────────────────────────────
# Intimações capturadas do DJEN — tratamento humano obrigatório.
# O job do scheduler captura; aqui o advogado processa.
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.models.user import User
from app.models.djen import DjenComunicacao
from app.models.deadline import Deadline
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


def _calcular_sugestao(c: DjenComunicacao) -> dict:
    """
    Monta a sugestão de prazo a partir da intimação (heurística por tipo).

    Fonte única de verdade compartilhada por `sugerir-prazo`, `prazo-sugerido`
    e `aceitar-prazo`. NÃO persiste nada e NÃO invoca a política de ownership —
    apenas calcula. O artigo/fundamentação só é citado quando a heurística casou
    EXPLICITAMENTE (nunca inventado). Prazo em dias úteis forenses, descontando
    feriados/suspensões via deadline_calculator.

    Retorna `disponivel=False` quando não há data-base (disponibilização) para
    ancorar a contagem — nesse caso o consumidor deve tratar como indisponível.
    """
    from app.services.deadline_calculator import prazo_dias_uteis

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

    # Sem data de disponibilização não há como ancorar a contagem do prazo.
    base = c.data_disponibilizacao
    if isinstance(base, datetime):
        base = base.date()
    if base is None:
        return {
            "disponivel": False,
            "com_id": c.id,
            "numero_processo": c.numero_processo,
            "case_id": c.case_id,
            "tipo_detectado": tipo_detectado,
            "dias": dias,
            "data_base": None,
            "data_sugerida": None,
            "fundamentacao": fundamentacao,
            "casou": casou,
            "aviso": (
                "Intimação sem data de disponibilização — não é possível sugerir "
                "prazo automaticamente. Informe o termo inicial manualmente."
            ),
        }

    # Início da contagem: dia útil seguinte à disponibilização (referência;
    # o advogado confirma a data real de intimação na publicação original).
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
        "disponivel": True,
        "com_id": c.id,
        "numero_processo": c.numero_processo,
        "case_id": c.case_id,
        "tipo_detectado": tipo_detectado,
        "dias": dias,
        "data_base": base,
        "data_sugerida": data_sugerida,
        "fundamentacao": fundamentacao,
        "casou": casou,
        "aviso": aviso,
    }


async def _carregar_comunicacao(
    com_id: str, db: AsyncSession, cu: User
) -> DjenComunicacao:
    """Carrega a intimação aplicando o escopo de visibilidade do advogado.

    404 (não 403) para não revelar a existência de intimação alheia.
    """
    c = (await db.execute(select(DjenComunicacao).where(
        DjenComunicacao.id == com_id
    ))).scalar_one_or_none()
    if not c or (not is_gestao(cu) and c.advogado_id != cu.id):
        raise HTTPException(status_code=404, detail="Comunicação não encontrada")
    return c


class AceitarPrazoRequest(BaseModel):
    """Override opcional da sugestão ao aceitar o prazo.

    Precedência: `data_prazo` (data absoluta) > `dias` (recalcula a partir da
    disponibilização) > sugestão calculada automaticamente.
    """
    dias: Optional[int] = None
    data_prazo: Optional[date] = None
    titulo: Optional[str] = None
    responsavel_id: Optional[str] = None
    prioridade: Optional[str] = None


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
    c = await _carregar_comunicacao(com_id, db, cu)
    return _calcular_sugestao(c)


@router.get("/{com_id}/prazo-sugerido")
async def prazo_sugerido(
    com_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Prazo assistido a partir da intimação DJEN — sugestão em modo LEITURA.

    Calcula (sem persistir) a data sugerida a partir da disponibilização,
    devolvendo dias, base de cálculo e o status atual do fluxo assistido
    (nenhum | sugerido | aceito | recusado) e o Deadline vinculado, se houver.
    Sem data de disponibilização, retorna `disponivel=False` de forma limpa.
    """
    c = await _carregar_comunicacao(com_id, db, cu)
    sugestao = _calcular_sugestao(c)
    sugestao["prazo_sugerido_status"] = c.prazo_sugerido_status or "nenhum"
    sugestao["prazo_deadline_id"] = c.prazo_deadline_id
    return sugestao


@router.post("/{com_id}/aceitar-prazo")
async def aceitar_prazo(
    com_id: str,
    payload: Optional[AceitarPrazoRequest] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Aceita o prazo assistido: cria um Deadline real vinculado ao caso da
    intimação e marca `prazo_sugerido_status="aceito"`.

    Override opcional no corpo (data_prazo absoluta > dias > sugestão). Exige
    intimação vinculada a um caso (422 caso contrário) e aplica ownership de
    caso. Idempotente: se já aceito e o Deadline ainda existe, devolve-o sem
    duplicar.
    """
    from app.services.deadline_calculator import prazo_dias_uteis
    from app.models.audit_log import criar_audit_log

    payload = payload or AceitarPrazoRequest()
    c = await _carregar_comunicacao(com_id, db, cu)

    if not c.case_id:
        raise HTTPException(
            status_code=422,
            detail="Intimação não vinculada a um caso — vincule um caso antes "
                   "de gerar o prazo.",
        )

    # Ownership: escrita em sub-recurso de caso (mesmo gate do router de prazos).
    await verificar_acesso_caso(db, cu, c.case_id)

    # Idempotência: já aceito e Deadline ainda vivo → devolve o existente.
    if c.prazo_sugerido_status == "aceito" and c.prazo_deadline_id:
        existente = (await db.execute(select(Deadline).where(
            Deadline.id == c.prazo_deadline_id,
            Deadline.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if existente is not None:
            return {
                "detail": "Prazo já havia sido aceito para esta intimação",
                "criado": False,
                "deadline_id": existente.id,
                "data_prazo": existente.data_prazo,
            }

    sugestao = _calcular_sugestao(c)

    # Termo inicial: disponibilização (dia útil seguinte via calculadora).
    base = c.data_disponibilizacao
    if isinstance(base, datetime):
        base = base.date()

    # Precedência: data_prazo absoluta > dias (recalcula) > sugestão calculada.
    if payload.data_prazo is not None:
        data_prazo = payload.data_prazo
        base_legal = sugestao.get("fundamentacao") or "Prazo informado manualmente"
    elif payload.dias is not None:
        if base is None:
            raise HTTPException(
                status_code=422,
                detail="Intimação sem data de disponibilização — informe "
                       "data_prazo diretamente.",
            )
        data_prazo = prazo_dias_uteis(base, payload.dias, tribunal=c.tribunal)
        base_legal = sugestao.get("fundamentacao") or f"{payload.dias} dias úteis"
    else:
        if not sugestao.get("disponivel"):
            raise HTTPException(
                status_code=422,
                detail="Não há sugestão de prazo disponível — informe dias ou "
                       "data_prazo.",
            )
        data_prazo = sugestao["data_sugerida"]
        base_legal = sugestao.get("fundamentacao") or \
            f"{sugestao['dias']} dias úteis (sugestão automática)"

    titulo = payload.titulo or (
        f"{sugestao.get('tipo_detectado') or 'Prazo'} — "
        f"proc. {c.numero_processo or 's/ número'}"
    )[:255]

    d = Deadline(
        id=str(uuid4()),
        titulo=titulo,
        tipo="processual",
        prioridade=payload.prioridade or "alta",
        descricao=(
            "Prazo gerado a partir de intimação DJEN "
            f"({c.tribunal or 'tribunal n/d'}). {sugestao.get('aviso') or ''}"
        ).strip(),
        data_prazo=data_prazo,
        data_intimacao=base,
        base_legal=base_legal[:255] if base_legal else None,
        case_id=c.case_id,
        responsavel_id=payload.responsavel_id or c.advogado_id or cu.id,
        origem="djen",
    )
    db.add(d)

    c.prazo_sugerido_status = "aceito"
    c.prazo_deadline_id = d.id

    await criar_audit_log(
        db, cu.id, cu.role.value, "CREATE", "deadlines", d.id,
        dados_depois={"origem": "djen", "com_id": c.id},
    )
    await db.commit()
    await db.refresh(d)
    return {
        "detail": "Prazo aceito e cadastrado",
        "criado": True,
        "deadline_id": d.id,
        "data_prazo": d.data_prazo,
        "titulo": d.titulo,
        "base_legal": d.base_legal,
    }


@router.post("/{com_id}/recusar-prazo")
async def recusar_prazo(
    com_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Recusa o prazo assistido: o advogado decidiu que a intimação não gera prazo.
    Apenas marca `prazo_sugerido_status="recusado"`; não cria Deadline.
    """
    c = await _carregar_comunicacao(com_id, db, cu)
    # Se houver caso, respeita o mesmo gate de ownership de escrita.
    if c.case_id:
        await verificar_acesso_caso(db, cu, c.case_id)
    c.prazo_sugerido_status = "recusado"
    await db.commit()
    return {
        "detail": "Prazo recusado — nenhum prazo será gerado para esta intimação",
        "prazo_sugerido_status": c.prazo_sugerido_status,
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
