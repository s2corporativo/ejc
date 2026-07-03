# ── app/routers/export.py ─────────────────────────────────────────────────────
# Exportação CSV (clientes, casos, honorários), PDF por caso e DOCX genérico.
from __future__ import annotations
import csv
import io
import re
import unicodedata
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.client import Client
from app.models.case import Case
from app.models.fee import Fee
from app.services.docx_service import gerar_docx_async

router = APIRouter(prefix="/export", tags=["Exportação"])


def _csv(filename: str, header: list[str], linhas: list[list]) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(header)
    w.writerows(linhas)
    data = "\ufeff" + buf.getvalue()    # BOM → acentos corretos no Excel
    return StreamingResponse(
        iter([data]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _ve_todos(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]


@router.get("/clientes.csv")
async def export_clientes(db: AsyncSession = Depends(get_db),
                          cu: User = Depends(get_current_user)):
    if cu.role.value == "cliente_externo":
        raise HTTPException(403, "Não autorizado")
    rows = (await db.execute(
        select(Client).where(Client.deleted_at.is_(None))
        .order_by(Client.created_at.desc())
    )).scalars().all()
    linhas = [[c.nome or c.razao_social or "", c.tipo.value,
               c.cpf or c.cnpj or "", c.email or "", c.telefone or "",
               str(c.status.value)] for c in rows]
    return _csv("clientes.csv",
                ["Nome", "Tipo", "Documento", "Email", "Telefone", "Status"], linhas)


@router.get("/casos.csv")
async def export_casos(db: AsyncSession = Depends(get_db),
                       cu: User = Depends(get_current_user)):
    if cu.role.value == "cliente_externo":
        raise HTTPException(403, "Não autorizado")
    q = select(Case).where(Case.deleted_at.is_(None))
    if not _ve_todos(cu):
        q = q.where(or_(Case.advogado_responsavel_id == cu.id,
                        Case.advogado_auxiliar_id == cu.id))
    rows = (await db.execute(q.order_by(Case.created_at.desc()))).scalars().all()
    linhas = [[c.numero_interno or "", c.titulo, str(c.area.value),
               str(c.status.value), c.numero_processo or "",
               c.parte_contraria or ""] for c in rows]
    return _csv("casos.csv",
                ["Nº interno", "Título", "Área", "Status",
                 "Nº processo", "Parte contrária"], linhas)


@router.get("/casos/{case_id}.pdf")
async def export_caso_pdf(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Exporta PDF do dossiê resumido de um caso.
    Restrito a staff (advogado+). Verifica visibilidade do caso.
    """
    if cu.role.value == "cliente_externo":
        raise HTTPException(403, "Não autorizado")

    # Verifica acesso ao caso
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    if not _ve_todos(cu):
        q = q.where(or_(
            Case.advogado_responsavel_id == cu.id,
            Case.advogado_auxiliar_id    == cu.id,
        ))
    case = (await db.execute(q)).scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Caso não encontrado ou sem acesso")

    try:
        from app.services.pdf_service import gerar_caso_pdf
        pdf_bytes = await gerar_caso_pdf(db, case_id, cu.id)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar PDF: {str(e)[:200]}")

    filename = f"caso_{case.numero_interno or case_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ═══ DOCX genérico (pareceres, propostas, relatórios de outras telas) ═══

_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DocxExportPayload(BaseModel):
    """Payload do DOCX genérico.

    meta (opcional): {"numero_processo": "0000000-00.0000.0.00.0000"} —
    exibido no cabeçalho abaixo do nome do escritório.
    """
    titulo: str = Field(..., min_length=1, max_length=255)
    conteudo_md: str = Field(..., min_length=1)
    meta: Optional[dict] = None


def _slug_arquivo(titulo: str, fallback: str = "documento") -> str:
    base = unicodedata.normalize("NFKD", titulo or "").encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:60]
    return slug or fallback


@router.post("/docx")
async def export_docx(
    payload: DocxExportPayload,
    cu: User = Depends(get_current_user),
):
    """
    Gera DOCX editável (Times 12pt, margens ABNT, timbre do escritório) a
    partir de markdown — reuso genérico p/ pareceres, propostas e relatórios.
    Restrito a staff. Para peças jurídicas persistidas, use
    GET /legal-docs/{id}/exportar-docx (com audit log por recurso).
    """
    if cu.role.value == "cliente_externo":
        raise HTTPException(403, "Não autorizado")

    try:
        docx_bytes = await gerar_docx_async(
            payload.titulo, payload.conteudo_md, payload.meta or {}
        )
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar DOCX: {str(e)[:200]}")

    filename = f"{_slug_arquivo(payload.titulo)}.docx"
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type=_DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/honorarios.csv")
async def export_honorarios(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # Financeiro: restrito a sócio+ (ou financeiro).
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"] and cu.role.value != "financeiro":
        raise HTTPException(403, "Não autorizado")
    rows = (await db.execute(
        select(Fee).where(Fee.deleted_at.is_(None)).order_by(Fee.created_at.desc())
    )).scalars().all()
    linhas = [[f.descricao or "", float(f.valor or 0), str(f.status.value),
               str(f.tipo.value) if getattr(f, "tipo", None) else ""] for f in rows]
    return _csv("honorarios.csv",
                ["Descrição", "Valor", "Status", "Tipo"], linhas)
