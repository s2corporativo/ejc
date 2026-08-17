# ── app/routers/sociedades_cliente.py ────────────────────────────────────────
# Gestão societária de CLIENTES empresariais — /empresarial/sociedades.
#
# NÃO confundir com routers/gestao_societaria.py (sócios DO ESCRITÓRIO): aqui
# gerenciamos as SOCIEDADES DOS CLIENTES — quadro societário, cap table e
# eventos societários (vertical Empresarial).
#
# Segurança (padrão do CRM de clientes + ownership de casos):
#   • escrita: mesmos papéis do CRM (_CLIENTES de clients.py);
#   • leitura: equipe interna (cliente_externo bloqueado);
#   • visibilidade: gestão (socio+) vê tudo; advogado comum só vê sociedades
#     de clientes que "enxerga" — é responsável pelo cliente OU atua em caso
#     do cliente (mesma matriz de cases._filtro_visibilidade / core/ownership).
#     Sociedade fora do escopo responde 404 (não vaza existência);
#   • audit log em toda escrita (criar_audit_log); soft delete na sociedade;
#   • LGPD: documento do sócio cifrado em repouso (services/pii_crypto, padrão
#     Bloco 6a de clients) — a API só expõe `documento_mascarado`.
from datetime import date, datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, func as sqlfunc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import is_gestao
from app.core.security import get_current_user, require_roles
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.client import Client
from app.models.sociedade_cliente import (
    EventoSocietario, SociedadeCliente, SocioSociedade, TipoEventoSocietario,
)
from app.models.user import User
from app.schemas.common import MsgResponse
from app.schemas.sociedade_cliente import (
    EventoCreate, SociedadeCreate, SociedadeUpdate, SocioCreate, SocioUpdate,
)
from app.services.sociedades_service import (
    calcular_percentual, montar_cap_table, preparar_documento_socio,
)

router = APIRouter(prefix="/empresarial/sociedades",
                   tags=["Empresarial / Gestão Societária de Clientes"])

# Mesmos papéis de escrita do CRM de clientes (clients.py _CLIENTES).
_ESCRITA = {"superadmin", "admin", "socio", "advogado", "secretaria"}


def _req_escrita(cu: User = Depends(get_current_user)) -> User:
    if cu.role.value not in _ESCRITA:
        raise HTTPException(status_code=403, detail="Sem permissão para gerenciar sociedades")
    return cu


def _req_leitura(cu: User = Depends(get_current_user)) -> User:
    """Leitura restrita à equipe interna — padrão clients._req_clientes_leitura."""
    if cu.role.value == "cliente_externo":
        raise HTTPException(status_code=403, detail="Sem permissão para consultar sociedades")
    return cu


# ── Visibilidade (padrão do cliente) ──────────────────────────────────────────

def _cond_cliente_visivel(cu: User):
    """Condição SQL de visibilidade do cliente para NÃO-gestão: responsável
    direto pelo cliente OU advogado (responsável/auxiliar) em caso do cliente."""
    atua_em_caso = (
        select(Case.id)
        .where(
            Case.client_id == Client.id,
            Case.deleted_at.is_(None),
            or_(Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id),
        )
        .exists()
    )
    return or_(Client.responsavel_id == cu.id, atua_em_caso)


async def _cliente_visivel(db: AsyncSession, cu: User, client: Client | None) -> bool:
    """Gate pontual (detalhe/escritas): gestão vê tudo; demais precisam ser
    responsáveis pelo cliente ou atuar em caso dele."""
    if client is None:
        return False
    if is_gestao(cu):
        return True
    if client.responsavel_id == cu.id:
        return True
    caso = (await db.execute(
        select(Case.id).where(
            Case.client_id == client.id,
            Case.deleted_at.is_(None),
            or_(Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id),
        ).limit(1)
    )).scalar_one_or_none()
    return caso is not None


