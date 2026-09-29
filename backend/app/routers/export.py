# ── app/routers/export.py ─────────────────────────────────────────────────────
# Exportação CSV (clientes, casos, honorários), PDF por caso e DOCX genérico.
from __future__ import annotations
import csv
import io
import logging
import re
import unicodedata
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import AliasChoices, BaseModel, Field
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.csv_safe import sanitize_csv_row
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.audit_log import criar_audit_log
from app.models.user import User
from app.models.client import Client
from app.models.case import Case
from app.models.fee import Fee
from app.services.docx_service import gerar_docx_async

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/export", tags=["Exportação"])


def _csv(filename: str, header: list[str], linhas: list[list]) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(sanitize_csv_row(header))
    w.writerows(sanitize_csv_row(linha) for linha in linhas)
    data = "\ufeff" + buf.getvalue()    # BOM → acentos corretos no Excel
    return StreamingResponse(
        iter([data]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _ve_todos(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]


# ── Gate do export de cadastro de clientes (M04) ─────────────────────────────
# Allowlist EXATA, no estilo EQUIPE_JURIDICA (core/security.py:57): sem
# fallback hierárquico, nomeada e reutilizável para teste.
#
# ATENÇÃO (core/security.py:43-56): NÃO trocar isto por `require_roles`/piso
# numérico. `estagiario` (3) e `secretaria` (2) ficariam de fora por nível,
# mas o piso escolheria o menor nível da lista (financeiro = 4) e abriria a
# exportação — o mesmo vazamento de função que a Issue #694 fechou na
# superfície jurídica. A allowlist é deliberadamente não hierárquica.
#
# O conjunto é o de M04 (homologação 2026-08-15) e foi preservado exatamente,
# `financeiro` incluso: reduzir esse papel é decisão do titular, não do
# endurecimento técnico.
EXPORT_CLIENTES_ROLES: frozenset[str] = frozenset({
    "superadmin", "admin", "socio", "financeiro",
})


def requer_export_clientes(cu: "User", detalhe: str = "Exportação de clientes "
                               "restrita a gestão e financeiro") -> None:
    """Gate do `GET /export/clientes.csv` (PII de cadastro em claro).

    Allowlist EXATA (EXPORT_CLIENTES_ROLES), sem fallback hierárquico — ver o
    alerta em core/security.py:43-56. Chame no CORPO do handler, nunca como
    `Depends` (o FastAPI trataria `cu`/`detalhe` como query params)."""
    role = getattr(getattr(cu, "role", None), "value", None) or str(getattr(cu, "role", "") or "")
    if role not in EXPORT_CLIENTES_ROLES:
        raise HTTPException(status_code=403, detail=detalhe)


def _escopo_clientes(q, cu: "User"):
    """Restringe o export de clientes ao que o usuário pode ver.

    DECISÃO DO TITULAR (2026-09-29): escopo RESTRITO, sem caminho alternativo e
    sem escopo próprio do financeiro. A gestão (`_ve_todos`) vê a base inteira;
    qualquer outro papel vê cliente PRÓPRIO (Client.responsavel_id == cu.id) OU
    cliente com ao menos um caso visível a ele — o mesmo par responsável/
    auxiliar de `export_casos`. Note que `financeiro` não está na gestão: ele
    mantém o acesso ao endpoint (allowlist intacta, ver acima) e simplesmente
    passa a ver menos linhas. Não reintroduza um "escopo do financeiro" sem
    decisão nova do titular.

    Por que os dois predicados (e não um só):
      * só "cliente com caso visível" apagaria leads e cadastros de clientes
        ainda sem caso — o `responsavel_id` existe justamente para ownership
        de cliente que ainda não virou processo;
      * só "cliente próprio" devolveria lista vazia para o advogado, cujo
        trabalho é justamente o caso que alguém da equipe abriu.
    A OR é a que preserva as duas coisas.
    """
    if _ve_todos(cu):
        return q
    visiveis = select(Case.client_id).where(
        Case.deleted_at.is_(None),
        or_(Case.advogado_responsavel_id == cu.id,
            Case.advogado_auxiliar_id == cu.id),
    )
    return q.where(or_(Client.responsavel_id == cu.id, Client.id.in_(visiveis)))


async def _registrar_exportacao(db, cu, *, acao: str, entidade: str,
                                registro_id: str | None, detalhes: str) -> None:
    """Trilha WORM única dos exports (fail-closed).

    DECISÃO DO TITULAR (2026-09-29): falhar FECHADO. O padrão comum seria
    engolir a exceção (log e seguir com a exportação) — aqui não: se o log ou
    o commit falhar, sobe 503 e nada é exportado. Não degrade sem decisão nova
    do titular.

    Grava e COMMITA antes de o handler montar qualquer corpo de resposta: um
    commit que falha estoura antes de qualquer byte de PII sair. O `detalhes`
    é de contagem/escopo por construção — nunca nome, documento, e-mail,
    telefone ou nome de parte.

    Fonte única para os três exports de dado (clientes.csv, casos.csv,
    caso.pdf) para que as trilhas não divirjam.
    """
    try:
        from app.core.request_context import get_client_ip
        await criar_audit_log(
            db,
            cu.id, cu.role.value, acao, entidade, registro_id,
            detalhes=detalhes, ip=get_client_ip(),
        )
        await db.commit()
    except Exception:
        logger.exception("Falha ao registrar trilha de exportação %s", acao)
        raise HTTPException(status_code=503,
                            detail="Falha ao registrar a exportação; nenhuma "
                                   "informação foi exportada")


@router.get(
    "/clientes.csv",
    dependencies=[Depends(rate_limit("export-clientes", 5))],
)
async def export_clientes(db: AsyncSession = Depends(get_db),
                          cu: User = Depends(get_current_user)):
    # M04 (homologação 2026-08-15): exportação de cadastro de clientes (com
    # CPF/CNPJ em claro) restrita a gestão e financeiro — LGPD mínimo acesso.
    # Gate nomeado e exato; ver EXPORT_CLIENTES_ROLES acima.
    requer_export_clientes(cu)
    q = select(Client).where(Client.deleted_at.is_(None))
    integral = _ve_todos(cu)
    q = _escopo_clientes(q, cu)
    rows = (await db.execute(
        q.order_by(Client.created_at.desc())
    )).scalars().all()
    # Documento decifrado sob demanda (cutover C6/LGPD): não há mais texto puro
    # no banco. Como esta é uma exportação deliberada, o ato recebe rate limit
    # e trilha WORM sem registrar qualquer PII no próprio log. A trilha é
    # gravada (fail-closed) ANTES de o corpo ser montado.
    linhas = [[c.nome or c.razao_social or "", c.tipo.value,
               c.documento_plain or "", c.email or "", c.telefone or "",
               str(c.status.value)] for c in rows]
    await _registrar_exportacao(
        db, cu,
        acao="EXPORT_CLIENTES_CSV",
        entidade="clients",
        registro_id=None,
        detalhes=f"escopo={'integral' if integral else 'proprio'}; "
                 f"registros={len(rows)}",
    )
    return _csv("clientes.csv",
                ["Nome", "Tipo", "Documento", "Email", "Telefone", "Status"], linhas)


@router.get("/casos.csv")
async def export_casos(db: AsyncSession = Depends(get_db),
                       cu: User = Depends(get_current_user)):
    if cu.role.value == "cliente_externo":
        raise HTTPException(403, "Não autorizado")
    q = select(Case).where(Case.deleted_at.is_(None))
    integral = _ve_todos(cu)
    if not integral:
        q = q.where(or_(Case.advogado_responsavel_id == cu.id,
                        Case.advogado_auxiliar_id == cu.id))
    rows = (await db.execute(q.order_by(Case.created_at.desc()))).scalars().all()
    linhas = [[c.numero_interno or "", c.titulo, str(c.area.value),
               str(c.status.value), c.numero_processo or "",
               c.parte_contraria or ""] for c in rows]
    await _registrar_exportacao(
        db, cu,
        acao="EXPORT_CASOS_CSV",
        entidade="cases",
        registro_id=None,
        detalhes=f"escopo={'integral' if integral else 'proprio'}; "
                 f"registros={len(rows)}",
    )
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
    integral = _ve_todos(cu)
    if not integral:
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
    except Exception:
        logger.exception("Erro ao gerar PDF do caso %s", case_id)
        raise HTTPException(500, "Erro ao gerar o PDF")

    filename = f"caso_{case.numero_interno or case_id}.pdf"
    await _registrar_exportacao(
        db, cu,
        acao="EXPORT_CASO_PDF",
        entidade="cases",
        registro_id=case.id,
        detalhes=f"escopo={'integral' if integral else 'proprio'}; registros=1",
    )
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
    # Aceita tanto "conteudo_md" (nome canônico) quanto o intuitivo "conteudo"
    # — evita 422 para quem chama a API pelo nome mais óbvio.
    conteudo_md: str = Field(
        ..., min_length=1,
        validation_alias=AliasChoices("conteudo_md", "conteudo"),
    )
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
    except Exception:
        logger.exception("Erro ao gerar DOCX")
        raise HTTPException(500, "Erro ao gerar o DOCX")

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