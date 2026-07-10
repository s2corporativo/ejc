# ── app/routers/search.py ─────────────────────────────────────────────────────
# Busca global unificada respeitando escopo, RBAC e minimização de PII.
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.case_parte import CaseParte
from app.models.client import Client
from app.models.legal_doc import LegalDoc
from app.models.process import Process
from app.models.user import User
from app.routers.clients import _CLIENTES
from app.services.pii_crypto import hash_documento, normalizar_documento

router = APIRouter(prefix="/search", tags=["Busca global"])


def _ve_todos(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]


def _escopo_casos(stmt, cu: User):
    if not _ve_todos(cu):
        stmt = stmt.where(
            or_(
                Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id,
            )
        )
    return stmt


def _so_digitos(coluna):
    return func.regexp_replace(func.coalesce(coluna, ""), "[^0-9]", "", "g")


def _mascarar_documento(value: str | None) -> str:
    digitos = normalizar_documento(value)
    if len(digitos) == 11:
        return f"***.{digitos[3:6]}.{digitos[6:9]}-**"
    if len(digitos) == 14:
        return f"**.{digitos[2:5]}.{digitos[5:8]}/****-**"
    return "Documento protegido" if digitos else ""


def _item_caso(caso: Case, subtitulo: str) -> dict:
    return {
        "tipo": "caso",
        "id": caso.id,
        "titulo": caso.titulo,
        "subtitulo": subtitulo,
        "link": f"/casos/{caso.id}",
    }


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
@router.get("/")
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
        digitos = normalizar_documento(q)
        if len(digitos) not in (11, 14):
            raise HTTPException(
                status_code=422,
                detail="Informe um CPF ou CNPJ completo para a busca protegida.",
            )

        if cu.role.value in _CLIENTES:
            conds_cli = []
            try:
                blind_index = hash_documento(digitos)
            except RuntimeError:
                blind_index = None
            if blind_index:
                conds_cli.append(
                    Client.cpf_hash == blind_index
                    if len(digitos) == 11
                    else Client.cnpj_hash == blind_index
                )
            # Compatibilidade controlada enquanto o plaintext legado existir:
            # apenas igualdade exata, nunca LIKE parcial.
            conds_cli.append(
                _so_digitos(Client.cpf) == digitos
                if len(digitos) == 11
                else _so_digitos(Client.cnpj) == digitos
            )
            client_query = (
                select(Client)
                .where(Client.deleted_at.is_(None), or_(*conds_cli))
                .order_by(Client.updated_at.desc())
            )
            for client in (
                await db.execute(client_query.limit(limit))
            ).scalars().all():
                documento = client.cpf or client.cnpj
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
        digitos = normalizar_documento(q)
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
        clients = (
            await db.execute(
                select(Client)
                .where(
                    Client.deleted_at.is_(None),
                    or_(
                        Client.nome.ilike(termo),
                        Client.razao_social.ilike(termo),
                    ),
                )
                .limit(limit)
            )
        ).scalars().all()
        for client in clients:
            out.append(
                {
                    "tipo": "cliente",
                    "id": client.id,
                    "titulo": client.nome or client.razao_social or "—",
                    "subtitulo": _mascarar_documento(client.cpf or client.cnpj),
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
        case_ids = select(Case.id).where(
            or_(
                Case.advogado_responsavel_id == cu.id,
                Case.advogado_auxiliar_id == cu.id,
            )
        )
        legal_doc_query = legal_doc_query.where(LegalDoc.case_id.in_(case_ids))
    for legal_doc in (
        await db.execute(legal_doc_query.limit(limit))
    ).scalars().all():
        out.append(
            {
                "tipo": "peca",
                "id": legal_doc.id,
                "titulo": legal_doc.titulo,
                "subtitulo": str(legal_doc.status.value),
                "link": "/pecas",
            }
        )

    return {"q": q, "tipo": tipo, "total": len(out), "resultados": out}