async def _carregar_sociedade(db: AsyncSession, cu: User, sociedade_id: str) -> SociedadeCliente:
    """404 se não existe, soft-deleted OU fora do escopo do usuário (não vaza
    a existência de sociedade de cliente alheio — mesmo racional do 404 de
    clientes não encontrados)."""
    soc = (await db.execute(
        select(SociedadeCliente).where(
            SociedadeCliente.id == sociedade_id,
            SociedadeCliente.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not soc:
        raise HTTPException(status_code=404, detail="Sociedade não encontrada")

    cli = (await db.execute(
        select(Client).where(Client.id == soc.client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not await _cliente_visivel(db, cu, cli):
        raise HTTPException(status_code=404, detail="Sociedade não encontrada")
    return soc


def _f(v):
    return float(v) if v is not None else None


def _out_socio(s: SocioSociedade, total_quotas) -> dict:
    return {
        "id": s.id,
        "nome": s.nome,
        # LGPD: NUNCA o documento em claro — apenas a máscara.
        "documento_mascarado": s.documento_mascarado,
        "quotas": _f(s.quotas) or 0.0,
        "percentual": calcular_percentual(s.quotas, total_quotas),
        "pro_labore": _f(s.pro_labore),
        "administrador": bool(s.administrador),
    }


def _out_evento(e: EventoSocietario) -> dict:
    return {
        "id": e.id,
        "tipo": e.tipo,
        "descricao": e.descricao,
        "data_evento": e.data_evento.isoformat() if e.data_evento else None,
        "created_by": e.created_by,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


# ── Due diligence (gatilho estático) ─────────────────────────────────────────
# Declarado ANTES das rotas parametrizadas. Reusa o mecanismo existente de
# templates estáticos de due diligence (tabela due_diligence_templates,
# routers/novos_modulos.py) — ver decisão em services/due_diligence_empresarial.

@router.post("/due-diligence/template", status_code=201)
async def semear_template_due_diligence(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_escrita),
):
    """Find-or-create (idempotente) do template estático de due diligence
    empresarial (gatilho `due_diligence_empresarial`) em due_diligence_templates.
    Depois de semeado, aparece em GET /due-diligence/templates?dd_type=..."""
    import json
    from app.services.due_diligence_empresarial import (
        GATILHO, ITENS_DUE_DILIGENCE, NOME_TEMPLATE,
    )

    existente = (await db.execute(text(
        "SELECT id FROM due_diligence_templates "
        "WHERE dd_type = :dd AND is_active = TRUE LIMIT 1"
    ), {"dd": GATILHO})).scalar()
    if existente:
        return {"template_id": existente, "gatilho": GATILHO,
                "itens": ITENS_DUE_DILIGENCE, "criado": False}

    novo_id = (await db.execute(text("""
        INSERT INTO due_diligence_templates (id, name, dd_type, items, created_by)
        VALUES (gen_random_uuid()::text, :name, :dd, CAST(:items AS jsonb), :uid)
        RETURNING id
    """), {
        "name": NOME_TEMPLATE, "dd": GATILHO,
        "items": json.dumps(ITENS_DUE_DILIGENCE, ensure_ascii=False),
        "uid": cu.id,
    })).scalar()
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "due_diligence_templates",
                          novo_id, detalhes=f"template estático {GATILHO} semeado")
    await db.commit()
    return {"template_id": novo_id, "gatilho": GATILHO,
            "itens": ITENS_DUE_DILIGENCE, "criado": True}


# ── Sociedades ────────────────────────────────────────────────────────────────

@router.get("")
async def listar(
    client_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_leitura),
):
    socios_count = (
        select(sqlfunc.count(SocioSociedade.id))
        .where(SocioSociedade.sociedade_id == SociedadeCliente.id)
        .correlate(SociedadeCliente)
        .scalar_subquery()
    )
    q = (
        select(SociedadeCliente, Client.nome, Client.razao_social, socios_count)
        .join(Client, Client.id == SociedadeCliente.client_id)
        .where(SociedadeCliente.deleted_at.is_(None), Client.deleted_at.is_(None))
    )
    if not is_gestao(cu):
        q = q.where(_cond_cliente_visivel(cu))
    if client_id:
        q = q.where(SociedadeCliente.client_id == client_id)
    q = q.order_by(SociedadeCliente.created_at.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).all()

    data = [{
        "id": soc.id,
        "client_id": soc.client_id,
        "client_nome": cli_nome or cli_razao or "Cliente sem nome",
        "razao_social": soc.razao_social,
        "cnpj": soc.cnpj,
        "tipo_societario": soc.tipo_societario,
        "capital_social": _f(soc.capital_social),
        "socios_count": n_socios or 0,
    } for soc, cli_nome, cli_razao, n_socios in rows]

    return {"data": data, "total": total, "page": page, "page_size": page_size}


@router.post("", status_code=201)
async def criar(
    payload: SociedadeCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_escrita),
):
    cli = (await db.execute(
        select(Client).where(Client.id == payload.client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not await _cliente_visivel(db, cu, cli):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    soc = SociedadeCliente(
        id=str(uuid4()),
        client_id=payload.client_id,
        razao_social=payload.razao_social.strip(),
        cnpj=payload.cnpj,
        tipo_societario=payload.tipo_societario.value,
        capital_social=payload.capital_social,
    )
    db.add(soc)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "sociedades_cliente",
                          soc.id, detalhes=f"cliente {payload.client_id}: {soc.razao_social}")
    await db.commit()
    return {
        "id": soc.id, "client_id": soc.client_id,
        "razao_social": soc.razao_social, "cnpj": soc.cnpj,
        "tipo_societario": soc.tipo_societario,
        "capital_social": _f(soc.capital_social),
    }


@router.get("/{sociedade_id}")
async def detalhe(
    sociedade_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_leitura),
):
    soc = await _carregar_sociedade(db, cu, sociedade_id)

    cli = (await db.execute(
        select(Client).where(Client.id == soc.client_id)
    )).scalar_one_or_none()

    socios = (await db.execute(
        select(SocioSociedade)
        .where(SocioSociedade.sociedade_id == soc.id)
        .order_by(SocioSociedade.quotas.desc(), SocioSociedade.nome)
    )).scalars().all()

    eventos = (await db.execute(
        select(EventoSocietario)
        .where(EventoSocietario.sociedade_id == soc.id)
        .order_by(EventoSocietario.data_evento.desc(), EventoSocietario.created_at.desc())
    )).scalars().all()

    cap_table = montar_cap_table(soc.capital_social, [s.quotas for s in socios])
    total_quotas = cap_table["total_quotas"]

    return {
        "id": soc.id,
        "client_id": soc.client_id,
        "client_nome": cli.nome_exibicao if cli else None,
        "razao_social": soc.razao_social,
        "cnpj": soc.cnpj,
        "tipo_societario": soc.tipo_societario,
        "capital_social": _f(soc.capital_social),
        "created_at": soc.created_at.isoformat() if soc.created_at else None,
        "socios": [_out_socio(s, total_quotas) for s in socios],
        "cap_table": cap_table,
        "eventos": [_out_evento(e) for e in eventos],
    }


@router.patch("/{sociedade_id}")
async def atualizar(
    sociedade_id: str,
    payload: SociedadeUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_escrita),
):
    soc = await _carregar_sociedade(db, cu, sociedade_id)
    mudancas = payload.model_dump(exclude_unset=True)
    if "tipo_societario" in mudancas and mudancas["tipo_societario"] is not None:
        mudancas["tipo_societario"] = mudancas["tipo_societario"].value
    for k, v in mudancas.items():
        setattr(soc, k, v)
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", "sociedades_cliente",
                          sociedade_id, detalhes=f"campos: {sorted(mudancas)}")
    await db.commit()
    return {
        "id": soc.id, "client_id": soc.client_id,
        "razao_social": soc.razao_social, "cnpj": soc.cnpj,
        "tipo_societario": soc.tipo_societario,
        "capital_social": _f(soc.capital_social),
    }


@router.delete("/{sociedade_id}", response_model=MsgResponse)
async def remover(
    sociedade_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["admin", "socio"])),
):
    """Soft delete — mesmo gate de exclusão do CRM de clientes (admin/socio+)."""
    soc = await _carregar_sociedade(db, cu, sociedade_id)
    soc.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "sociedades_cliente",
                          sociedade_id)
    await db.commit()
    return MsgResponse(detail="Sociedade removida")


