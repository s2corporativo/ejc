# ── app/routers/search.py ─────────────────────────────────────────────────────
# Busca global unificada respeitando escopo, RBAC e minimização de PII.
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ownership import ids_clientes_visiveis, visao_total_clientes
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.case_parte import CaseParte
from app.models.client import Client
from app.models.deadline import Deadline
from app.models.document import Document
from app.models.fee import Fee
from app.models.legal_doc import LegalDoc
from app.models.process import Process
from app.models.task import Task
from app.models.user import User
from app.routers.clients import _CLIENTES
from app.services.module_registry import PERFIS_FINANCEIRO
from app.services.pii_crypto import (
    hash_documento,
    mascarar_documento,
    normalizar_documento,
)

router = APIRouter(prefix="/search", tags=["Busca global"])


def _ve_todos(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]


def _escopo_clientes(stmt, cu: User):
    """Aplica a mesma segregação de carteira do CRM à busca identificável."""
    if visao_total_clientes(cu):
        return stmt
    return stmt.where(Client.id.in_(ids_clientes_visiveis(cu)))


def _ids_casos_do_usuario(user: User):
    return (
        select(Case.id)
        .where(
            Case.deleted_at.is_(None),
            or_(
                Case.advogado_responsavel_id == user.id,
                Case.advogado_auxiliar_id == user.id,
            ),
        )
        .scalar_subquery()
    )


def _ids_clientes_dos_casos_do_usuario(user: User):
    return (
        select(Case.client_id)
        .where(
            Case.deleted_at.is_(None),
            Case.client_id.is_not(None),
            or_(
                Case.advogado_responsavel_id == user.id,
                Case.advogado_auxiliar_id == user.id,
            ),
        )
        .scalar_subquery()
    )


def _escopo_casos(stmt, cu: User):
    if not _ve_todos(cu):
        stmt = stmt.where(
            or_(
                Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id,
            )
        )
    return stmt


def _escopo_documentos(stmt, cu: User):
    """Espelha a listagem do GED sem pesquisar conteúdo/OCR.

    A busca global retorna somente metadados de documentos visíveis. Perfis
    abaixo de sócio não recebem documentos restritos/confidenciais e, sem
    gestão, o escopo é carteira, cliente de caso próprio ou upload realmente
    avulso feito pelo próprio usuário.
    """
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        stmt = stmt.where(Document.confidencialidade.in_(["normal", "interno"]))
    if _ve_todos(cu):
        return stmt
    return stmt.where(
        or_(
            Document.case_id.in_(_ids_casos_do_usuario(cu)),
            (
                Document.case_id.is_(None)
                & Document.client_id.in_(_ids_clientes_dos_casos_do_usuario(cu))
            ),
            (
                Document.case_id.is_(None)
                & Document.client_id.is_(None)
                & (Document.uploaded_by == cu.id)
            ),
        )
    )


def _escopo_tarefas(stmt, cu: User):
    """Com caso vale a carteira; sem caso, responsabilidade/autoria direta."""
    if _ve_todos(cu):
        return stmt
    return stmt.where(
        or_(
            Task.case_id.in_(_ids_casos_do_usuario(cu)),
            (
                Task.case_id.is_(None)
                & or_(Task.responsavel_id == cu.id, Task.criado_por == cu.id)
            ),
        )
    )


def _escopo_prazos(stmt, cu: User):
    """Prazo com caso segue carteira; prazo avulso é pessoal ao responsável."""
    if _ve_todos(cu):
        return stmt
    return stmt.where(
        or_(
            Deadline.case_id.in_(_ids_casos_do_usuario(cu)),
            (
                Deadline.case_id.is_(None)
                & (Deadline.responsavel_id == cu.id)
            ),
        )
    )


def _escopo_fees(stmt, cu: User):
    """Espelha `fees._filtro_fees_lista` sem expor valores na busca."""
    if cu.role.value in PERFIS_FINANCEIRO:
        return stmt
    return stmt.where(Fee.case_id.in_(_ids_casos_do_usuario(cu)))


