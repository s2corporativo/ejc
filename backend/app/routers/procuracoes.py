# ── app/routers/procuracoes.py ───────────────────────────────────────────────
from __future__ import annotations
from datetime import date
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import get_current_user
from app.models.user import User
from app.models.procuracao import Procuracao
from app.models.client import Client
from app.models.audit_log import criar_audit_log
# Segregação de titularidade de clientes (sigilo interno — LGPD/EOAB): mesma
# fonte de verdade do CRM (clients.py). Procuração expõe PII do outorgante
# (nome, CPF/CNPJ, endereço na qualificação) — logo herda a MESMA regra de
# carteira: gestão/secretaria veem tudo; advogado/adv_auxiliar só os próprios.
from app.routers.clients import _filtro_visibilidade_cliente, _pode_ver_cliente
from app.schemas.procuracao import ProcuracaoCreate, ProcuracaoResponse
from app.schemas.common import MsgResponse
from app.services.documental import _procuracao

router = APIRouter(prefix="/procuracoes", tags=["Procurações"])

_ADV = {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar"}


def _req_adv(cu: User = Depends(get_current_user)) -> User:
    # Emissão/revogação de procuração = ato jurídico: só equipe jurídica (advogado+).
    if cu.role.value not in _ADV:
        raise HTTPException(status_code=403, detail="Acesso restrito à equipe jurídica")
    return cu


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    client_id: Optional[str] = None,
    vencendo: bool = False,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Procuracao).where(
        Procuracao.deleted_at.is_(None), Procuracao.revogada == False,
    )
    # Sigilo interno (A1): a listagem expunha TODAS as procurações (client_id +
    # poderes) a qualquer usuário autenticado. Aplica a mesma segregação de
    # titularidade da listagem de clientes (join é seguro: client_id NOT NULL).
    q = _filtro_visibilidade_cliente(
        q.join(Client, Client.id == Procuracao.client_id), cu
    )
    if client_id:
        q = q.where(Procuracao.client_id == client_id)
    if vencendo:
        from datetime import timedelta
        q = q.where(
            Procuracao.data_validade.isnot(None),
            Procuracao.data_validade <= date.today() + timedelta(days=30),
        )
    q = q.order_by(Procuracao.data_validade.asc().nullslast())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [ProcuracaoResponse.model_validate(p) for p in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/", response_model=ProcuracaoResponse, status_code=201)
async def criar(
    payload: ProcuracaoCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_adv),
):
    # Titularidade (A1): antes aceitava client_id arbitrário — advogado emitia
    # procuração para cliente de OUTRA carteira. 404 não vaza existência
    # (espelha clients.detalhe); gestão/secretaria passam dentro do helper.
    cli = (await db.execute(
        select(Client).where(
            Client.id == payload.client_id, Client.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not cli or not await _pode_ver_cliente(cu, cli, db):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    p = Procuracao(id=str(uuid4()), **payload.model_dump())
    db.add(p)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "procuracoes", p.id)
    await db.commit()
    await db.refresh(p)
    return p


@router.post("/{proc_id}/minuta")
async def gerar_minuta(
    proc_id: str,
    case_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_adv),
):
    # Gera a MINUTA da procuracao a partir do registro cadastrado, garantindo que
    # o texto reflita EXATAMENTE os poderes concedidos (tipo_poderes /
    # permite_substabelecimento / poderes_especiais). Nunca outorga
    # substabelecimento/renuncia que o cadastro nao autorizou.
    p = (await db.execute(
        select(Procuracao).where(
            Procuracao.id == proc_id, Procuracao.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Procuração não encontrada")

    cli = await db.get(Client, p.client_id)
    if not cli:
        raise HTTPException(status_code=404, detail="Cliente da procuração não encontrado")
    # Titularidade (A1): a minuta monta a qualificação com PII do outorgante —
    # restrita à carteira do usuário (gestão/secretaria passam no helper).
    # 404 com o mesmo shape do "não existe" para não vazar existência.
    if not await _pode_ver_cliente(cu, cli, db):
        raise HTTPException(status_code=404, detail="Procuração não encontrada")

    case = None
    if case_id:
        # Ownership de caso (mesmo gate dos routers novos, ex.: orquestrador):
        # 404 p/ caso inexistente/soft-deleted; 403 se fora da carteira.
        case = await verificar_acesso_caso(db, cu, case_id)
        # Coerência: a procuração emitida deve ser do próprio outorgante do caso.
        if getattr(case, "client_id", None) and case.client_id != p.client_id:
            raise HTTPException(
                status_code=400, detail="Caso não pertence ao cliente da procuração"
            )

    adv = getattr(cu, "full_name", None) or "[advogado responsavel]"
    minuta = _procuracao(
        case, cli, adv,
        tipo_poderes=p.tipo_poderes,
        permite_substabelecimento=bool(p.permite_substabelecimento),
        poderes_especiais=p.poderes_especiais,
        foro_restrito=p.foro_restrito,
    )
    await criar_audit_log(db, cu.id, cu.role.value, "MINUTA", "procuracoes", p.id)
    await db.commit()
    return {
        "procuracao_id": p.id,
        "tipo_poderes": p.tipo_poderes,
        "permite_substabelecimento": bool(p.permite_substabelecimento),
        "minuta": minuta,
    }


@router.post("/{proc_id}/revogar", response_model=MsgResponse)
async def revogar(
    proc_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_adv),
):
    p = (await db.execute(
        select(Procuracao).where(
            Procuracao.id == proc_id, Procuracao.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Procuração não encontrada")
    # Titularidade (A1): revogação é ato sobre mandato de cliente — restrita à
    # carteira (gestão/secretaria passam no helper). 404 não vaza existência.
    cli = await db.get(Client, p.client_id)
    if cli is None or not await _pode_ver_cliente(cu, cli, db):
        raise HTTPException(status_code=404, detail="Procuração não encontrada")
    p.revogada = True
    p.revogada_em = date.today()
    await criar_audit_log(db, cu.id, cu.role.value, "REVOGACAO", "procuracoes", proc_id)
    await db.commit()
    return MsgResponse(detail="Procuração revogada")