# ── Sócios ────────────────────────────────────────────────────────────────────

@router.post("/{sociedade_id}/socios", status_code=201)
async def adicionar_socio(
    sociedade_id: str,
    payload: SocioCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_escrita),
):
    soc = await _carregar_sociedade(db, cu, sociedade_id)

    # LGPD (padrão Bloco 6a): documento cifrado + índice cego + máscara.
    # O texto puro NUNCA é persistido nem retorna na resposta.
    pii = preparar_documento_socio(payload.documento)
    s = SocioSociedade(
        id=str(uuid4()),
        sociedade_id=soc.id,
        nome=payload.nome.strip(),
        quotas=payload.quotas,
        pro_labore=payload.pro_labore,
        administrador=payload.administrador,
        **pii,
    )
    db.add(s)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "socios_sociedade",
                          s.id, detalhes=f"sociedade {soc.id}: sócio {s.nome}")
    await db.commit()
    return _out_socio(s, None)  # percentual definitivo sai no GET do detalhe


async def _carregar_socio(db: AsyncSession, cu: User, socio_id: str) -> SocioSociedade:
    """Carrega o sócio e valida o acesso VIA sociedade (visibilidade do cliente).
    404 nos dois casos — não vaza existência fora do escopo."""
    s = (await db.execute(
        select(SocioSociedade).where(SocioSociedade.id == socio_id)
    )).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Sócio não encontrado")
    await _carregar_sociedade(db, cu, s.sociedade_id)  # 404 se fora do escopo
    return s