def _so_digitos(coluna):
    return func.regexp_replace(func.coalesce(coluna, ""), "[^0-9]", "", "g")


def _mascarar_documento(value: str | None) -> str:
    """Máscara canônica (services/pii_crypto) adaptada ao subtítulo da busca:
    string sempre — vazia quando não há documento, rótulo genérico quando o
    valor existe mas tem comprimento inesperado (não é CPF nem CNPJ)."""
    if not normalizar_documento(value):
        return ""
    return mascarar_documento(value) or "Documento protegido"


def _item_caso(caso: Case, subtitulo: str) -> dict:
    return {
        "tipo": "caso",
        "id": caso.id,
        "titulo": caso.titulo,
        "subtitulo": subtitulo,
        "link": f"/casos/{caso.id}",
    }


def _status_texto(value) -> str:
    return str(value.value) if hasattr(value, "value") else str(value or "")


async def _auditar_busca_pii(
    db: AsyncSession,
    cu: User,
    total: int,
) -> None:
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "SEARCH_PII",
        "global_search",
        detalhes=f"Busca exata por CPF/CNPJ; resultados={total}",
    )
    await db.commit()


@router.get("")
@limiter.limit("30/minute")
async def busca_global(
    request: Request,
    q: str = Query(..., min_length=2, max_length=120),
    tipo: str = Query("tudo", pattern="^(tudo|parte|cpf|processo)$"),
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if cu.role.value == "cliente_externo":
        return {"q": q, "tipo": tipo, "resultados": []}

    termo = f"%{q.strip()}%"
    out: list[dict] = []

    if tipo == "parte":
        query = _escopo_casos(
            select(CaseParte, Case)
            .join(Case, Case.id == CaseParte.case_id)
            .where(
                Case.deleted_at.is_(None),
                CaseParte.ativo.is_(True),
                CaseParte.nome.ilike(termo),
            )
            .order_by(Case.updated_at.desc()),
            cu,
        )
        casos_vistos: set[str] = set()
        for parte, caso in (await db.execute(query.limit(limit * 3))).all():
            if caso.id in casos_vistos:
                continue
            casos_vistos.add(caso.id)
            out.append(_item_caso(caso, f"Parte: {parte.nome}"))
            if len(out) >= limit:
                break
        return {"q": q, "tipo": tipo, "total": len(out), "resultados": out}

    if tipo == "cpf":
        digitos = normalizar_documento(q) or ""
        if len(digitos) not in (11, 14):
            raise HTTPException(
                status_code=422,
                detail="Informe um CPF ou CNPJ completo para a busca protegida.",
            )

        if cu.role.value in _CLIENTES:
            try:
                blind_index = hash_documento(digitos)
            except RuntimeError:
                blind_index = None
            # Cutover C6/LGPD: busca de cliente por documento é feita SOMENTE
            # pelo índice cego (HMAC) — não há mais cpf/cnpj em texto puro no
            # banco. Igualdade exata (CPF/CNPJ completo). Sem PII_HASH_KEY
            # (blind_index None) não há como casar documento → pula clientes.
            if blind_index:
                cond_cli = (
                    Client.cpf_hash == blind_index
                    if len(digitos) == 11
                    else Client.cnpj_hash == blind_index
                )
                client_query = _escopo_clientes(
                    select(Client).where(Client.deleted_at.is_(None), cond_cli),
                    cu,
                ).order_by(Client.updated_at.desc())
                for client in (
                    await db.execute(client_query.limit(limit))
                ).scalars().all():
                    documento = client.documento_plain
                    out.append(
                        {
                            "tipo": "cliente",
                            "id": client.id,
                            "titulo": client.nome or client.razao_social or "—",
                            "subtitulo": _mascarar_documento(documento),
                            "link": "/clientes",
                        }
                    )

        parte_query = _escopo_casos(
            select(CaseParte, Case)
            .join(Case, Case.id == CaseParte.case_id)
            .where(
                Case.deleted_at.is_(None),
                CaseParte.ativo.is_(True),
                _so_digitos(CaseParte.cpf_cnpj) == digitos,
            )
            .order_by(Case.updated_at.desc()),
            cu,
        )
        casos_vistos: set[str] = set()
        for parte, caso in (
            await db.execute(parte_query.limit(limit * 3))
        ).all():
            if caso.id in casos_vistos:
                continue
            casos_vistos.add(caso.id)
            out.append(
                _item_caso(
                    caso,
                    f"Parte: {parte.nome} · {_mascarar_documento(parte.cpf_cnpj)}",
                )
            )
            if len(casos_vistos) >= limit:
                break
        await _auditar_busca_pii(db, cu, len(out))
        return {"q": q, "tipo": tipo, "total": len(out), "resultados": out}

    if tipo == "processo":
        digitos = normalizar_documento(q) or ""
        casos_vistos: set[str] = set()
        conds = [Case.numero_processo.ilike(termo), Case.numero_interno.ilike(termo)]
        if digitos:
            alvo = f"%{digitos}%"
            conds.extend(
                [
                    _so_digitos(Case.numero_processo).like(alvo),
                    _so_digitos(Case.numero_interno).like(alvo),
                ]
            )
        case_query = _escopo_casos(
            select(Case)
            .where(Case.deleted_at.is_(None), or_(*conds))
            .order_by(Case.updated_at.desc()),
            cu,
        )
        for caso in (await db.execute(case_query.limit(limit))).scalars().all():
            casos_vistos.add(caso.id)
            out.append(
                _item_caso(
                    caso,
                    caso.numero_processo or caso.numero_interno or "",
                )
            )

        process_conds = [Process.numero_cnj.ilike(termo)]
        if digitos:
            process_conds.append(_so_digitos(Process.numero_cnj).like(f"%{digitos}%"))
        process_query = _escopo_casos(
            select(Process, Case)
            .join(Case, Case.id == Process.case_id)
            .where(
                Process.deleted_at.is_(None),
                Case.deleted_at.is_(None),
                or_(*process_conds),
            )
            .order_by(Case.updated_at.desc()),
            cu,
        )
        adicionados = 0
        for process, caso in (
            await db.execute(process_query.limit(limit * 3))
        ).all():
            if caso.id in casos_vistos:
                continue
            casos_vistos.add(caso.id)
            out.append(_item_caso(caso, process.numero_cnj or ""))
            adicionados += 1
            if adicionados >= limit:
                break
        return {"q": q, "tipo": tipo, "total": len(out), "resultados": out}

    # Busca geral: clientes somente para perfis do CRM e somente por nome/razão.
    if cu.role.value in _CLIENTES:
        client_query = _escopo_clientes(
            select(Client).where(
                Client.deleted_at.is_(None),
                or_(
                    Client.nome.ilike(termo),
                    Client.razao_social.ilike(termo),
                ),
            ),
            cu,
        )
        clients = (await db.execute(client_query.limit(limit))).scalars().all()
        for client in clients:
            out.append(
                {
                    "tipo": "cliente",
                    "id": client.id,
                    "titulo": client.nome or client.razao_social or "—",
                    "subtitulo": _mascarar_documento(client.documento_plain),
                    "link": "/clientes",
                }
            )

    case_query = select(Case).where(
        Case.deleted_at.is_(None),
        or_(
            Case.titulo.ilike(termo),
            Case.numero_interno.ilike(termo),
            Case.numero_processo.ilike(termo),
        ),
    )
    if not _ve_todos(cu):
        case_query = case_query.where(
            or_(
                Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id,
            )
        )
    for case in (await db.execute(case_query.limit(limit))).scalars().all():
        out.append(
            {
                "tipo": "caso",
                "id": case.id,
                "titulo": case.titulo,
                "subtitulo": case.numero_interno or case.numero_processo or "",
                "link": f"/casos/{case.id}",
            }
        )

    legal_doc_query = select(LegalDoc).where(
        LegalDoc.deleted_at.is_(None),
        LegalDoc.titulo.ilike(termo),
    )
    if not _ve_todos(cu):
        legal_doc_query = legal_doc_query.where(
            LegalDoc.case_id.in_(_ids_casos_do_usuario(cu))
        )
    for legal_doc in (
        await db.execute(legal_doc_query.limit(limit))
    ).scalars().all():
        out.append(
            {
                "tipo": "peca",
                "id": legal_doc.id,
                "titulo": legal_doc.titulo,
                "subtitulo": _status_texto(legal_doc.status),
                "link": (
                    f"/casos/{legal_doc.case_id}?tab=pecas"
                    if legal_doc.case_id
                    else "/pecas"
                ),
            }
        )

    # GED: título apenas. OCR/conteúdo fica fora da busca global para impedir
    # snippets ou inferência de conteúdo sensível em uma superfície transversal.
    document_query = _escopo_documentos(
        select(Document).where(
            Document.deleted_at.is_(None),
            Document.titulo.ilike(termo),
        ),
        cu,
    ).order_by(Document.created_at.desc())
    for document in (
        await db.execute(document_query.limit(limit))
    ).scalars().all():
        out.append(
            {
                "tipo": "documento",
                "id": document.id,
                "titulo": document.titulo,
                "subtitulo": document.tipo or "Documento",
                "link": (
                    f"/casos/{document.case_id}?tab=documentos"
                    if document.case_id
                    else "/documentos"
                ),
            }
        )

    task_query = _escopo_tarefas(
        select(Task).where(
            Task.deleted_at.is_(None),
            Task.titulo.ilike(termo),
        ),
        cu,
    ).order_by(Task.updated_at.desc())
    for task in (await db.execute(task_query.limit(limit))).scalars().all():
        subtitulo = _status_texto(task.status)
        if task.data_limite:
            subtitulo = f"{subtitulo} · {task.data_limite.isoformat()}"
        out.append(
            {
                "tipo": "tarefa",
                "id": task.id,
                "titulo": task.titulo,
                "subtitulo": subtitulo,
                "link": "/atividades?tipo=tarefa",
            }
        )

    deadline_query = _escopo_prazos(
        select(Deadline).where(
            Deadline.deleted_at.is_(None),
            Deadline.titulo.ilike(termo),
        ),
        cu,
    ).order_by(Deadline.data_prazo.asc())
    for deadline in (
        await db.execute(deadline_query.limit(limit))
    ).scalars().all():
        out.append(
            {
                "tipo": "prazo",
                "id": deadline.id,
                "titulo": deadline.titulo,
                "subtitulo": (
                    f"{_status_texto(deadline.status)} · {deadline.data_prazo.isoformat()}"
                ),
                "link": "/atividades?tipo=prazo",
            }
        )

    # Financeiro: mesma visibilidade do router de honorários, sem valor,
    # percentual, observação ou dados de pagamento na superfície global.
    fee_query = _escopo_fees(
        select(Fee).where(
            Fee.deleted_at.is_(None),
            Fee.descricao.ilike(termo),
        ),
        cu,
    ).order_by(Fee.updated_at.desc())
    for fee in (await db.execute(fee_query.limit(limit))).scalars().all():
        out.append(
            {
                "tipo": "financeiro",
                "id": fee.id,
                "titulo": fee.descricao,
                "subtitulo": _status_texto(fee.status),
                "link": (
                    f"/casos/{fee.case_id}?tab=financeiro"
                    if fee.case_id
                    else "/financeiro"
                ),
            }
        )

    return {"q": q, "tipo": tipo, "total": len(out), "resultados": out}
