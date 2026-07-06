# ── app/routers/templates.py ─────────────────────────────────────────────────
# Templates de peças: CRUD + geração de peça a partir do caso.
# Substituição segura de {{variaveis}} — sem execução de código (não-Jinja).
import re
from datetime import datetime, timezone, date
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.utils.format import formatar_brl  # #41: formatador BRL único
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.template import DocTemplate
from app.models.client import Client
from app.models.legal_doc import LegalDoc, PecaTipo, PecaStatus
from app.models.audit_log import criar_audit_log
from app.schemas.common import MsgResponse

router = APIRouter(prefix="/templates", tags=["Templates de Peças"])

# Variáveis suportadas (documentadas para o usuário)
VARIAVEIS = [
    "cliente_nome", "cliente_cpf_cnpj", "cliente_endereco",
    "numero_processo", "parte_contraria", "comarca", "vara",
    "valor_causa", "area", "data_hoje",
    "advogado_nome", "advogado_oab",
]


class TemplateIn(BaseModel):
    titulo: str
    tipo_peca: str
    area: Optional[str] = None
    descricao: Optional[str] = None
    conteudo: str


class GerarIn(BaseModel):
    case_id: str
    titulo_peca: Optional[str] = None


def _render(conteudo: str, ctx: dict) -> str:
    """Substituição literal de {{var}} — imune a injeção de template."""
    def repl(m):
        return str(ctx.get(m.group(1).strip(), f"[{m.group(1).strip()}?]"))
    return re.sub(r"\{\{\s*([a-z_]+)\s*\}\}", repl, conteudo)


_MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _data_extenso(d: date) -> str:
    """Data por extenso em pt-BR, independente do locale do container."""
    return f"{d.day:02d} de {_MESES_PT[d.month - 1]} de {d.year}"


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(DocTemplate).where(
        DocTemplate.deleted_at.is_(None), DocTemplate.ativo == True,
    ).order_by(DocTemplate.titulo)
    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery()))).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {
        "data": [
            {"id": t.id, "titulo": t.titulo, "tipo_peca": t.tipo_peca,
             "area": t.area, "descricao": t.descricao}
            for t in rows
        ],
        "total": total, "variaveis_disponiveis": VARIAVEIS,
    }


@router.get("/{tpl_id}")
async def detalhe(
    tpl_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    t = (await db.execute(select(DocTemplate).where(
        DocTemplate.id == tpl_id, DocTemplate.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    return {"id": t.id, "titulo": t.titulo, "tipo_peca": t.tipo_peca,
            "area": t.area, "descricao": t.descricao, "conteudo": t.conteudo}


@router.post("/", status_code=201)
async def criar(
    payload: TemplateIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio", "advogado"])),
):
    tipos_validos = [t.value for t in PecaTipo]
    if payload.tipo_peca not in tipos_validos:
        raise HTTPException(status_code=422, detail=f"tipo_peca inválido. Use: {tipos_validos}")
    t = DocTemplate(id=str(uuid4()), created_by=cu.id, **payload.model_dump())
    db.add(t)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "doc_templates", t.id)
    await db.commit()
    return {"id": t.id, "detail": "Template criado"}


@router.post("/{tpl_id}/gerar", status_code=201)
async def gerar_peca(
    tpl_id: str, payload: GerarIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Gera LegalDoc rascunho com variáveis do caso preenchidas."""
    t = (await db.execute(select(DocTemplate).where(
        DocTemplate.id == tpl_id, DocTemplate.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template não encontrado")

    # Gate de ownership (IDOR): só quem atua no caso (ou gestão) gera peça dele.
    case = await verificar_acesso_caso(db, cu, payload.case_id)

    client = (await db.execute(select(Client).where(
        Client.id == case.client_id
    ))).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Caso sem cliente vinculado")

    endereco = ", ".join(filter(None, [
        client.logradouro, client.numero, client.bairro,
        f"{client.cidade}/{client.estado}" if client.cidade else None,
    ])) or "—"

    ctx = {
        "cliente_nome": client.nome or client.razao_social or "—",
        "cliente_cpf_cnpj": client.cpf or client.cnpj or "—",
        "cliente_endereco": endereco,
        "numero_processo": case.numero_processo or "—",
        "parte_contraria": case.parte_contraria or "—",
        "comarca": case.comarca or "—",
        "vara": case.vara or "—",
        "valor_causa": formatar_brl(case.valor_causa) if case.valor_causa else "—",
        "area": case.area.value if hasattr(case.area, "value") else str(case.area),
        "data_hoje": _data_extenso(date.today()),
        "advogado_nome": cu.full_name,
        "advogado_oab": cu.oab_number or "—",
    }

    doc = LegalDoc(
        id=str(uuid4()),
        titulo=payload.titulo_peca or f"{t.titulo} — {ctx['cliente_nome']}",
        tipo_peca=PecaTipo(t.tipo_peca),
        status=PecaStatus.rascunho,
        conteudo=_render(t.conteudo, ctx),
        ai_generated=False,   # template ≠ IA; revisão segue boas práticas normais
        case_id=case.id, created_by=cu.id,
    )
    db.add(doc)
    await criar_audit_log(
        db, cu.id, cu.role.value, "CREATE", "legal_docs", doc.id,
        detalhes=f"Gerada do template '{t.titulo}'",
    )
    await db.commit()
    return {"id": doc.id, "titulo": doc.titulo, "detail": "Peça gerada como rascunho"}


@router.delete("/{tpl_id}", response_model=MsgResponse)
async def remover(
    tpl_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    t = (await db.execute(select(DocTemplate).where(
        DocTemplate.id == tpl_id, DocTemplate.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    t.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return MsgResponse(detail="Template removido")