# Contrato do frontend (SociedadesCliente.tsx): PATCH/DELETE são FLAT em
# /empresarial/sociedades/socios/{socio_id} — a sociedade é resolvida pelo
# próprio sócio (e o acesso validado por ela).
@router.patch("/socios/{socio_id}")
async def atualizar_socio(
    socio_id: str,
    payload: SocioUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_escrita),
):
    s = await _carregar_socio(db, cu, socio_id)

    mudancas = payload.model_dump(exclude_unset=True)
    documento = mudancas.pop("documento", None)
    for k, v in mudancas.items():
        setattr(s, k, v)
    if documento is not None:
        for k, v in preparar_documento_socio(documento).items():
            setattr(s, k, v)

    campos = sorted(list(mudancas) + (["documento"] if documento is not None else []))
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", "socios_sociedade",
                          socio_id, detalhes=f"campos: {campos}")
    await db.commit()
    return _out_socio(s, None)


@router.delete("/socios/{socio_id}", response_model=MsgResponse)
async def remover_socio(
    socio_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_escrita),
):
    """Remove o sócio do quadro e registra AUTOMATICAMENTE o evento societário
    `saida_socio` (trilha societária não depende de disciplina manual)."""
    s = await _carregar_socio(db, cu, socio_id)

    evento = EventoSocietario(
        id=str(uuid4()),
        sociedade_id=s.sociedade_id,
        tipo=TipoEventoSocietario.saida_socio.value,
        descricao=f"Saída do sócio {s.nome} (removido do quadro societário)",
        data_evento=date.today(),
        created_by=cu.id,
    )
    db.add(evento)
    await db.delete(s)
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "socios_sociedade",
                          socio_id, detalhes=f"sociedade {s.sociedade_id}: saída de "
                                             f"{s.nome} (evento {evento.id})")
    await db.commit()
    return MsgResponse(detail="Sócio removido — evento 'saida_socio' registrado")


# ── Eventos societários ───────────────────────────────────────────────────────

@router.post("/{sociedade_id}/eventos", status_code=201)
async def registrar_evento(
    sociedade_id: str,
    payload: EventoCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_escrita),
):
    soc = await _carregar_sociedade(db, cu, sociedade_id)
    e = EventoSocietario(
        id=str(uuid4()),
        sociedade_id=soc.id,
        tipo=payload.tipo.value,
        descricao=payload.descricao,
        data_evento=payload.data_evento,
        created_by=cu.id,
    )
    db.add(e)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "eventos_societarios",
                          e.id, detalhes=f"sociedade {soc.id}: {e.tipo}")
    await db.commit()
    return _out_evento(e)
